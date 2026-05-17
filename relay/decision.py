from relay.assessor import assess_risk
import relay.db as _db

_MIN_SAMPLES = 5  # minimum decisions before trusting approval rate


def should_interrupt(action_type: str, description: str) -> tuple[bool, str]:
    """
    Core decision logic shared by hook and MCP server.
    Returns (interrupt: bool, reason: str).
    """
    risk = assess_risk(action_type, description)
    risk_level = risk["risk_level"]
    approval_rate = _db.get_approval_rate(action_type)
    total = sum(
        r["total"]
        for r in _db.get_stats()["by_action_type"]
        if r["action_type"] == action_type
    )
    has_enough_history = total >= _MIN_SAMPLES

    if risk_level == "high":
        return True, f"High-risk operation: {risk['reason']}"

    if risk_level == "low":
        if has_enough_history and approval_rate >= 0.9:
            return False, f"Auto-approved: low risk, {approval_rate:.0%} approval rate over {total} decisions."
        if not has_enough_history:
            return False, "Low risk — proceeding automatically."

    # medium or low without enough history
    if not has_enough_history:
        return True, f"Not enough history for '{action_type}' yet ({total}/{_MIN_SAMPLES} decisions) — asking to build baseline."

    if approval_rate >= 0.8:
        return False, f"Auto-approved: {approval_rate:.0%} approval rate over {total} decisions."

    return True, f"{risk_level.capitalize()} risk, only {approval_rate:.0%} approval rate over {total} decisions."
