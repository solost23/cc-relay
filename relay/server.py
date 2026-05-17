from mcp.server.fastmcp import FastMCP

import relay.db as _db
from relay.assessor import assess_risk
from relay.decision import should_interrupt as _should_interrupt
from relay.installer import ensure_installed
from relay.notifier import send_notification

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
        send_notification(
            title="Relay: Waiting for your confirmation",
            message=f"{action_type}: {action_description[:100]}\n\nReturn to your terminal to respond.",
        )

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


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
