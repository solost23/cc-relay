import json
import sys

import relay.db as _db
from relay.assessor import assess_risk
from relay.decision import should_interrupt as _should_interrupt
from relay.notifier import send_notification

# Map Claude Code tool names to relay action_type
_TOOL_TO_ACTION_TYPE = {
    "Write": "file_write",
    "Edit": "file_write",
    "Read": "file_read",
    "Glob": "file_read",
    "Grep": "file_read",
    "NotebookEdit": "file_write",
    "WebFetch": "network_request",
    "WebSearch": "network_request",
}

# Tools that are always safe — skip assessment entirely
_ALWAYS_ALLOW = {"Read", "Glob", "Grep", "WebSearch", "AskUserQuestion", "ExitPlanMode", "LSP"}


def _bash_action_type(command: str) -> str:
    cmd = command.strip().lower()
    danger_prefixes = ("rm ", "rm\t", "rmdir", "sudo rm", "git reset", "git push --force",
                       "git push -f", "drop table", "truncate ", "delete from")
    write_prefixes = ("git commit", "git push", "git merge", "git rebase", "pip install",
                      "uv add", "npm install", "apt ", "brew install", "curl ", "wget ",
                      "mv ", "cp ", "mkdir", "touch ", "chmod", "chown")
    read_prefixes = ("ls", "cat ", "head ", "tail ", "grep ", "find ", "git log",
                     "git status", "git diff", "git show", "echo ", "pwd", "which ",
                     "uv run pytest", "uv run python -c")

    if any(cmd.startswith(p) for p in danger_prefixes):
        return "file_delete"
    if any(cmd.startswith(p) for p in write_prefixes):
        return "bash_write"
    if any(cmd.startswith(p) for p in read_prefixes):
        return "bash_read"
    return "bash_write"


def _get_action_type(tool_name: str, tool_input: dict) -> str:
    if tool_name == "Bash":
        return _bash_action_type(tool_input.get("command", ""))
    return _TOOL_TO_ACTION_TYPE.get(tool_name, "bash_write")


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
        send_notification(message=f"{tool_name}: {description[:100]}")
        return _ask(reason)

    risk = assess_risk(action_type, description)
    _db.record_decision(action_type, description, "approved", risk["risk_level"])
    return _allow()


def handle_post_tool_use(payload: dict) -> dict:
    """Record approved decisions for actions that went through the ask prompt."""
    tool_name = payload.get("tool_name", "")
    if tool_name in _ALWAYS_ALLOW:
        return {}

    action_type = _get_action_type(tool_name, payload.get("tool_input", {}))
    description = _get_description(tool_name, payload.get("tool_input", {}))

    interrupt, _ = _should_interrupt(action_type, description)
    if not interrupt:
        # pre_tool_use already recorded this as auto-approved
        return {}

    # Tool ran = user approved the ask prompt
    risk = assess_risk(action_type, description)
    _db.record_decision(action_type, description, "approved", risk["risk_level"])
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
