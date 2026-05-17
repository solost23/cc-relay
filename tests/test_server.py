import pathlib

import pytest

import relay.db as db_module
from relay.server import assess_action, record_decision


@pytest.fixture(autouse=True)
def isolated_db(tmp_path, monkeypatch):
    """Redirect all db calls to a temp database for each test."""
    test_db = tmp_path / "test.db"
    db_module.init_db(test_db)
    monkeypatch.setattr(db_module, "_DEFAULT_DB", test_db)
    return test_db


def test_assess_high_risk_always_interrupts():
    result = assess_action("file_delete", "rm important.txt")
    assert result["should_interrupt"] is True
    assert result["risk_level"] == "high"


def test_assess_low_risk_no_history_proceeds():
    result = assess_action("file_read", "cat config.yaml")
    assert result["should_interrupt"] is False
    assert result["risk_level"] == "low"


def test_assess_medium_risk_no_history_interrupts():
    result = assess_action("file_write", "write to app.py")
    assert result["should_interrupt"] is True


def test_assess_medium_risk_high_approval_proceeds(isolated_db):
    for _ in range(10):
        db_module.record_decision("file_write", "write x", "approved", "medium", isolated_db)
    result = assess_action("file_write", "write something")
    assert result["should_interrupt"] is False
    assert result["approval_rate"] == 1.0


def test_assess_medium_risk_low_approval_interrupts(isolated_db):
    for _ in range(5):
        db_module.record_decision("file_write", "write x", "rejected", "medium", isolated_db)
    result = assess_action("file_write", "write something")
    assert result["should_interrupt"] is True


def test_record_decision_approved(isolated_db):
    result = record_decision("file_write", "write x", "approved", "medium")
    assert result["recorded"] is True
    assert db_module.get_approval_rate("file_write", isolated_db) == 1.0


def test_record_decision_rejected(isolated_db):
    result = record_decision("file_delete", "rm x", "rejected", "high")
    assert result["recorded"] is True
    assert db_module.get_approval_rate("file_delete", isolated_db) == 0.0


def test_record_decision_invalid_value():
    result = record_decision("file_write", "write x", "maybe", "medium")
    assert result["recorded"] is False
    assert "error" in result


def test_assess_returns_expected_keys():
    result = assess_action("bash_write", "run script")
    assert {"should_interrupt", "risk_level", "reversible", "approval_rate", "reason"} <= result.keys()
