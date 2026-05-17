from mcp.server.fastmcp import FastMCP

import relay.db as _db
from relay.assessor import assess_risk
from relay.installer import ensure_installed
from relay.notifier import send_notification

mcp = FastMCP("relay")

_db.init_db()
ensure_installed()


def _has_any_history(action_type: str) -> bool:
    return len(_db.get_recent_decisions(action_type, limit=1)) > 0


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
    risk = assess_risk(action_type, action_description)
    approval_rate = _db.get_approval_rate(action_type)
    risk_level = risk["risk_level"]
    has_history = approval_rate != 0.5 or _has_any_history(action_type)

    if risk_level == "high":
        should_interrupt = True
        reason = f"High-risk action ({risk['reason']})"
    elif risk_level == "low" and has_history and approval_rate >= 0.9:
        should_interrupt = False
        reason = f"Low risk and {approval_rate:.0%} historical approval rate — proceeding automatically."
    elif not has_history:
        should_interrupt = risk_level != "low"
        reason = f"No history for '{action_type}' yet — asking once to establish baseline."
    else:
        should_interrupt = approval_rate < 0.8
        reason = (
            f"{risk_level.capitalize()} risk, {approval_rate:.0%} historical approval rate."
        )

    if should_interrupt:
        send_notification(
            title="Relay: Waiting for your confirmation",
            message=f"{action_type}: {action_description[:100]}\n\nReturn to your terminal to respond.",
        )

    return {
        "should_interrupt": should_interrupt,
        "risk_level": risk_level,
        "reversible": risk["reversible"],
        "approval_rate": round(approval_rate, 3),
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

    Call this after the user responds to a confirmation request.

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
