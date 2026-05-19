import json
import sys

import cc_relay.db as _db
from cc_relay.assessor import assess_risk
from cc_relay.decision import should_interrupt as _should_interrupt
from cc_relay.notifier import send_notification

# Map Claude Code tool names to relay action_type
_TOOL_TO_ACTION_TYPE = {
    "Read": "file_read",
    "Glob": "file_read",
    "Grep": "file_read",
    "WebFetch": "network_request",
    "WebSearch": "network_request",
}

# Tools that are always safe — skip assessment entirely
_ALWAYS_ALLOW = {"Read", "Glob", "Grep", "WebSearch", "AskUserQuestion", "ExitPlanMode", "LSP"}

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
                     "uv run pytest", "uv run python -c")

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


def _get_action_type(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Bash":
        return _bash_action_type(tool_input.get("command", ""))
    if tool_name in ("Write", "Edit", "NotebookEdit"):
        path = tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
        return _file_action_type(path)
    return _TOOL_TO_ACTION_TYPE.get(tool_name, "bash_write:shell")


def _get_description(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Bash":
        return tool_input.get("command", "")[:200]
    if tool_name in ("Write", "Edit", "NotebookEdit"):
        return tool_input.get("file_path", "") or tool_input.get("notebook_path", "")
    if tool_name in ("Read", "Glob", "Grep"):
        return tool_input.get("file_path", "") or tool_input.get("pattern", "")
    if tool_name in ("WebFetch", "WebSearch"):
        return tool_input.get("url", "") or tool_input.get("query", "")
    return json.dumps(tool_input)[:200]


def handle_pre_tool_use(payload: dict) -> dict:
    tool_name = payload.get("tool_name", "")

    if tool_name in _ALWAYS_ALLOW:
        return _allow()

    action_type = _get_action_type(tool_name, payload.get("tool_input", {}))
    description = _get_description(tool_name, payload.get("tool_input", {}))

    interrupt, reason = _should_interrupt(action_type, description)

    if interrupt:
        risk = assess_risk(action_type, description)
        _db.add_pending(action_type, description, risk["risk_level"])
        send_notification(message=f"{tool_name}: {description[:100]}")
        return _ask(reason)

    risk = assess_risk(action_type, description)
    _db.record_decision(action_type, description, "approved", risk["risk_level"])
    return _allow()


def handle_post_tool_use(payload: dict) -> dict:
    """Resolve pending decisions for actions that went through the ask prompt."""
    tool_name = payload.get("tool_name", "")
    if tool_name in _ALWAYS_ALLOW:
        return {}

    action_type = _get_action_type(tool_name, payload.get("tool_input", {}))
    description = _get_description(tool_name, payload.get("tool_input", {}))

    # Unconditionally attempt to resolve: resolve_pending is a noop if no pending record exists.
    # Re-evaluating should_interrupt here is wrong — the decision state may have changed
    # since pre_tool_use ran, causing pending records to leak.
    _db.resolve_pending(action_type, description)
    return {}


def handle_stop(payload: dict) -> dict:
    """Flush all pending decisions as rejected when the session ends."""
    _db.flush_pending_as_rejected()
    return {}


def _allow() -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }


def _ask(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "ask",
            "permissionDecisionReason": reason,
        }
    }


def run_pre_tool_use() -> None:
    payload = json.loads(sys.stdin.read())
    result = handle_pre_tool_use(payload)
    print(json.dumps(result))


def run_post_tool_use() -> None:
    payload = json.loads(sys.stdin.read())
    result = handle_post_tool_use(payload)
    if result:
        print(json.dumps(result))


def run_stop() -> None:
    payload = json.loads(sys.stdin.read())
    handle_stop(payload)
