import pathlib
import tempfile

import pytest

from cc_relay.db import get_approval_rate, get_recent_decisions, get_stats, init_db, record_decision
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
