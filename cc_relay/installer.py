import json
import tomllib
from importlib.metadata import version
from pathlib import Path

_SETTINGS_PATH = Path.home() / ".claude" / "settings.json"
_CODEX_CONFIG_PATH = Path.home() / ".codex" / "config.toml"
_HOOK_EVENTS = ("PreToolUse", "PostToolUse", "Stop")


def _load_json(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def _save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def _load_settings() -> dict:
    return _load_json(_SETTINGS_PATH)


def _save_settings(settings: dict) -> None:
    _save_json(_SETTINGS_PATH, settings)


def _load_toml(path: Path) -> dict:
    if path.exists():
        try:
            return tomllib.loads(path.read_text())
        except tomllib.TOMLDecodeError:
            return {}
    return {}


def _toml_value(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    if isinstance(value, dict):
        return _toml_inline_table(value)
    raise TypeError(f"Unsupported TOML value: {type(value)!r}")


def _toml_inline_table(table: dict) -> str:
    preferred = ("type", "command", "timeout", "statusMessage", "matcher", "hooks")
    keys = [k for k in preferred if k in table] + [k for k in table if k not in preferred]
    return "{ " + ", ".join(f"{key} = {_toml_value(table[key])}" for key in keys) + " }"


def _format_hooks_section(hooks: dict) -> str:
    lines = ["[hooks]"]
    for event in _HOOK_EVENTS:
        entries = hooks.get(event, [])
        if not entries:
            continue
        lines.append(f"{event} = [")
        for entry in entries:
            lines.append(f"  {_toml_inline_table(entry)},")
        lines.append("]")
    return "\n".join(lines) + "\n"


def _root_hooks_from_config(data: dict) -> dict:
    hooks = data.get("hooks", {})
    return {key: value for key, value in hooks.items() if key != "state"}


def _write_codex_config_hooks(hooks: dict) -> None:
    _CODEX_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = _CODEX_CONFIG_PATH.read_text() if _CODEX_CONFIG_PATH.exists() else ""
    hook_section = _format_hooks_section(hooks)
    lines = text.splitlines()

    start = next((i for i, line in enumerate(lines) if line.strip() == "[hooks]"), None)
    if start is not None:
        end = start + 1
        while end < len(lines) and not lines[end].lstrip().startswith("["):
            end += 1
        lines[start:end] = hook_section.rstrip().splitlines()
        _CODEX_CONFIG_PATH.write_text("\n".join(lines).rstrip() + "\n")
        return

    insert_at = next((i for i, line in enumerate(lines) if line.strip().startswith("[hooks.")), None)
    if insert_at is not None:
        lines[insert_at:insert_at] = hook_section.rstrip().splitlines() + [""]
        _CODEX_CONFIG_PATH.write_text("\n".join(lines).rstrip() + "\n")
        return

    prefix = text.rstrip()
    if prefix:
        _CODEX_CONFIG_PATH.write_text(prefix + "\n\n" + hook_section)
    else:
        _CODEX_CONFIG_PATH.write_text(hook_section)


def _relay_hook(subcommand: str, timeout: int, client: str = "claude") -> dict:
    ver = version("cc-relay")
    hook = {
        "type": "command",
        "command": f"uvx cc-relay=={ver} hook {subcommand} --client {client}",
        "timeout": timeout,
    }
    if subcommand == "pre":
        hook["statusMessage"] = "Relay: assessing action..."
    return hook


def _remove_relay_hooks(entries: list) -> list:
    def is_relay_hook(entry: dict) -> bool:
        raw = json.dumps(entry)
        return "cc-relay" in raw or "uvx relay==" in raw

    return [h for h in entries if not is_relay_hook(h)]


def is_installed() -> bool:
    """Check if relay hooks are registered at the current version and relay is first in PreToolUse."""
    ver = version("cc-relay")
    settings = _load_settings()
    hooks = settings.get("hooks", {})
    pre = hooks.get("PreToolUse", [])
    pre_first = bool(pre) and f"cc-relay=={ver}" in json.dumps(pre[0]) and "--client claude" in json.dumps(pre[0])
    stop_ok = any(f"cc-relay=={ver}" in json.dumps(h) and "--client claude" in json.dumps(h) for h in hooks.get("Stop", []))
    return pre_first and stop_ok


def ensure_installed() -> None:
    """Install (or upgrade) hooks if missing or version has changed. Safe to call on every startup."""
    if not is_installed():
        install()


def ensure_all_installed() -> None:
    """Install (or upgrade) Claude Code and Codex hooks if missing."""
    if not is_installed():
        install()
    if not is_codex_installed():
        install_codex()


def install() -> None:
    settings = _load_settings()

    ver = version("cc-relay")
    pre_hook = _relay_hook("pre", 10)
    post_hook = _relay_hook("post", 5)
    stop_hook = _relay_hook("stop", 5)

    hooks = settings.setdefault("hooks", {})

    hooks["PreToolUse"] = _remove_relay_hooks(hooks.get("PreToolUse", []))
    hooks["PreToolUse"].insert(0, {"matcher": ".*", "hooks": [pre_hook]})

    hooks["PostToolUse"] = _remove_relay_hooks(hooks.get("PostToolUse", []))
    hooks["PostToolUse"].append({"matcher": ".*", "hooks": [post_hook]})

    hooks["Stop"] = _remove_relay_hooks(hooks.get("Stop", []))
    hooks["Stop"].append({"hooks": [stop_hook]})

    _save_settings(settings)

    print("✓ Relay installed successfully.")
    print(f"  Version: {ver}")
    print(f"  Settings: {_SETTINGS_PATH}")
    print()
    print("Restart Claude Code for changes to take effect.")


def is_codex_installed() -> bool:
    """Check if relay hooks are registered in the user-level Codex config."""
    ver = version("cc-relay")
    hooks = _root_hooks_from_config(_load_toml(_CODEX_CONFIG_PATH))
    pre = hooks.get("PreToolUse", [])
    pre_first = bool(pre) and f"cc-relay=={ver}" in json.dumps(pre[0]) and "--client codex" in json.dumps(pre[0])
    stop_ok = any(f"cc-relay=={ver}" in json.dumps(h) and "--client codex" in json.dumps(h) for h in hooks.get("Stop", []))
    return pre_first and stop_ok


def install_codex() -> None:
    hooks = _root_hooks_from_config(_load_toml(_CODEX_CONFIG_PATH))

    ver = version("cc-relay")
    pre_hook = _relay_hook("pre", 10, "codex")
    post_hook = _relay_hook("post", 5, "codex")
    stop_hook = _relay_hook("stop", 5, "codex")

    hooks["PreToolUse"] = _remove_relay_hooks(hooks.get("PreToolUse", []))
    hooks["PreToolUse"].insert(0, {"matcher": ".*", "hooks": [pre_hook]})

    hooks["PostToolUse"] = _remove_relay_hooks(hooks.get("PostToolUse", []))
    hooks["PostToolUse"].append({"matcher": ".*", "hooks": [post_hook]})

    hooks["Stop"] = _remove_relay_hooks(hooks.get("Stop", []))
    hooks["Stop"].append({"hooks": [stop_hook]})

    _write_codex_config_hooks(hooks)

    print("✓ Relay installed globally for Codex.")
    print(f"  Version: {ver}")
    print(f"  Config: {_CODEX_CONFIG_PATH}")
    print()
    print("Restart Codex and review/trust the new user-level hooks when prompted.")


def install_all() -> None:
    install()
    print()
    install_codex()


def uninstall() -> None:
    settings = _load_settings()
    hooks = settings.get("hooks", {})

    hooks["PreToolUse"] = _remove_relay_hooks(hooks.get("PreToolUse", []))
    hooks["PostToolUse"] = _remove_relay_hooks(hooks.get("PostToolUse", []))
    hooks["Stop"] = _remove_relay_hooks(hooks.get("Stop", []))

    _save_settings(settings)

    print("✓ Relay uninstalled.")
    print("Restart Claude Code for changes to take effect.")


def uninstall_codex() -> None:
    hooks = _root_hooks_from_config(_load_toml(_CODEX_CONFIG_PATH))

    hooks["PreToolUse"] = _remove_relay_hooks(hooks.get("PreToolUse", []))
    hooks["PostToolUse"] = _remove_relay_hooks(hooks.get("PostToolUse", []))
    hooks["Stop"] = _remove_relay_hooks(hooks.get("Stop", []))

    _write_codex_config_hooks(hooks)

    print("✓ Relay uninstalled from global Codex config.")
    print("Restart Codex for changes to take effect.")


def uninstall_all() -> None:
    uninstall()
    print()
    uninstall_codex()
