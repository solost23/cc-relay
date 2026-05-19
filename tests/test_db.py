import pathlib
import tempfile

import pytest

from cc_relay.db import (
    add_pending, flush_pending_as_rejected, get_active_days, get_approval_rate,
    get_recent_decisions, get_stats, init_db, record_decision,
    reset_action_type, resolve_pending,
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


# --- pending decisions ---

def test_resolve_pending_records_approved(db):
    add_pending("file_delete", "rm foo", "high")
    resolve_pending("file_delete", "rm foo")
    assert get_approval_rate("file_delete") == 1.0
    assert get_approval_rate("file_delete") == 1.0  # only one record


def test_resolve_pending_fifo(db):
    add_pending("bash_write:git", "git push", "medium")
    add_pending("bash_write:git", "git push", "medium")
    resolve_pending("bash_write:git", "git push")
    # one resolved as approved, one still pending
    from cc_relay.db import _db_path
    import sqlite3
    with sqlite3.connect(_db_path(None)) as conn:
        count = conn.execute("SELECT COUNT(*) FROM pending_decisions").fetchone()[0]
    assert count == 1
    assert get_approval_rate("bash_write:git") == 1.0


def test_resolve_pending_no_match_is_noop(db):
    resolve_pending("file_delete", "rm nonexistent")
    assert get_approval_rate("file_delete") == 0.5  # no records


def test_flush_pending_as_rejected(db):
    add_pending("file_delete", "rm a", "high")
    add_pending("file_delete", "rm b", "high")
    add_pending("bash_write:git", "git push", "medium")
    count = flush_pending_as_rejected()
    assert count == 3
    assert get_approval_rate("file_delete") == 0.0
    assert get_approval_rate("bash_write:git") == 0.0


def test_flush_pending_clears_table(db):
    add_pending("file_delete", "rm x", "high")
    flush_pending_as_rejected()
    # second flush should return 0
    assert flush_pending_as_rejected() == 0


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


def test_get_active_days_within_window_counted(db):
    import sqlite3
    from cc_relay.db import _db_path
    with sqlite3.connect(_db_path(None)) as conn:
        conn.execute(
            "INSERT INTO decisions (action_type, action_description, decision, risk_level, created_at) VALUES (?, ?, ?, ?, datetime('now', '-5 days'))",
            ("bash_write:git", "recent push", "approved", "medium"),
        )
    assert get_active_days("bash_write:git", window_days=30) == 1

