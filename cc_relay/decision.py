from cc_relay.assessor import assess_risk
import cc_relay.db as _db

_MIN_WEIGHT_LOW = 4.0
_MIN_WEIGHT_MEDIUM = 7.0

_AUTO_APPROVE_RATE_LOW = 0.9
_AUTO_APPROVE_RATE_MEDIUM = 0.85


def should_interrupt(action_type: str, description: str) -> tuple[bool, str]:
    """
    Core decision logic shared by hook and MCP server.
    Returns (interrupt: bool, reason: str).
    """
    risk = assess_risk(action_type, description)
    risk_level = risk["risk_level"]
    approval_rate = _db.get_approval_rate(action_type)
    total = _db.get_count(action_type)

    if risk_level == "high":
        return True, f"High-risk operation: {risk['reason']}"

    if risk_level == "low":
        if total >= _MIN_WEIGHT_LOW and approval_rate >= _AUTO_APPROVE_RATE_LOW:
            return False, f"Auto-approved: low risk, {approval_rate:.0%} approval rate."
        if total < _MIN_WEIGHT_LOW:
            return False, "Low risk — proceeding automatically."

    # medium (or low that failed the approval-rate check above)
    if risk_level == "medium":
        min_weight = _MIN_WEIGHT_MEDIUM
        auto_rate = _AUTO_APPROVE_RATE_MEDIUM
    else:
        min_weight = _MIN_WEIGHT_LOW
        auto_rate = _AUTO_APPROVE_RATE_LOW

    if total < min_weight:
        return True, f"Not enough history for '{action_type}' yet — asking to build baseline."

    if approval_rate >= auto_rate:
        return False, f"Auto-approved: {approval_rate:.0%} approval rate."

    return True, f"{risk_level.capitalize()} risk, only {approval_rate:.0%} approval rate."
