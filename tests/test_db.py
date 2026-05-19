import pathlib
import tempfile

import pytest

from cc_relay.db import (
    approve_latest_rejected, get_active_days, get_approval_rate,
    get_count, get_recent_decisions, get_stats, init_db, record_decision,
    reset_action_type,
)
import cc_relay.db as db_module


@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "test.db"
    init_db(path)
    monkeypatch.setattr(db_module, "_DEFAULT_DB", path)
    return path


def test_init_creates_table(db):
    init_db(db)
    assert db.exists()


def test_approval_rate_no_history_returns_neutral(db):
    assert get_approval_rate("bash_write") == 0.5


def test_approval_rate_all_approved(db):
    for _ in range(3):
        record_decision("bash_write", "ls", "approved", "low")
    assert get_approval_rate("bash_write") == 1.0


def test_approval_rate_mixed(db):
    record_decision("file_write", "write a", "approved", "medium")
    record_decision("file_write", "write b", "approved", "medium")
    record_decision("file_write", "write c", "rejected", "medium")
    rate = get_approval_rate("file_write")
    assert abs(rate - 2 / 3) < 0.001


def test_approval_rate_all_rejected(db):
    record_decision("file_delete", "rm x", "rejected", "high")
    assert get_approval_rate("file_delete") == 0.0


def test_get_recent_decisions_order(db):
    record_decision("git_push", "push main", "approved", "medium")
    record_decision("git_push", "push feat", "rejected", "medium")
    rows = get_recent_decisions("git_push", limit=10)
    assert len(rows) == 2
    assert rows[0]["decision"] == "rejected"  # most recent first (higher id)


def test_get_recent_decisions_limit(db):
    for i in range(5):
        record_decision("bash_write", f"cmd {i}", "approved", "low")
    rows = get_recent_decisions("bash_write", limit=3)
    assert len(rows) == 3


def test_get_stats_empty(db):
    stats = get_stats()
    assert stats["total_decisions"] == 0
    assert stats["by_action_type"] == []


def test_approval_rate_respects_window(db):
    # Insert 60 records: first 50 rejected, last 10 approved.
    # Window is 50 most recent, so rate should be 10/50 = 0.2
    for _ in range(50):
        record_decision("bash_write", "old cmd", "rejected", "medium")
    for _ in range(10):
        record_decision("bash_write", "new cmd", "approved", "medium")
    rate = get_approval_rate("bash_write")
    assert abs(rate - 10 / 50) < 0.001


def test_get_stats_populated(db):
    record_decision("file_write", "a", "approved", "medium")
    record_decision("file_write", "b", "approved", "medium")
    record_decision("file_delete", "c", "rejected", "high")
    stats = get_stats()
    assert stats["total_decisions"] == 3
    types = {r["action_type"]: r for r in stats["by_action_type"]}
    assert types["file_write"]["approval_rate"] == 1.0
    assert types["file_delete"]["approval_rate"] == 0.0


# --- approve_latest_rejected ---

def test_approve_latest_rejected_flips_to_approved(db):
    record_decision("file_delete", "rm foo", "rejected", "high")
    approve_latest_rejected("file_delete", "rm foo")
    assert get_approval_rate("file_delete") == 1.0


def test_approve_latest_rejected_picks_most_recent(db):
    record_decision("bash_write:git", "git push", "rejected", "medium")
    record_decision("bash_write:git", "git push", "rejected", "medium")
    approve_latest_rejected("bash_write:git", "git push")
    # one approved, one still rejected → rate = 0.5
    assert abs(get_approval_rate("bash_write:git") - 0.5) < 0.001


def test_approve_latest_rejected_no_match_is_noop(db):
    approve_latest_rejected("file_delete", "rm nonexistent")
    assert get_approval_rate("file_delete") == 0.5  # no records


def test_approve_latest_rejected_fallback_to_action_type_only(db):
    record_decision("bash_write:git", "git push origin master", "rejected", "medium")
    # description mismatch — should still resolve via action_type fallback
    approve_latest_rejected("bash_write:git", "git push origin main")
    assert get_approval_rate("bash_write:git") == 1.0


# --- reset ---

def test_reset_action_type(db):
    for _ in range(5):
        record_decision("bash_write:git", "git push", "approved", "medium")
    count = reset_action_type("bash_write:git")
    assert count == 5
    assert get_approval_rate("bash_write:git") == 0.5  # back to neutral


def test_reset_action_type_nonexistent(db):
    count = reset_action_type("nonexistent_type")
    assert count == 0


# --- get_active_days ---

def test_get_active_days_no_history(db):
    assert get_active_days("bash_write:git") == 0


def test_get_active_days_counts_distinct_days(db):
    # 3 records on the same day → still 1 active day
    for _ in range(3):
        record_decision("bash_write:git", "git push", "approved", "medium")
    assert get_active_days("bash_write:git") == 1


def test_get_active_days_outside_window_not_counted(db):
    import sqlite3
    from cc_relay.db import _db_path
    # Insert a record 31 days ago directly
    with sqlite3.connect(_db_path(None)) as conn:
        conn.execute(
            "INSERT INTO decisions (action_type, action_description, decision, risk_level, created_at) VALUES (?, ?, ?, ?, datetime('now', '-31 days'))",
            ("bash_write:git", "old push", "approved", "medium"),
        )
    assert get_active_days("bash_write:git", window_days=30) == 0


def test_resolve_pending_fallback_to_action_type_only(db):
    record_decision("bash_write:git", "git push origin master", "rejected", "medium")
    # description mismatch — should still resolve via action_type fallback
    approve_latest_rejected("bash_write:git", "git push origin main")
    assert get_approval_rate("bash_write:git") == 1.0


def test_get_count_uses_window(db):
    # Insert more than the window size; get_count should cap at window size
    from cc_relay.db import _APPROVAL_RATE_WINDOW
    for i in range(_APPROVAL_RATE_WINDOW + 10):
        record_decision("bash_write:git", f"cmd {i}", "approved", "medium")
    assert get_count("bash_write:git") == _APPROVAL_RATE_WINDOW


