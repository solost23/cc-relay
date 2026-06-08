import json
import sys

import cc_relay.db as _db
from cc_relay.assessor import assess_risk
from cc_relay.decision import should_interrupt as _should_interrupt
from cc_relay.notifier import send_notification, send_completion_notification

_CODEX_BLOCK_SUFFIX = (
    "Relay blocked this Codex tool call. Codex PreToolUse hooks cannot pause for "
    "interactive approval here, so do not try an alternate tool call or workaround. "
    "Stop and wait for the user to send a new instruction if they want to proceed."
)
_NOTIFICATION_FAILED_SUFFIX = (
    "Relay could not deliver the desktop notification; check your system "
    "notification permissions."
)

# Map Claude Code tool names to relay action_type
_TOOL_TO_ACTION_TYPE = {
    "Read": "file_read",
    "Glob": "file_read",
    "Grep": "file_read",
    "list_files": "file_read",
    "read_file": "file_read",
    "search": "file_read",
    "WebFetch": "network_request",
    "WebSearch": "network_request",
    "web_search": "network_request",
}

# Tools that are always safe — skip assessment entirely
_ALWAYS_ALLOW = {
    "Read", "Glob", "Grep", "WebSearch", "AskUserQuestion", "ExitPlanMode", "LSP",
    "list_files", "read_file", "search",
}
_COMMAND_TOOLS = {"Bash", "shell_command", "exec_command", "unified_exec", "functions.exec_command"}
_PATCH_TOOLS = {"apply_patch", "functions.apply_patch"}

