import pytest
from unittest.mock import patch, MagicMock
from relay.hook import handle_pre_tool_use, handle_post_tool_use


def _pre(tool_name, tool_input=None):
    return handle_pre_tool_use({"tool_name": tool_name, "tool_input": tool_input or {}})


def _post(tool_name, tool_input=None):
    return handle_post_tool_use({"tool_name": tool_name, "tool_input": tool_input or {}})


def _decision(result):
    return result.get("hookSpecificOutput", {}).get("permissionDecision")


# --- always-allow tools ---

def test_always_allow_tools_pass_through():
    for tool in ("Read", "Glob", "Grep", "WebSearch", "AskUserQuestion"):
        result = _pre(tool, {"file_path": "/tmp/x"})
        assert _decision(result) == "allow", f"{tool} should always be allowed"


def test_always_allow_post_returns_empty():
    assert _post("Read", {"file_path": "/tmp/x"}) == {}


# --- auto-approve path (no interrupt) ---

def test_auto_approved_action_returns_allow():
    with patch("relay.hook._should_interrupt", return_value=(False, "auto")), \
         patch("relay.hook._db.record_decision") as mock_record, \
         patch("relay.hook.assess_risk", return_value={"risk_level": "low", "reversible": True, "reason": ""}):
        result = _pre("Bash", {"command": "git status"})
        assert _decision(result) == "allow"
        mock_record.assert_called_once()


def test_auto_approved_post_does_not_double_record():
    with patch("relay.hook._should_interrupt", return_value=(False, "auto")), \
         patch("relay.hook._db.record_decision") as mock_record:
        result = _post("Bash", {"command": "git status"})
        assert result == {}
        mock_record.assert_not_called()


# --- interrupt path ---

def test_interrupt_returns_ask():
    with patch("relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("relay.hook.send_notification"):
        result = _pre("Bash", {"command": "rm -rf /"})
        assert _decision(result) == "ask"


def test_interrupt_includes_reason():
    with patch("relay.hook._should_interrupt", return_value=(True, "dangerous op")), \
         patch("relay.hook.send_notification"):
        result = _pre("Bash", {"command": "rm -rf /"})
        reason = result["hookSpecificOutput"].get("permissionDecisionReason")
        assert reason == "dangerous op"


def test_interrupt_fires_notification():
    with patch("relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("relay.hook.send_notification") as mock_notify:
        _pre("Write", {"file_path": "/etc/hosts"})
        mock_notify.assert_called_once()


def test_post_records_when_interrupted_and_tool_ran():
    with patch("relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("relay.hook._db.record_decision") as mock_record, \
         patch("relay.hook.assess_risk", return_value={"risk_level": "high", "reversible": False, "reason": ""}):
        result = _post("Bash", {"command": "rm -rf /"})
        assert result == {}
        mock_record.assert_called_once_with(
            "file_delete", "rm -rf /", "approved", "high"
        )
