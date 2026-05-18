# cc-relay

Relay is an intelligent interrupt layer for Claude Code. It intercepts every tool call via hooks, combines historical approval records with risk assessment, and automatically decides which operations to allow through and which to pause for your confirmation — sending a desktop notification when your input is needed.

**Core value:** Let AI tasks run in the background and only interrupt you when a real decision is required.

[中文](README.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

## How it works

```
Claude is about to execute a tool (Write, Bash, Edit, etc.)
    ↓
PreToolUse hook fires → relay hook pre
    ↓
Look up historical approval rate + assess risk level
    ↓
allow → tool executes immediately, recorded as approved
ask   → tool pauses, desktop notification sent, Claude Code shows a confirmation prompt
    ↓
User confirms → Claude continues, PostToolUse hook records the result
    ↓
History accumulates → future decisions for the same action type become more accurate
```

## Decision logic

| Condition | Result |
|---|---|
| High-risk operation (delete files, force push, drop table, write to system paths) | Always interrupt |
| Low risk + historical approval rate ≥ 90% | Always auto-approve |
| First occurrence of this action type (no history) | Low risk: auto-approve; others: interrupt once to build baseline |
| Everything else | Interrupt if approval rate < 80% |

Action types are partitioned by path and command, each accumulating approval rates independently:

| Action type | Description | Risk |
|---|---|---|
| `file_write:system` | Write to `/etc/`, `/usr/`, etc. | High |
| `file_write:config` | Write to `.env`, `.yaml`, `.toml`, etc. | Medium |
| `file_write:code` | Write to regular code files | Medium |
| `bash_write:git` | git commit / push / merge | Medium |
| `bash_write:package_manager` | pip / uv / npm installs | Medium |
| `bash_write:shell` | mv / cp / chmod and other shell ops | Medium |
| `file_delete` | rm, drop table, and other deletions | High |
| `bash_read` / `file_read` | Read-only operations | Low |

## Installation

**Global install** (recommended) — add the following to the `mcpServers` field in **`~/.claude.json`**:

```json
{
  "mcpServers": {
    "relay": {
      "type": "stdio",
      "command": "uvx",
      "args": ["cc-relay"]
    }
  }
}
```

**Per-project install** — create **`.mcp.json`** in your project root:

```json
{
  "mcpServers": {
    "relay": {
      "type": "stdio",
      "command": "uvx",
      "args": ["cc-relay"]
    }
  }
}
```

Restart Claude Code. Relay will automatically register its hooks into `~/.claude/settings.json` on first startup, after which all tool calls will pass through the relay decision layer.

## Uninstall

```bash
uvx cc-relay --uninstall
```

## Notification support

Notification text switches automatically based on system language. Currently supported: Chinese, English, Japanese, Korean.

| Platform | Implementation | Notes |
|---|---|---|
| macOS | `osascript` | Built-in, works out of the box |
| Linux | `notify-send` | Requires a desktop environment; available by default on Ubuntu/GNOME |
| Windows | `plyer` | Works out of the box |

## MCP tools (optional)

Once the hook is installed, Relay works automatically with no further configuration. If you want to inspect approval statistics, call `relay__get_stats_tool` inside Claude Code.

## Known limitations

Relay hooks do not fire in `--dangerously-skip-permissions` mode (that mode bypasses the hook mechanism entirely).

## Local development

```bash
git clone https://github.com/solost23/cc-relay
cd cc-relay
uv sync
uv run pytest
uv run mcp dev cc_relay/server.py
```
