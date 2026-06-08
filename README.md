# cc-relay

[![PyPI version](https://img.shields.io/pypi/v/cc-relay)](https://pypi.org/project/cc-relay/)
[![Python](https://img.shields.io/pypi/pyversions/cc-relay)](https://pypi.org/project/cc-relay/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

An adaptive interrupt layer for Claude Code and Codex. Relay intercepts tool calls via hooks, learns from your approval history, and automatically decides what to let through — only interrupting you when a real decision is needed, and sending a desktop notification so you're never left wondering why the task stalled.

**The key idea:** other permission tools use static rules or call an LLM on every action. Relay tracks your actual approval rate per action type and adapts over time. After you approve `git commit` ten times, it stops asking. High-risk operations always interrupt — everything else gets quieter as you use it.

[中文](README.zh.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

## Why cc-relay

| | Static allowlists | LLM classifier | **cc-relay** |
|---|---|---|---|
| Setup | Manual rule maintenance | API key required | Zero config |
| Learns from you | No | No | **Yes** |
| Cost per decision | Free | ~$0.001/call | Free |
| Adapts to your workflow | No | No | **Yes** |
| Works offline | Yes | No | **Yes** |

## How it works

```
The agent is about to execute a tool (Write, Bash, Edit, shell command, etc.)
    ↓
PreToolUse hook fires → relay hook pre
    ↓
Look up historical approval rate + assess risk level
    ↓
allow → tool executes immediately, auto-recorded as approved
interrupt → tool pauses or is blocked, desktop notification sent, client asks for your decision
    ↓
User confirms → agent continues, PostToolUse marks record as approved
User rejects  → session ends
    ↓
Stop hook fires → marks pending records as rejected + sends completion notification
    ↓
History accumulates → same action type gets quieter over time
```

## Decision logic

| Condition | Result |
|---|---|
| High-risk (delete files, force push, drop table, system paths) | Always interrupt |
| Low risk, effective weight < 4 | Auto-approve (no baseline needed) |
| Low risk, effective weight ≥ 4, approval rate ≥ 90% | Auto-approve |
| Medium risk, effective weight < 7 | Interrupt to build baseline |
| Medium risk, effective weight ≥ 7, approval rate ≥ 85% | Auto-approve |
| Everything else | Interrupt |

Approval rates use **exponential time decay** (half-life: 7 days) — recent decisions carry more weight than old ones. If you start rejecting an action you previously always approved, the weighted approval rate drops quickly and Relay starts interrupting again within days. Old approvals fade naturally, so the system never gets permanently locked into auto-approve.

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

Relay supports both **Claude Code** and **Codex**. Add the MCP server to your agent config; on first startup, Relay installs hooks for both clients:

- Claude Code hooks: `~/.claude/settings.json`
- Codex hooks: `~/.codex/config.toml`

**Claude Code global config** — add to the `mcpServers` field in **`~/.claude.json`**:

```json
{
  "mcpServers": {
    "relay": {
      "type": "stdio",
      "command": "uvx",
      "args": ["cc-relay@latest"]
    }
  }
}
```

**Codex global config** — add to **`~/.codex/config.toml`**:

```toml
[mcp_servers.relay]
type = "stdio"
command = "uvx"
args = ["cc-relay@latest"]
```

Restart your agent. Relay starts as an MCP server and runs `--install-all` behavior automatically, so both Claude Code and Codex hooks are kept up to date.

## Uninstall

```bash
uvx cc-relay --uninstall-all
```

## Notification support

Relay sends two types of desktop notifications. Text auto-switches based on system language (Chinese, English, Japanese, Korean).

- **Interrupt**: when an action needs your approval — prompts you to return to the terminal
- **Completion**: when the agent finishes responding — so you know the task is done even if you stepped away

| Platform | Implementation | Notes |
|---|---|---|
| macOS | `osascript` | Built-in, works out of the box |
| Linux | `notify-send` | Requires desktop environment (default on Ubuntu/GNOME) |
| Windows | `plyer` | Works out of the box |

## MCP tools

Once installed, Relay works automatically. You can also call these tools directly inside Claude Code or Codex:

| Tool | Description |
|---|---|
| `relay__get_stats_tool` | View approval statistics for all action types |
| `relay__get_recent_decisions_tool` | View recent decision history for a specific action type |
| `relay__reset_action_type_tool` | Clear history for an action type and rebuild baseline |

## CLI

```bash
# Install / uninstall both Claude Code and Codex hooks
uvx cc-relay --install-all
uvx cc-relay --uninstall-all

# Advanced: manage one client only
uvx cc-relay --install
uvx cc-relay --install-codex
uvx cc-relay --uninstall
uvx cc-relay --uninstall-codex

# View recent decisions for an action type (default 20)
uvx cc-relay --history bash_write:git
uvx cc-relay --history file_write:code 50

# Clear all history for an action type
uvx cc-relay --reset bash_write:git
```

## Known limitations

Relay hooks do not fire in `--dangerously-skip-permissions` mode (that mode bypasses the hook mechanism entirely).

Codex PreToolUse hooks cannot pause for an inline approval prompt. When Relay blocks a Codex action, the agent must stop and wait for you; if you explicitly approve the exact action and the agent retries it, Relay flips the recent rejected record to approved and lets that retry through.

## Local development

```bash
git clone https://github.com/solost23/cc-relay
cd cc-relay
uv sync
uv run pytest
uv run mcp dev cc_relay/server.py
```
