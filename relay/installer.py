import json
import subprocess
import sys
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


def _ensure_package_installed(python: str) -> None:
    """Ensure relay is importable from any working directory, not just the project root."""
    result = subprocess.run(
        [python, "-c", "import relay"],
        cwd="/",
        capture_output=True,
    )
    if result.returncode != 0:
        project_root = Path(__file__).parent.parent
        print("  Installing relay package into current environment...")
        # Try pip first, fall back to uv (some venvs ship without pip)
        pip_ok = subprocess.run(
            [python, "-m", "pip", "install", "-e", str(project_root)],
            capture_output=True,
        ).returncode == 0
        if not pip_ok:
            subprocess.run(
                ["uv", "pip", "install", "-e", str(project_root)],
                check=True,
            )


def install() -> None:
    # Use the current Python interpreter — same environment relay is already running in
    python = sys.executable

    _ensure_package_installed(python)

    settings = _load_settings()

    pre_hook = {
        "type": "command",
        "command": f"{python} -m relay hook pre",
        "timeout": 10,
        "statusMessage": "Relay: assessing action...",
    }

    post_hook = {
        "type": "command",
        "command": f"{python} -m relay hook post",
        "timeout": 5,
    }

    hooks = settings.setdefault("hooks", {})

    hooks["PreToolUse"] = [h for h in hooks.get("PreToolUse", []) if "relay" not in json.dumps(h)]
    hooks["PreToolUse"].append({"matcher": ".*", "hooks": [pre_hook]})

    hooks["PostToolUse"] = [h for h in hooks.get("PostToolUse", []) if "relay" not in json.dumps(h)]
    hooks["PostToolUse"].append({"matcher": ".*", "hooks": [post_hook]})

    _save_settings(settings)

    print("✓ Relay installed successfully.")
    print(f"  Python: {python}")
    print(f"  Settings: {_SETTINGS_PATH}")
    print()
    print("Restart Claude Code for changes to take effect.")


def uninstall() -> None:
    settings = _load_settings()
    hooks = settings.get("hooks", {})

    hooks["PreToolUse"] = [h for h in hooks.get("PreToolUse", []) if "relay" not in json.dumps(h)]
    hooks["PostToolUse"] = [h for h in hooks.get("PostToolUse", []) if "relay" not in json.dumps(h)]

    _save_settings(settings)

    print("✓ Relay uninstalled.")
    print("Restart Claude Code for changes to take effect.")
