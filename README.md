# Relay

Relay 是一个 MCP server，为 Claude Code 提供智能中断决策层。它通过学习你的历史审批记录，自动判断哪些操作可以直接执行、哪些需要暂停等待你确认，并在需要确认时发送桌面通知。

**核心价值：** 让 AI 任务在后台跑，只在真正需要你决策时才打断你。

## 工作原理

```
Claude 准备执行操作
    ↓
调用 assess_action(action_type, action_description)
    ↓
Relay 查询历史批准率 + 评估风险等级
    ↓
should_interrupt = false → Claude 直接执行
should_interrupt = true  → 发送桌面通知，Claude 暂停等待
    ↓
用户回复后，调用 record_decision 记录结果
    ↓
历史积累 → 下次同类操作判断更准确
```

## 决策逻辑

| 条件 | 结果 |
|---|---|
| 高风险操作（删文件、force push、drop 表） | 始终打断 |
| 低风险 + 历史批准率 ≥ 90% | 始终直接执行 |
| 该类型操作首次出现（无历史） | 低风险直接执行，其他打断一次建立基线 |
| 其他情况 | 历史批准率 < 80% 则打断 |

## 安装

在你的 Claude Code 配置中添加以下 MCP server 配置：

**`~/.claude/mcp.json`** 或项目的 **`.mcp.json`**：

```json
{
  "mcpServers": {
    "relay": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/solost23/relay",
        "relay"
      ]
    }
  }
}
```

重启 Claude Code 后生效，无需手动 clone 仓库。

## 通知支持

| 平台 | 实现 | 说明 |
|---|---|---|
| macOS | `osascript` | 系统内置，开箱即用 |
| Linux | `notify-send` | 需要桌面环境，Ubuntu/GNOME 默认已有 |
| Windows | `plyer` | 开箱即用 |

## MCP 工具说明

### `assess_action`

在执行任何非只读操作前调用，返回是否需要打断用户。

```
assess_action(
    action_type="file_write",
    action_description="Writing updated config to app.yaml"
)
```

返回：
```json
{
  "should_interrupt": true,
  "risk_level": "medium",
  "reversible": true,
  "approval_rate": 0.5,
  "reason": "No history for 'file_write' yet — asking once to establish baseline."
}
```

### `record_decision`

用户回复后必须调用，记录决策结果用于后续学习。

```
record_decision(
    action_type="file_write",
    action_description="Writing updated config to app.yaml",
    decision="approved",
    risk_level="medium"
)
```

### `get_stats_tool`

查看 Relay 已学习到的统计数据。

```json
{
  "total_decisions": 42,
  "by_action_type": [
    { "action_type": "file_write", "total": 20, "approved": 19, "approval_rate": 0.95 },
    { "action_type": "git_push",   "total": 10, "approved": 10, "approval_rate": 1.0  },
    { "action_type": "file_delete","total": 12, "approved": 3,  "approval_rate": 0.25 }
  ]
}
```

## action_type 参考

| action_type | 风险 | 示例 |
|---|---|---|
| `file_read` | 低 | 读取文件 |
| `bash_read` | 低 | ls、cat、grep |
| `git_log` / `git_status` / `git_diff` | 低 | 只读 git 操作 |
| `db_read` | 低 | SELECT 查询 |
| `file_write` / `file_create` | 中 | 创建或修改文件 |
| `bash_write` | 中 | 修改状态的 shell 命令 |
| `git_commit` / `git_push` | 中 | 提交和推送 |
| `db_write` / `db_update` | 中 | INSERT、UPDATE |
| `network_request` | 中 | curl、API 调用 |
| `file_delete` | 高 | 删除文件 |
| `git_reset` / `git_force_push` | 高 | 破坏性 git 操作 |
| `db_drop` | 高 | DROP TABLE、无 WHERE 的 DELETE |

## 已知限制

Relay 在 `--dangerously-skip-permissions` 或 `bypassPermissions` 模式下不生效。这两种模式下 Claude 跳过推理循环直接执行工具，`assess_action` 不会被调用。

## 本地开发

```bash
git clone https://github.com/solost23/relay
cd relay
uv sync
uv run pytest
uv run mcp dev relay/server.py
```
