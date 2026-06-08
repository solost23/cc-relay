from unittest.mock import patch

from cc_relay.notifier import send_completion_notification, send_notification


def test_interrupt_notification_uses_codex_title_on_macos():
    strings = {
        "title": "Relay: 需要你的确认",
        "suffix": "\n\n请返回终端进行操作。",
    }
    with patch("cc_relay.notifier._t", return_value=strings), \
         patch("cc_relay.notifier.platform.system", return_value="Darwin"), \
         patch("cc_relay.notifier.subprocess.Popen") as mock_popen:
        assert send_notification("Bash: rm -rf /", client="codex") is True

    script = mock_popen.call_args.args[0][-1]
    assert "Relay: 需要你的确认 (Codex)" in script


def test_completion_notification_uses_codex_title_on_macos():
    with patch("cc_relay.notifier._t", return_value={"done_title": "Claude 已完成", "done_msg": "任务已完成"}), \
         patch("cc_relay.notifier.platform.system", return_value="Darwin"), \
         patch("cc_relay.notifier.subprocess.Popen") as mock_popen:
        assert send_completion_notification("codex") is True

    script = mock_popen.call_args.args[0][-1]
    assert "Codex 已完成" in script
    assert "Claude 已完成" not in script


def test_completion_notification_defaults_to_claude_title_on_macos():
    with patch("cc_relay.notifier._t", return_value={"done_title": "Claude 已完成", "done_msg": "任务已完成"}), \
         patch("cc_relay.notifier.platform.system", return_value="Darwin"), \
         patch("cc_relay.notifier.subprocess.Popen") as mock_popen:
        assert send_completion_notification() is True

    script = mock_popen.call_args.args[0][-1]
    assert "Claude 已完成" in script