_SYSTEM_PATHS = ("/etc/", "/usr/", "/bin/", "/sbin/", "/boot/", "/sys/", "/proc/")
_CONFIG_EXTS = (".env", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf")
_CONFIG_NAMES = ("dockerfile", "makefile", ".gitignore", ".gitconfig", "requirements.txt")


def _file_action_type(path: str) -> str:
    p = path.lower()
    if any(p.startswith(s) for s in _SYSTEM_PATHS):
        return "file_write:system"
    if any(p.endswith(e) for e in _CONFIG_EXTS) or any(p.endswith(n) for n in _CONFIG_NAMES):
        return "file_write:config"
    return "file_write:code"


def _classify_single_command(cmd: str) -> str:
    """Classify a single shell token (no &&/||/; chaining) into an action type."""
    # force-push variants map to their own high-risk type
    force_push_prefixes = ("git push --force", "git push -f", "git push origin --force",
                           "git push origin -f")
    danger_prefixes = ("rm ", "rm\t", "rmdir", "sudo rm", "git reset", "drop table",
                       "truncate ", "delete from")
    git_prefixes = ("git commit", "git push", "git merge", "git rebase")
    pkg_prefixes = ("pip install", "uv add", "npm install", "apt ", "brew install")
    shell_prefixes = ("mv ", "cp ", "mkdir", "touch ", "chmod", "chown", "curl ", "wget ")
    read_prefixes = ("ls", "cat ", "head ", "tail ", "grep ", "find ", "git log",
                     "git status", "git diff", "git show", "pwd", "which ",
                     "env", "printenv", "ps ",
                     "ps\t", "df ", "du ", "free", "top ", "htop", "uname",
                     "date", "whoami", "id ", "id\t", "wc ", "sort ", "uniq ",
                     "cut ", "awk ", "sed ", "tr ", "xargs ", "tee ",
                     "uv run pytest", "uv run python -c", "python -c", "python3 -c",
                     "node -e", "node -p")

    if ">" in cmd:
        return "bash_write:shell"
    if any(cmd.startswith(p) for p in force_push_prefixes):
        return "git_force_push"
    if any(cmd.startswith(p) for p in danger_prefixes):
        return "file_delete"
    if any(cmd.startswith(p) for p in git_prefixes):
        return "bash_write:git"
    if any(cmd.startswith(p) for p in pkg_prefixes):
        return "bash_write:package_manager"
    if any(cmd.startswith(p) for p in shell_prefixes):
        return "bash_write:shell"
    if any(cmd.startswith(p) for p in read_prefixes):
        return "bash_read"
    return "bash_write:shell"


def _bash_action_type(command: str) -> str:
    import re
    # Split on shell separators (&&, ||, ;, |) to find the most dangerous segment.
    # Newlines also separate commands in multi-line scripts.
    segments = re.split(r"&&|\|\||;|\n|\|", command)
    types = [_classify_single_command(s.strip().lower()) for s in segments if s.strip()]
    if not types:
        return "bash_write:shell"

    # Risk priority: higher index = higher risk
    _RISK_ORDER = ["bash_read", "bash_write:shell", "bash_write:package_manager",
                   "bash_write:git", "file_delete", "git_force_push"]

    def _rank(t: str) -> int:
        try:
            return _RISK_ORDER.index(t)
        except ValueError:
            return len(_RISK_ORDER)  # unknown types treated as highest

    return max(types, key=_rank)


def _get_command(tool_input: dict) -> str:
    command = tool_input.get("command") or tool_input.get("cmd") or tool_input.get("shell_command")
    if command:
        return str(command)
    argv = tool_input.get("argv") or tool_input.get("args")
    if isinstance(argv, list):
        return " ".join(str(arg) for arg in argv)
    return ""


def _get_action_type(tool_name: str, tool_input: dict) -> str:
    if tool_name in _COMMAND_TOOLS:
        return _bash_action_type(_get_command(tool_input))
    if tool_name in ("Write", "Edit", "NotebookEdit"):
        path = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
        return _file_action_type(path)
    if tool_name in _PATCH_TOOLS:
        patch = tool_input.get("patch", "") or tool_input.get("input", "")
        if not str(patch).strip():
            return "file_patch:unknown"
        if "delete file" in str(patch).lower():
            return "file_delete"
        return "file_write:code"
    return _TOOL_TO_ACTION_TYPE.get(tool_name, "bash_write:shell")


def _get_description(tool_name: str, tool_input: dict) -> str:
    if tool_name in _COMMAND_TOOLS:
        return _get_command(tool_input)[:200]
    if tool_name in ("Write", "Edit", "NotebookEdit"):
        return tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
    if tool_name in _PATCH_TOOLS:
        patch = tool_input.get("patch", "") or tool_input.get("input", "")
        return str(patch)[:200] or "apply_patch with unavailable patch contents"
    if tool_name in ("Read", "Glob", "Grep"):
        return tool_input.get("file_path", "") or tool_input.get("pattern", "")
    if tool_name in ("WebFetch", "WebSearch"):
        return tool_input.get("url", "") or tool_input.get("query", "")
    return json.dumps(tool_input)[:200]


def _client_name(payload: dict, client: str | None = None) -> str:
    if client in ("claude", "codex"):
        return client
    if "hook_event_name" in payload:
        return "codex"
    return "claude"


def handle_pre_tool_use(payload: dict, client: str | None = None) -> dict:
    client_name = _client_name(payload, client)
    tool_name = payload.get("tool_name", "")

    if tool_name in _ALWAYS_ALLOW:
        return _allow(client_name)

    action_type = _get_action_type(tool_name, payload.get("tool_input", {}))
    description = _get_description(tool_name, payload.get("tool_input", {}))

    interrupt, reason = _should_interrupt(
        action_type,
        description,
    )

    if interrupt:
        risk = assess_risk(action_type, description)
        _db.record_decision(action_type, description, "rejected", risk["risk_level"])
        notified = send_notification(
            message=f"{tool_name}: {description[:100]}",
            client=client_name,
        )
        if not notified:
            reason = f"{reason} {_NOTIFICATION_FAILED_SUFFIX}"
        return _interrupt(reason, client_name)

    risk = assess_risk(action_type, description)
    _db.record_decision(action_type, description, "approved", risk["risk_level"])
    return _allow(client_name)


def handle_post_tool_use(payload: dict) -> dict:
    """Flip the pre-recorded rejected decision to approved — tool ran means user approved."""
    tool_name = payload.get("tool_name", "")
    if tool_name in _ALWAYS_ALLOW:
        return {}

    action_type = _get_action_type(tool_name, payload.get("tool_input", {}))
    description = _get_description(tool_name, payload.get("tool_input", {}))

    _db.approve_latest_rejected(action_type, description)
    return {}


def handle_stop(payload: dict, client: str | None = None) -> dict:
    send_completion_notification(_client_name(payload, client))
    return {}


def _allow(client: str = "claude") -> dict:
    if client == "codex":
        return {}
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }


def _interrupt(reason: str, client: str = "claude") -> dict:
    if client == "codex":
        reason = f"{reason} {_CODEX_BLOCK_SUFFIX}"
        return {
            "decision": "block",
            "reason": reason,
        }
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }


def run_pre_tool_use(client: str | None = None) -> None:
    payload = _read_payload()
    result = handle_pre_tool_use(payload, client)
    if result:
        print(json.dumps(result))


def run_post_tool_use() -> None:
    payload = _read_payload()
    result = handle_post_tool_use(payload)
    if result:
        print(json.dumps(result))


def run_stop(client: str | None = None) -> None:
    payload = _read_payload()
    handle_stop(payload, client)


def _read_payload() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}
