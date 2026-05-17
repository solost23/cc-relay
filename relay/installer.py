import json
import shutil
import subprocess
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


def _install_relay_tool() -> str:
    """
    Ensure relay is installed as a local uv tool and return its binary path.
    Uses `uv tool install` so the binary lives at ~/.local/bin/relay (or equivalent).
    """
    # Check if already installed locally
    found = shutil.which("relay")
    if found:
        return found

    print("  Installing relay as a local tool via uv...")
    subprocess.run(
        ["uv", "tool", "install", "git+https://github.com/solost23/relay"],
        check=True,
    )

    found = shutil.which("relay")
    if found:
        return found

    # Explicit fallback path
    fallback = Path.home() / ".local" / "bin" / "relay"
    if fallback.exists():
        return str(fallback)

    raise RuntimeError("relay binary not found after uv tool install")


def is_installed() -> bool:
    """Check if relay hooks are already registered in settings.json."""
    settings = _load_settings()
    for hook_list in settings.get("hooks", {}).get("PreToolUse", []):
        if "relay" in json.dumps(hook_list):
            return True
    return False


def ensure_installed() -> None:
    """Install only if not already installed. Safe to call on every startup."""
    if not is_installed():
        install()


def install() -> None:
    bin_path = _install_relay_tool()
    settings = _load_settings()

    pre_hook = {
        "type": "command",
        "command": f"{bin_path} hook pre",
        "timeout": 10,
        "statusMessage": "Relay: assessing action...",
    }

    post_hook = {
        "type": "command",
        "command": f"{bin_path} hook post",
        "timeout": 5,
    }

    hooks = settings.setdefault("hooks", {})

    hooks["PreToolUse"] = [h for h in hooks.get("PreToolUse", []) if "relay" not in json.dumps(h)]
    hooks["PreToolUse"].append({"matcher": ".*", "hooks": [pre_hook]})

    hooks["PostToolUse"] = [h for h in hooks.get("PostToolUse", []) if "relay" not in json.dumps(h)]
    hooks["PostToolUse"].append({"matcher": ".*", "hooks": [post_hook]})

    permissions = settings.setdefault("permissions", {})
    permissions["defaultMode"] = "bypassPermissions"

    _save_settings(settings)

    print("✓ Relay installed successfully.")
    print(f"  Binary: {bin_path}")
    print(f"  Settings: {_SETTINGS_PATH}")
    print()
    print("Restart Claude Code for changes to take effect.")


def uninstall() -> None:
    settings = _load_settings()
    hooks = settings.get("hooks", {})

    hooks["PreToolUse"] = [h for h in hooks.get("PreToolUse", []) if "relay" not in json.dumps(h)]
    hooks["PostToolUse"] = [h for h in hooks.get("PostToolUse", []) if "relay" not in json.dumps(h)]

    permissions = settings.get("permissions", {})
    if permissions.get("defaultMode") == "bypassPermissions":
        del permissions["defaultMode"]

    _save_settings(settings)

    print("✓ Relay uninstalled.")
    print("Restart Claude Code for changes to take effect.")
