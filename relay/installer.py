import json
import shutil
import sys
from pathlib import Path

_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"

# relay executable path resolved at install time via shutil.which or uvx
_HOOK_COMMAND = "relay"


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


def _relay_bin() -> str:
    """Return the command to invoke relay hook subcommands."""
    found = shutil.which("relay")
    if found:
        return found
    # Fallback: uvx invocation
    return "uvx --from git+https://github.com/solost23/relay relay"


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
    settings = _load_settings()

    bin_cmd = _relay_bin()

    pre_hook = {
        "type": "command",
        "command": f"{bin_cmd} hook pre",
        "timeout": 30,
        "statusMessage": "Relay: assessing action...",
    }

    post_hook = {
        "type": "command",
        "command": f"{bin_cmd} hook post",
        "timeout": 10,
    }

    hooks = settings.setdefault("hooks", {})

    # PreToolUse — match all tools
    pre_hooks = hooks.setdefault("PreToolUse", [])
    # Remove any existing relay entry
    hooks["PreToolUse"] = [h for h in pre_hooks if "relay" not in json.dumps(h)]
    hooks["PreToolUse"].append({"matcher": ".*", "hooks": [pre_hook]})

    # PostToolUse — match all tools
    post_hooks = hooks.setdefault("PostToolUse", [])
    hooks["PostToolUse"] = [h for h in post_hooks if "relay" not in json.dumps(h)]
    hooks["PostToolUse"].append({"matcher": ".*", "hooks": [post_hook]})

    # Set bypassPermissions so Claude Code doesn't double-prompt
    permissions = settings.setdefault("permissions", {})
    permissions["defaultMode"] = "bypassPermissions"

    _save_settings(settings)

    print("✓ Relay installed successfully.")
    print(f"  Settings updated: {_SETTINGS_PATH}")
    print("  PreToolUse and PostToolUse hooks registered.")
    print("  Permission mode set to bypassPermissions.")
    print()
    print("Restart Claude Code for changes to take effect.")


def uninstall() -> None:
    settings = _load_settings()
    hooks = settings.get("hooks", {})

    hooks["PreToolUse"] = [h for h in hooks.get("PreToolUse", []) if "relay" not in json.dumps(h)]
    hooks["PostToolUse"] = [h for h in hooks.get("PostToolUse", []) if "relay" not in json.dumps(h)]

    # Restore default permission mode
    permissions = settings.get("permissions", {})
    if permissions.get("defaultMode") == "bypassPermissions":
        del permissions["defaultMode"]

    _save_settings(settings)

    print("✓ Relay uninstalled.")
    print("Restart Claude Code for changes to take effect.")
