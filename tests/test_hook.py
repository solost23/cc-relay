import io

import pytest
from unittest.mock import patch
from cc_relay.hook import (
    handle_pre_tool_use, handle_post_tool_use, handle_stop, run_post_tool_use,
    run_pre_tool_use, run_stop, _file_action_type, _bash_action_type,
)
import cc_relay.db as db_module


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

def test_bash_action_type_force_push():
    assert _bash_action_type("git push --force") == "git_force_push"
    assert _bash_action_type("git push -f") == "git_force_push"
    assert _bash_action_type("git push origin --force") == "git_force_push"

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

def test_bash_action_type_chained_escalates_to_highest_risk():
    # safe prefix followed by dangerous segment → must return the dangerous type
    assert _bash_action_type("uv run pytest && rm -rf dist") == "file_delete"
    assert _bash_action_type("git status && git push --force") == "git_force_push"
    assert _bash_action_type("ls -la; git commit -m 'x'") == "bash_write:git"

def test_bash_action_type_pipe_does_not_downgrade():
    # piped read commands stay read
    assert _bash_action_type("git log | grep fix") == "bash_read"

def test_bash_action_type_multiline_escalates():
    assert _bash_action_type("git status\nrm -rf /tmp/foo") == "file_delete"


def test_codex_command_tool_uses_cmd_field():
    with patch("cc_relay.hook._should_interrupt", return_value=(False, "auto")), \
         patch("cc_relay.hook._db.record_decision") as mock_record, \
         patch("cc_relay.hook.assess_risk", return_value={"risk_level": "low", "reversible": True, "reason": ""}):
        result = handle_pre_tool_use(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "exec_command",
                "tool_input": {"cmd": "git status"},
            },
            "codex",
        )
        assert result == {}
        assert mock_record.call_args.args[0] == "bash_read"


def test_codex_apply_patch_delete_is_file_delete():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "delete")), \
         patch("cc_relay.hook._db.record_decision") as mock_record, \
         patch("cc_relay.hook.send_notification"):
        handle_pre_tool_use(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch",
                "tool_input": {"patch": "*** Delete File: old.py\n"},
            },
            "codex",
        )
        assert mock_record.call_args.args[0] == "file_delete"


def test_codex_apply_patch_without_payload_is_unknown_patch():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "unknown patch")), \
         patch("cc_relay.hook._db.record_decision") as mock_record, \
         patch("cc_relay.hook.assess_risk", return_value={"risk_level": "high", "reversible": False, "reason": ""}), \
         patch("cc_relay.hook.send_notification"):
        result = handle_pre_tool_use(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "apply_patch",
                "tool_input": {},
            },
            "codex",
        )
        assert result["decision"] == "block"
        assert result["reason"].startswith("unknown patch")
        assert "Stop and wait for the user" in result["reason"]
        mock_record.assert_called_once_with(
            "file_patch:unknown",
            "apply_patch with unavailable patch contents",
            "rejected",
            "high",
        )


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
    with patch("cc_relay.hook._db.record_decision") as mock_record, \
         patch("cc_relay.hook._db.approve_latest_rejected"):
        result = _post("Bash", {"command": "git status"})
        assert result == {}
        mock_record.assert_not_called()


def test_post_always_attempts_approve():
    with patch("cc_relay.hook._db.approve_latest_rejected") as mock_approve:
        _post("Bash", {"command": "git status"})
        mock_approve.assert_called_once_with("bash_read", "git status")


# --- interrupt path ---

def test_interrupt_returns_ask():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("cc_relay.hook._db.record_decision"), \
         patch("cc_relay.hook.send_notification"):
        result = _pre("Bash", {"command": "rm -rf /"})
        assert _decision(result) == "ask"


def test_hook_event_name_does_not_override_default_claude_client():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("cc_relay.hook._db.record_decision"), \
         patch("cc_relay.hook.send_notification") as mock_notify:
        result = handle_pre_tool_use(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "rm -rf /"},
            }
        )

    assert _decision(result) == "ask"
    mock_notify.assert_called_once_with(message="Bash: rm -rf /", client="claude")


def test_codex_auto_approved_action_returns_empty_allow():
    with patch("cc_relay.hook._should_interrupt", return_value=(False, "auto")), \
         patch("cc_relay.hook._db.record_decision"), \
         patch("cc_relay.hook.assess_risk", return_value={"risk_level": "low", "reversible": True, "reason": ""}):
        result = handle_pre_tool_use(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "git status"},
            },
            "codex",
        )
        assert result == {}


