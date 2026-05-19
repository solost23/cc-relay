import pytest
from unittest.mock import patch
from cc_relay.hook import handle_pre_tool_use, handle_post_tool_use, handle_stop, _file_action_type, _bash_action_type


def _pre(tool_name, tool_input=None):
    return handle_pre_tool_use({"tool_name": tool_name, "tool_input": tool_input or {}})


def _post(tool_name, tool_input=None):
    return handle_post_tool_use({"tool_name": tool_name, "tool_input": tool_input or {}})


def _decision(result):
    return result.get("hookSpecificOutput", {}).get("permissionDecision")


# --- file action type classification ---

def test_file_action_type_system():
    assert _file_action_type("/etc/hosts") == "file_write:system"
    assert _file_action_type("/usr/local/bin/foo") == "file_write:system"

def test_file_action_type_config():
    assert _file_action_type("/home/user/.env") == "file_write:config"
    assert _file_action_type("pyproject.toml") == "file_write:config"
    assert _file_action_type("config.yaml") == "file_write:config"

def test_file_action_type_code():
    assert _file_action_type("relay/hook.py") == "file_write:code"
    assert _file_action_type("README.md") == "file_write:code"


# --- bash action type classification ---

def test_bash_action_type_git():
    assert _bash_action_type("git commit -m 'fix'") == "bash_write:git"
    assert _bash_action_type("git push origin master") == "bash_write:git"

def test_bash_action_type_package_manager():
    assert _bash_action_type("uv add requests") == "bash_write:package_manager"
    assert _bash_action_type("npm install lodash") == "bash_write:package_manager"

def test_bash_action_type_shell():
    assert _bash_action_type("mv foo bar") == "bash_write:shell"
    assert _bash_action_type("chmod +x script.sh") == "bash_write:shell"

def test_bash_action_type_delete():
    assert _bash_action_type("rm -rf /tmp/foo") == "file_delete"

def test_bash_action_type_read():
    assert _bash_action_type("git status") == "bash_read"
    assert _bash_action_type("ls -la") == "bash_read"

def test_bash_action_type_echo_is_not_read():
    # echo can redirect to files — must not be classified as read
    assert _bash_action_type("echo hello > file.txt") != "bash_read"
    assert _bash_action_type("echo hello") != "bash_read"


# --- always-allow tools ---

def test_always_allow_tools_pass_through():
    for tool in ("Read", "Glob", "Grep", "WebSearch", "AskUserQuestion"):
        result = _pre(tool, {"file_path": "/tmp/x"})
        assert _decision(result) == "allow", f"{tool} should always be allowed"


def test_always_allow_post_returns_empty():
    assert _post("Read", {"file_path": "/tmp/x"}) == {}


# --- auto-approve path ---

def test_auto_approved_action_returns_allow():
    with patch("cc_relay.hook._should_interrupt", return_value=(False, "auto")), \
         patch("cc_relay.hook._db.record_decision") as mock_record, \
         patch("cc_relay.hook.assess_risk", return_value={"risk_level": "low", "reversible": True, "reason": ""}):
        result = _pre("Bash", {"command": "git status"})
        assert _decision(result) == "allow"
        mock_record.assert_called_once()


def test_auto_approved_post_does_not_double_record():
    with patch("cc_relay.hook._should_interrupt", return_value=(False, "auto")), \
         patch("cc_relay.hook._db.record_decision") as mock_record:
        result = _post("Bash", {"command": "git status"})
        assert result == {}
        mock_record.assert_not_called()


# --- interrupt path ---

def test_interrupt_returns_ask():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("cc_relay.hook._db.add_pending"), \
         patch("cc_relay.hook.send_notification"):
        result = _pre("Bash", {"command": "rm -rf /"})
        assert _decision(result) == "ask"


def test_interrupt_includes_reason():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "dangerous op")), \
         patch("cc_relay.hook._db.add_pending"), \
         patch("cc_relay.hook.send_notification"):
        result = _pre("Bash", {"command": "rm -rf /"})
        reason = result["hookSpecificOutput"].get("permissionDecisionReason")
        assert reason == "dangerous op"


def test_interrupt_fires_notification():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("cc_relay.hook._db.add_pending"), \
         patch("cc_relay.hook.send_notification") as mock_notify:
        _pre("Write", {"file_path": "/etc/hosts"})
        mock_notify.assert_called_once()


def test_interrupt_writes_pending():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("cc_relay.hook._db.add_pending") as mock_pending, \
         patch("cc_relay.hook.assess_risk", return_value={"risk_level": "high", "reversible": False, "reason": ""}), \
         patch("cc_relay.hook.send_notification"):
        _pre("Bash", {"command": "rm -rf /"})
        mock_pending.assert_called_once_with("file_delete", "rm -rf /", "high")


def test_post_resolves_pending_when_tool_ran():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("cc_relay.hook._db.resolve_pending") as mock_resolve:
        result = _post("Bash", {"command": "rm -rf /"})
        assert result == {}
        mock_resolve.assert_called_once_with("file_delete", "rm -rf /")


# --- stop hook ---

def test_stop_flushes_pending():
    with patch("cc_relay.hook._db.flush_pending_as_rejected") as mock_flush:
        handle_stop({})
        mock_flush.assert_called_once()

