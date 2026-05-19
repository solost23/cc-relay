from cc_relay.assessor import assess_risk
import cc_relay.db as _db

_MIN_SAMPLES_LOW = 5

_AUTO_APPROVE_RATE_LOW = 0.9
_AUTO_APPROVE_RATE_MEDIUM = 0.85

# Adaptive min_samples thresholds for medium-risk actions.
# Keyed by number of distinct active days in the past 30 days.
_ADAPTIVE_THRESHOLDS = [
    (7, 5),   # used on 7+ days → high-frequency → need only 5 samples
    (2, 8),   # used on 2-6 days → moderate frequency → need 8 samples
    (0, 12),  # used on 0-1 days → low-frequency or new → need 12 samples
]


def _adaptive_min_samples(action_type: str) -> int:
    active_days = _db.get_active_days(action_type)
    for threshold, min_samples in _ADAPTIVE_THRESHOLDS:
        if active_days >= threshold:
            return min_samples
    return _ADAPTIVE_THRESHOLDS[-1][1]


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
        if total >= _MIN_SAMPLES_LOW and approval_rate >= _AUTO_APPROVE_RATE_LOW:
            return False, f"Auto-approved: low risk, {approval_rate:.0%} approval rate over {total} decisions."
        if total < _MIN_SAMPLES_LOW:
            return False, "Low risk — proceeding automatically."

    # medium (or low that failed the approval-rate check above)
    if risk_level == "medium":
        min_samples = _adaptive_min_samples(action_type)
        auto_rate = _AUTO_APPROVE_RATE_MEDIUM
    else:
        min_samples = _MIN_SAMPLES_LOW
        auto_rate = _AUTO_APPROVE_RATE_LOW

    if total < min_samples:
        return True, f"Not enough history for '{action_type}' yet ({total}/{min_samples} decisions) — asking to build baseline."

    if approval_rate >= auto_rate:
        return False, f"Auto-approved: {approval_rate:.0%} approval rate over {total} decisions."

    return True, f"{risk_level.capitalize()} risk, only {approval_rate:.0%} approval rate over {total} decisions."
