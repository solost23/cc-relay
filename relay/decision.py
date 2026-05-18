from relay.assessor import assess_risk
import relay.db as _db

_MIN_SAMPLES_LOW = 5     # low-risk actions need fewer samples to trust
_MIN_SAMPLES_MEDIUM = 10  # medium-risk actions need more evidence before auto-approving

_AUTO_APPROVE_RATE_LOW = 0.9
_AUTO_APPROVE_RATE_MEDIUM = 0.85


def _get_total(action_type: str) -> int:
    return sum(
        r["total"]
        for r in _db.get_stats()["by_action_type"]
        if r["action_type"] == action_type
    )


def should_interrupt(action_type: str, description: str) -> tuple[bool, str]:
    """
    Core decision logic shared by hook and MCP server.
    Returns (interrupt: bool, reason: str).
    """
    risk = assess_risk(action_type, description)
    risk_level = risk["risk_level"]
    approval_rate = _db.get_approval_rate(action_type)
    total = _get_total(action_type)

    if risk_level == "high":
        return True, f"High-risk operation: {risk['reason']}"

    if risk_level == "low":
        if total >= _MIN_SAMPLES_LOW and approval_rate >= _AUTO_APPROVE_RATE_LOW:
            return False, f"Auto-approved: low risk, {approval_rate:.0%} approval rate over {total} decisions."
        # low risk with no/insufficient history: proceed silently, no need to build baseline
        if total < _MIN_SAMPLES_LOW:
            return False, "Low risk — proceeding automatically."

    # medium (or low that failed the approval-rate check above)
    min_samples = _MIN_SAMPLES_MEDIUM if risk_level == "medium" else _MIN_SAMPLES_LOW
    auto_rate = _AUTO_APPROVE_RATE_MEDIUM if risk_level == "medium" else _AUTO_APPROVE_RATE_LOW

    if total < min_samples:
        return True, f"Not enough history for '{action_type}' yet ({total}/{min_samples} decisions) — asking to build baseline."

    if approval_rate >= auto_rate:
        return False, f"Auto-approved: {approval_rate:.0%} approval rate over {total} decisions."

    return True, f"{risk_level.capitalize()} risk, only {approval_rate:.0%} approval rate over {total} decisions."
