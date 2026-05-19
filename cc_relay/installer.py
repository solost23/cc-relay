import json
from importlib.metadata import version
from pathlib import Path

_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"


def _load_settings() -> dict:
    if _SETTINGS_PATH.exists():
        try:
            return json.loads(_SETTINGS_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_settings(settings: dict) -> None:
    _SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SETTINGS_PATH.write_text(json.dumps(settings, indent=2) + "\n")


def is_installed() -> bool:
    """Check if relay hooks are registered at the current version (PreToolUse + Stop)."""
    ver = version("cc-relay")
    settings = _load_settings()
    hooks = settings.get("hooks", {})
    pre_ok = any(f"cc-relay=={ver}" in json.dumps(h) for h in hooks.get("PreToolUse", []))
    stop_ok = any(f"cc-relay=={ver}" in json.dumps(h) for h in hooks.get("Stop", []))
    return pre_ok and stop_ok


def ensure_installed() -> None:
    """Install (or upgrade) hooks if missing or version has changed. Safe to call on every startup."""
    if not is_installed():
        install()


def install() -> None:
    settings = _load_settings()

    ver = version("cc-relay")
    pre_hook = {
        "type": "command",
        "command": f"uvx cc-relay=={ver} hook pre",
        "timeout": 10,
        "statusMessage": "Relay: assessing action...",
    }

    post_hook = {
        "type": "command",
        "command": f"uvx cc-relay=={ver} hook post",
        "timeout": 5,
    }

    stop_hook = {
        "type": "command",
        "command": f"uvx cc-relay=={ver} hook stop",
        "timeout": 5,
    }

    hooks = settings.setdefault("hooks", {})

    hooks["PreToolUse"] = [h for h in hooks.get("PreToolUse", []) if "relay" not in json.dumps(h)]
    hooks["PreToolUse"].append({"matcher": ".*", "hooks": [pre_hook]})

    hooks["PostToolUse"] = [h for h in hooks.get("PostToolUse", []) if "relay" not in json.dumps(h)]
    hooks["PostToolUse"].append({"matcher": ".*", "hooks": [post_hook]})

    hooks["Stop"] = [h for h in hooks.get("Stop", []) if "relay" not in json.dumps(h)]
    hooks["Stop"].append({"hooks": [stop_hook]})

    _save_settings(settings)

    print("✓ Relay installed successfully.")
    print(f"  Version: {ver}")
    print(f"  Settings: {_SETTINGS_PATH}")
    print()
    print("Restart Claude Code for changes to take effect.")


def uninstall() -> None:
    settings = _load_settings()
    hooks = settings.get("hooks", {})

    hooks["PreToolUse"] = [h for h in hooks.get("PreToolUse", []) if "relay" not in json.dumps(h)]
    hooks["PostToolUse"] = [h for h in hooks.get("PostToolUse", []) if "relay" not in json.dumps(h)]
    hooks["Stop"] = [h for h in hooks.get("Stop", []) if "relay" not in json.dumps(h)]

    _save_settings(settings)

    print("✓ Relay uninstalled.")
    print("Restart Claude Code for changes to take effect.")
