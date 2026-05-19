# cc-relay

Relay 是一个 Claude Code 智能中断层。它通过 hook 拦截每次工具调用，结合历史审批记录和风险评估，自动决定哪些操作直接执行、哪些需要暂停等你确认，并在需要确认时发送桌面通知。

**核心价值：** 让 AI 任务在后台跑，只在真正需要你决策时才打断你。

[English](README.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

## 工作原理

```
Claude 准备执行工具（Write、Bash、Edit 等）
    ↓
PreToolUse hook 触发 → relay hook pre
    ↓
查询历史批准率 + 评估风险等级
    ↓
allow → 工具直接执行，自动记录为已批准
ask   → 工具暂停，写入待处理记录，发送桌面通知，Claude Code 弹出确认提示
    ↓
用户确认后 Claude 继续，PostToolUse hook 将待处理记录标记为已批准
用户拒绝后会话结束，Stop hook 将所有未确认记录标记为已拒绝
    ↓
历史积累 → 下次同类操作判断更准确
```

## 决策逻辑

| 条件 | 结果 |
|---|---|
| 高风险操作（删文件、force push、drop 表、写系统路径） | 始终拦截 |
| 低风险，样本 < 5 | 直接执行（无需建立基线） |
| 低风险，样本 ≥ 5，批准率 ≥ 90% | 自动执行 |
| 中风险，样本不足（自适应阈值：5–12 次，取决于使用频率） | 拦截，建立基线 |
| 中风险，样本充足，批准率 ≥ 85% | 自动执行 |
| 其他情况 | 拦截 |

中风险自适应阈值根据过去 30 天的活跃天数动态调整：高频（≥7 天）需 5 次，中频（2–6 天）需 8 次，低频（≤1 天）需 12 次。

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
      "args": ["cc-relay@latest"]
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
      "args": ["cc-relay@latest"]
    }
  }
}
```

重启 Claude Code。Relay 会在首次启动时自动将 hook 注册到 `~/.claude/settings.json`，之后所有工具调用都会经过 relay 的决策层。

## 卸载

```bash
uvx cc-relay --uninstall
```

## 通知支持

通知文字会根据系统语言自动切换，目前支持中文、英文、日文、韩文。

| 平台 | 实现 | 说明 |
|---|---|---|
| macOS | `osascript` | 系统内置，开箱即用 |
| Linux | `notify-send` | 需要桌面环境，Ubuntu/GNOME 默认已有 |
| Windows | `plyer` | 开箱即用 |

## MCP 工具（可选）

安装 hook 后 relay 已经自动工作，不需要额外配置。你也可以在 Claude Code 里直接调用以下工具：

| 工具 | 说明 |
|---|---|
| `relay__get_stats_tool` | 查看所有操作类型的审批统计 |
| `relay__get_recent_decisions_tool` | 查看某个操作类型的最近决策记录 |
| `relay__reset_action_type_tool` | 清除某个操作类型的所有历史，重新建立基线 |

## CLI 命令

```bash
# 安装 / 卸载 hook
uvx cc-relay --install
uvx cc-relay --uninstall

# 查看某操作类型的最近决策（默认 20 条）
uvx cc-relay --history bash_write:git
uvx cc-relay --history file_write:code 50

# 清除某操作类型的所有历史
uvx cc-relay --reset bash_write:git
```

## 已知限制

Relay hook 在 `--dangerously-skip-permissions` 模式下不生效（该模式完全跳过 hook 机制）。

## 本地开发

```bash
git clone https://github.com/solost23/cc-relay
cd cc-relay
uv sync
uv run pytest
uv run mcp dev cc_relay/server.py
```

