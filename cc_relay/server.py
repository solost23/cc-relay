from mcp.server.fastmcp import FastMCP

import cc_relay.db as _db
from cc_relay.assessor import assess_risk
from cc_relay.decision import should_interrupt as _should_interrupt
from cc_relay.installer import ensure_installed
from cc_relay.notifier import send_notification

mcp = FastMCP("relay")

_db.init_db()
ensure_installed()


@mcp.tool()
def assess_action(action_type: str, action_description: str) -> dict:
    """
    Assess whether an action requires user confirmation before execution.

    Call this before any non-trivial operation. Returns should_interrupt=True
    when the user should be asked, along with reasoning. When should_interrupt
    is True, a desktop notification is sent automatically.

    action_type: category of the action (e.g. 'file_delete', 'bash_write', 'git_push')
    action_description: human-readable description of what will happen
    """
    interrupt, reason = _should_interrupt(action_type, action_description)
    risk = assess_risk(action_type, action_description)

    if interrupt:
        send_notification(message=f"{action_type}: {action_description[:100]}")

    return {
        "should_interrupt": interrupt,
        "risk_level": risk["risk_level"],
        "reversible": risk["reversible"],
        "approval_rate": round(_db.get_approval_rate(action_type), 3),
        "reason": reason,
    }


@mcp.tool()
def record_decision(
    action_type: str,
    action_description: str,
    decision: str,
    risk_level: str,
) -> dict:
    """
    Record the user's decision for an action to improve future assessments.

    action_type: same value passed to assess_action
    action_description: same value passed to assess_action
    decision: 'approved' or 'rejected'
    risk_level: risk_level returned by assess_action
    """
    if decision not in ("approved", "rejected"):
        return {"recorded": False, "error": "decision must be 'approved' or 'rejected'"}

    _db.record_decision(
        action_type=action_type,
        action_description=action_description,
        decision=decision,
        risk_level=risk_level,
    )
    return {"recorded": True}


@mcp.tool()
def get_stats_tool() -> dict:
    """
    Return approval rate statistics for all action types.

    Use this to inspect what relay has learned — which operations are auto-approved,
    which still require confirmation, and how many decisions have been recorded total.
    """
    return _db.get_stats()


@mcp.tool()
def get_recent_decisions_tool(action_type: str, limit: int = 20) -> dict:
    """
    Get recent decision history for a specific action type.

    Useful for auditing what relay has learned and debugging auto-approve behavior.

    action_type: the action type to query (e.g. 'file_delete', 'bash_write:git')
    limit: max number of records to return (default 20)
    """
    decisions = _db.get_recent_decisions(action_type, limit)
    return {"action_type": action_type, "decisions": decisions, "count": len(decisions)}


@mcp.tool()
def reset_action_type_tool(action_type: str) -> dict:
    """
    Delete all decision history for a specific action type.

    Use this to reset learned behavior so relay will start building a new baseline
    from scratch for that action type.

    action_type: the action type to reset (e.g. 'file_delete', 'bash_write:git')
    """
    count = _db.reset_action_type(action_type)
    return {"reset": True, "deleted_count": count, "action_type": action_type}


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
