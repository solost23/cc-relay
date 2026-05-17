import json
import sys

import relay.db as _db
from relay.assessor import assess_risk
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

# Low-risk tools that never need interruption
_ALWAYS_ALLOW = {"Read", "Glob", "Grep", "WebSearch", "AskUserQuestion", "ExitPlanMode", "LSP"}


def _bash_action_type(command: str) -> str:
    """Infer action_type from a bash command string."""
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
    return "bash_write"  # default bash to write-risk


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

    risk = assess_risk(action_type, description)
    approval_rate = _db.get_approval_rate(action_type)
    risk_level = risk["risk_level"]
    has_history = len(_db.get_recent_decisions(action_type, limit=1)) > 0

    if risk_level == "high":
        should_interrupt = True
        reason = f"High-risk operation: {risk['reason']}"
    elif risk_level == "low" and has_history and approval_rate >= 0.9:
        should_interrupt = False
        reason = "Auto-approved: low risk with high historical approval rate."
    elif not has_history:
        should_interrupt = risk_level != "low"
        reason = f"First time seeing '{action_type}' — asking once to establish baseline."
    else:
        should_interrupt = approval_rate < 0.8
        reason = f"{risk_level.capitalize()} risk, {approval_rate:.0%} historical approval rate."

    if should_interrupt:
        send_notification(
            title="Relay: Action needs your approval",
            message=f"{tool_name}: {description[:100]}\n\nReturn to your terminal to respond.",
        )
        return _deny(reason)

    # Auto-approved — record it
    _db.record_decision(action_type, description, "approved", risk_level)
    return _allow()


def handle_post_tool_use(payload: dict) -> dict:
    """Record decisions for operations that were interrupted and user approved."""
    tool_name = payload.get("tool_name", "")
    if tool_name in _ALWAYS_ALLOW:
        return {}

    action_type = _get_action_type(tool_name, payload.get("tool_input", {}))
    description = _get_description(tool_name, payload.get("tool_input", {}))
    risk = assess_risk(action_type, description)

    # Tool ran successfully — user must have approved it
    _db.record_decision(action_type, description, "approved", risk["risk_level"])
    return {}


def _allow() -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "allow",
        }
    }


def _deny(reason: str) -> dict:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
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