def test_codex_interrupt_returns_block():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("cc_relay.hook._db.record_decision"), \
         patch("cc_relay.hook.send_notification") as mock_notify:
        result = handle_pre_tool_use(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "rm -rf /"},
            },
            "codex",
        )
        assert result["decision"] == "block"
        assert result["reason"].startswith("high risk")
        assert "Stop and wait for the user" in result["reason"]
        mock_notify.assert_called_once_with(message="Bash: rm -rf /", client="codex")


def test_codex_interrupt_reports_notification_failure():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("cc_relay.hook._db.record_decision"), \
         patch("cc_relay.hook.send_notification", return_value=False):
        result = handle_pre_tool_use(
            {
                "hook_event_name": "PreToolUse",
                "tool_name": "Bash",
                "tool_input": {"command": "rm -rf /"},
            },
            "codex",
        )

    assert result["decision"] == "block"
    assert "could not deliver the desktop notification" in result["reason"]
    assert "Stop and wait for the user" in result["reason"]


def test_codex_retried_blocked_action_is_approved(tmp_path, monkeypatch):
    test_db = tmp_path / "test.db"
    db_module.init_db(test_db)
    monkeypatch.setattr(db_module, "_DEFAULT_DB", test_db)

    payload = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m 'x'"},
    }

    with patch("cc_relay.hook.send_notification"):
        first = handle_pre_tool_use(payload, "codex")
        second = handle_pre_tool_use(payload, "codex")

    assert first["decision"] == "block"
    assert "retry it once" in first["reason"]
    assert second == {}
    assert db_module.get_approval_rate("bash_write:git") == 1.0


def test_interrupt_includes_reason():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "dangerous op")), \
         patch("cc_relay.hook._db.record_decision"), \
         patch("cc_relay.hook.send_notification"):
        result = _pre("Bash", {"command": "rm -rf /"})
        reason = result["hookSpecificOutput"].get("permissionDecisionReason")
        assert reason == "dangerous op"


def test_interrupt_fires_notification():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("cc_relay.hook._db.record_decision"), \
         patch("cc_relay.hook.send_notification") as mock_notify:
        _pre("Write", {"file_path": "/etc/hosts"})
        mock_notify.assert_called_once()


def test_interrupt_writes_rejected():
    with patch("cc_relay.hook._should_interrupt", return_value=(True, "high risk")), \
         patch("cc_relay.hook._db.record_decision") as mock_record, \
         patch("cc_relay.hook.assess_risk", return_value={"risk_level": "high", "reversible": False, "reason": ""}), \
         patch("cc_relay.hook.send_notification"):
        _pre("Bash", {"command": "rm -rf /"})
        mock_record.assert_called_once_with("file_delete", "rm -rf /", "rejected", "high")


def test_post_approves_latest_rejected_when_tool_ran():
    with patch("cc_relay.hook._db.approve_latest_rejected") as mock_approve:
        result = _post("Bash", {"command": "rm -rf /"})
        assert result == {}
        mock_approve.assert_called_once_with("file_delete", "rm -rf /")


# --- stop hook ---

def test_stop_notifies_default_claude():
    with patch("cc_relay.hook.send_completion_notification") as mock_notify:
        result = handle_stop({})
        assert result == {}
        mock_notify.assert_called_once_with("claude")


def test_stop_notifies_codex_client():
    with patch("cc_relay.hook.send_completion_notification") as mock_notify:
        result = handle_stop({}, "codex")
        assert result == {}
        mock_notify.assert_called_once_with("codex")


def test_hook_runners_tolerate_empty_stdin(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with patch("cc_relay.hook.handle_pre_tool_use", return_value={}):
        run_pre_tool_use("codex")

    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with patch("cc_relay.hook.handle_post_tool_use", return_value={}):
        run_post_tool_use()

    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    with patch("cc_relay.hook.handle_stop", return_value={}) as mock_stop:
        run_stop("codex")
        mock_stop.assert_called_once_with({}, "codex")


def test_hook_runners_tolerate_invalid_json(monkeypatch):
    monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
    with patch("cc_relay.hook.handle_pre_tool_use", return_value={}):
        run_pre_tool_use("codex")
