import json
import tomllib

import pytest

import cc_relay.installer as installer_module
from cc_relay.installer import (
    ensure_all_installed, ensure_installed, install, install_codex,
    is_codex_installed, is_installed, uninstall, uninstall_codex,
)


@pytest.fixture
def settings_file(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(installer_module, "_SETTINGS_PATH", path)
    return path


@pytest.fixture
def codex_config_file(tmp_path, monkeypatch):
    path = tmp_path / ".codex" / "config.toml"
    monkeypatch.setattr(installer_module, "_CODEX_CONFIG_PATH", path)
    return path


def test_is_installed_false_when_no_settings(settings_file):
    assert is_installed() is False


def test_install_writes_versioned_hooks(settings_file):
    install()
    data = json.loads(settings_file.read_text())
    pre_hooks = json.dumps(data["hooks"]["PreToolUse"])
    post_hooks = json.dumps(data["hooks"]["PostToolUse"])
    from importlib.metadata import version
    ver = version("cc-relay")
    assert f"cc-relay=={ver}" in pre_hooks
    assert f"cc-relay=={ver}" in post_hooks
    assert "--client claude" in pre_hooks
    assert "--client claude" in post_hooks


def test_is_installed_true_after_install(settings_file):
    install()
    assert is_installed() is True


def test_is_installed_false_for_missing_claude_client_arg(settings_file):
    from importlib.metadata import version
    ver = version("cc-relay")
    settings_file.write_text(json.dumps({
        "hooks": {
            "PreToolUse": [{"matcher": ".*", "hooks": [{"command": f"uvx cc-relay=={ver} hook pre"}]}],
            "Stop": [{"hooks": [{"command": f"uvx cc-relay=={ver} hook stop"}]}],
        }
    }))
    assert is_installed() is False


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
    ver = version("cc-relay")
    data = json.loads(settings_file.read_text())
    pre_hooks = json.dumps(data["hooks"]["PreToolUse"])
    assert f"cc-relay=={ver}" in pre_hooks
    assert "relay==0.0.1" not in pre_hooks


def test_ensure_all_installed_writes_claude_and_codex(settings_file, codex_config_file):
    ensure_all_installed()
    assert is_installed() is True
    assert is_codex_installed() is True
    assert settings_file.exists()
    assert codex_config_file.exists()


def test_uninstall_removes_hooks(settings_file):
    install()
    uninstall()
    data = json.loads(settings_file.read_text())
    assert data["hooks"]["PreToolUse"] == []
    assert data["hooks"]["PostToolUse"] == []


def test_install_codex_writes_global_config_hooks(codex_config_file):
    install_codex()
    data = tomllib.loads(codex_config_file.read_text())
    pre_hooks = json.dumps(data["hooks"]["PreToolUse"])
    post_hooks = json.dumps(data["hooks"]["PostToolUse"])
    from importlib.metadata import version
    ver = version("cc-relay")
    assert f"cc-relay=={ver}" in pre_hooks
    assert "--client codex" in pre_hooks
    assert "--client codex" in post_hooks


def test_is_codex_installed_true_after_install(codex_config_file):
    install_codex()
    assert is_codex_installed() is True


def test_uninstall_codex_removes_hooks(codex_config_file):
    install_codex()
    uninstall_codex()
    data = tomllib.loads(codex_config_file.read_text())
    assert data["hooks"].get("PreToolUse", []) == []
    assert data["hooks"].get("PostToolUse", []) == []


def test_install_codex_preserves_hook_state(codex_config_file):
    codex_config_file.parent.mkdir(parents=True)
    codex_config_file.write_text(
        '[hooks.state."/repo/.codex/hooks.json:pre_tool_use:0:0"]\n'
        'trusted_hash = "sha256:test"\n'
    )
    install_codex()
    data = tomllib.loads(codex_config_file.read_text())
    state = data["hooks"]["state"]["/repo/.codex/hooks.json:pre_tool_use:0:0"]
    assert state["trusted_hash"] == "sha256:test"
