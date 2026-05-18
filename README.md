# Relay

Relay 是一个 Claude Code 智能中断层。它通过 hook 拦截每次工具调用，结合历史审批记录和风险评估，自动决定哪些操作直接执行、哪些需要暂停等你确认，并在需要确认时发送桌面通知。

**核心价值：** 让 AI 任务在后台跑，只在真正需要你决策时才打断你。

[English](README.en.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

## 工作原理

```
Claude 准备执行工具（Write、Bash、Edit 等）
    ↓
PreToolUse hook 触发 → relay hook pre
    ↓
查询历史批准率 + 评估风险等级
    ↓
allow → 工具直接执行，自动记录为已批准
ask   → 工具暂停，发送桌面通知，Claude Code 弹出确认提示
    ↓
用户确认后 Claude 继续，PostToolUse hook 记录结果
    ↓
历史积累 → 下次同类操作判断更准确
```

## 决策逻辑

| 条件 | 结果 |
|---|---|
| 高风险操作（删文件、force push、drop 表、写系统路径） | 始终拦截 |
| 低风险 + 历史批准率 ≥ 90% | 始终直接执行 |
| 该类型操作首次出现（无历史） | 低风险直接执行，其他拦截一次建立基线 |
| 其他情况 | 历史批准率 < 80% 则拦截 |

操作类型按路径和命令细分，各自独立积累批准率：

| 操作类型 | 说明 | 风险 |
|---|---|---|
| `file_write:system` | 写入 `/etc/`、`/usr/` 等系统路径 | 高 |
| `file_write:config` | 写入 `.env`、`.yaml`、`.toml` 等配置文件 | 中 |
| `file_write:code` | 写入普通代码文件 | 中 |
| `bash_write:git` | git commit / push / merge | 中 |
| `bash_write:package_manager` | pip / uv / npm 安装 | 中 |
| `bash_write:shell` | mv / cp / chmod 等 shell 操作 | 中 |
| `file_delete` | rm、drop table 等删除操作 | 高 |
| `bash_read` / `file_read` | 只读操作 | 低 |

## 安装

**全局安装**（推荐）——将以下内容添加到 **`~/.claude.json`** 的 `mcpServers` 字段：

```json
{
  "mcpServers": {
    "relay": {
      "type": "stdio",
      "command": "uvx",
      "args": ["relay"]
    }
  }
}
```

**项目级安装**——在项目根目录创建 **`.mcp.json`**：

```json
{
  "mcpServers": {
    "relay": {
      "type": "stdio",
      "command": "uvx",
      "args": ["relay"]
    }
  }
}
```

重启 Claude Code。Relay 会在首次启动时自动将 hook 注册到 `~/.claude/settings.json`，之后所有工具调用都会经过 relay 的决策层。

## 卸载

```bash
uvx relay --uninstall
```

## 通知支持

通知文字会根据系统语言自动切换，目前支持中文、英文、日文、韩文。

| 平台 | 实现 | 说明 |
|---|---|---|
| macOS | `osascript` | 系统内置，开箱即用 |
| Linux | `notify-send` | 需要桌面环境，Ubuntu/GNOME 默认已有 |
| Windows | `plyer` | 开箱即用 |

## MCP 工具（可选）

安装 hook 后 relay 已经自动工作，不需要额外配置。但如果你想查看统计数据，可以在 Claude Code 里调用 `relay__get_stats_tool` 查看审批统计。

## 已知限制

Relay hook 在 `--dangerously-skip-permissions` 模式下不生效（该模式完全跳过 hook 机制）。

## 本地开发

```bash
git clone https://github.com/solost23/relay
cd relay
uv sync
uv run pytest
uv run mcp dev relay/server.py
```

