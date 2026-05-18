import json

import pytest

import cc_relay.installer as installer_module
from cc_relay.installer import ensure_installed, install, is_installed, uninstall


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(installer_module, "_SETTINGS_PATH", path)
    return path


def test_is_installed_false_when_no_settings(settings_file):
    assert is_installed() is False


def test_install_writes_versioned_hooks(settings_file):
    install()
    data = json.loads(settings_file.read_text())
    pre_hooks = json.dumps(data["hooks"]["PreToolUse"])
    post_hooks = json.dumps(data["hooks"]["PostToolUse"])
    from importlib.metadata import version
    ver = version("relay")
    assert f"relay=={ver}" in pre_hooks
    assert f"relay=={ver}" in post_hooks


def test_is_installed_true_after_install(settings_file):
    install()
    assert is_installed() is True


def test_is_installed_false_for_different_version(settings_file):
    # Simulate a hook written by an older version
    settings_file.write_text(json.dumps({
        "hooks": {
            "PreToolUse": [{"matcher": ".*", "hooks": [{"command": "uvx relay==0.0.1 hook pre"}]}]
        }
    }))
    assert is_installed() is False


def test_ensure_installed_upgrades_stale_version(settings_file):
    # Write a hook with a fake old version
    settings_file.write_text(json.dumps({
        "hooks": {
            "PreToolUse": [{"matcher": ".*", "hooks": [{"command": "uvx relay==0.0.1 hook pre"}]}],
            "PostToolUse": [],
        }
    }))
    ensure_installed()
    from importlib.metadata import version
    ver = version("relay")
    data = json.loads(settings_file.read_text())
    pre_hooks = json.dumps(data["hooks"]["PreToolUse"])
    assert f"relay=={ver}" in pre_hooks
    assert "relay==0.0.1" not in pre_hooks


def test_uninstall_removes_hooks(settings_file):
    install()
    uninstall()
    data = json.loads(settings_file.read_text())
    assert data["hooks"]["PreToolUse"] == []
    assert data["hooks"]["PostToolUse"] == []
