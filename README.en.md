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
ask   → tool pauses, pending record written, desktop notification sent, Claude Code shows a confirmation prompt
    ↓
User confirms → Claude continues, PostToolUse hook marks the pending record as approved
User rejects → session ends, Stop hook marks all unresolved pending records as rejected
    ↓
History accumulates → future decisions for the same action type become more accurate
```

## Decision logic

| Condition | Result |
|---|---|
| High-risk operation (delete files, force push, drop table, write to system paths) | Always interrupt |
| Low risk, samples < 5 | Auto-approve (no baseline needed) |
| Low risk, samples ≥ 5, approval rate ≥ 90% | Auto-approve |
| Medium risk, insufficient samples (adaptive threshold: 5–12, based on usage frequency) | Interrupt to build baseline |
| Medium risk, sufficient samples, approval rate ≥ 85% | Auto-approve |
| Everything else | Interrupt |

The medium-risk adaptive threshold adjusts based on distinct active days in the past 30 days: high-frequency (≥7 days) needs 5 samples, moderate (2–6 days) needs 8, low-frequency (≤1 day) needs 12.

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

Once the hook is installed, Relay works automatically with no further configuration. You can also call these tools directly inside Claude Code:

| Tool | Description |
|---|---|
| `relay__get_stats_tool` | View approval statistics for all action types |
| `relay__get_recent_decisions_tool` | View recent decision history for a specific action type |
| `relay__reset_action_type_tool` | Clear all history for an action type and start fresh |

## CLI commands

```bash
# Install / uninstall hooks
uvx cc-relay --install
uvx cc-relay --uninstall

# View recent decisions for an action type (default 20)
uvx cc-relay --history bash_write:git
uvx cc-relay --history file_write:code 50

# Clear all history for an action type
uvx cc-relay --reset bash_write:git
```

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
