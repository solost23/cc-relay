from relay.assessor import assess_risk


def test_high_risk_types():
    for t in (
        "file_delete", "db_drop", "git_reset", "git_force_push", "rm_rf",
        "git_rebase", "git_amend", "env_write", "secret_write",
        "permission_change", "network_send", "ci_cd_modify", "cron_write",
    ):
        r = assess_risk(t, "some action")
        assert r["risk_level"] == "high", f"{t} should be high"
        assert r["reversible"] is False


def test_low_risk_types():
    for t in ("file_read", "bash_read", "git_log", "git_status", "git_diff", "db_read"):
        r = assess_risk(t, "some action")
        assert r["risk_level"] == "low", f"{t} should be low"
        assert r["reversible"] is True


def test_medium_risk_types():
    for t in ("file_write", "file_create", "db_write", "git_commit", "git_push", "bash_write"):
        r = assess_risk(t, "some action")
        assert r["risk_level"] == "medium", f"{t} should be medium"


def test_unknown_type_with_danger_word_in_description():
    r = assess_risk("custom_op", "delete all user records")
    assert r["risk_level"] == "high"


def test_unknown_type_without_danger_word():
    r = assess_risk("custom_op", "process the queue")
    assert r["risk_level"] == "medium"


def test_case_insensitive_type():
    r = assess_risk("FILE_DELETE", "rm something")
    assert r["risk_level"] == "high"
