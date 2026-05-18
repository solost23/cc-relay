_HIGH_RISK_TYPES = {
    "file_delete",
    "db_drop",
    "git_reset",
    "git_force_push",
    "git_rebase",
    "git_amend",
    "rm_rf",
    "process_kill",
    "file_write:system",
    "env_write",
    "secret_write",
    "permission_change",
    "network_send",
    "ci_cd_modify",
    "cron_write",
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
    "file_write:code",
    "file_write:config",
    "file_create",
    "db_write",
    "db_update",
    "bash_write:git",
    "bash_write:package_manager",
    "bash_write:shell",
    "network_request",
    # legacy — kept for existing DB records
    "file_write",
    "git_commit",
    "git_push",
    "bash_write",
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
