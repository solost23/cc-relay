_HIGH_RISK_TYPES = {
    "file_delete",
    "db_drop",
    "git_reset",
    "git_force_push",
    "rm_rf",
    "process_kill",
}

_LOW_RISK_TYPES = {
    "file_read",
    "bash_read",
    "git_log",
    "git_status",
    "git_diff",
    "db_read",
    "list_files",
}

_MEDIUM_RISK_TYPES = {
    "file_write",
    "file_create",
    "db_write",
    "db_update",
    "git_commit",
    "git_push",
    "bash_write",
    "network_request",
}


def assess_risk(action_type: str, action_description: str) -> dict:
    """Return risk_level, reversible flag, and reason for the given action."""
    t = action_type.lower()

    if t in _HIGH_RISK_TYPES:
        return {
            "risk_level": "high",
            "reversible": False,
            "reason": f"Action type '{action_type}' is destructive and not reversible.",
        }

    if t in _LOW_RISK_TYPES:
        return {
            "risk_level": "low",
            "reversible": True,
            "reason": f"Action type '{action_type}' is read-only and safe.",
        }

    if t in _MEDIUM_RISK_TYPES:
        return {
            "risk_level": "medium",
            "reversible": True,
            "reason": f"Action type '{action_type}' modifies state but is generally recoverable.",
        }

    # Heuristic fallback: scan description for danger words
    danger_words = {"delete", "remove", "drop", "truncate", "force", "overwrite", "rm"}
    desc_lower = action_description.lower()
    if any(w in desc_lower for w in danger_words):
        return {
            "risk_level": "high",
            "reversible": False,
            "reason": "Description contains potentially destructive keywords.",
        }

    return {
        "risk_level": "medium",
        "reversible": True,
        "reason": f"Unknown action type '{action_type}'; defaulting to medium risk.",
    }
