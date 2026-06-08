# cc-relay

[![PyPI version](https://img.shields.io/pypi/v/cc-relay)](https://pypi.org/project/cc-relay/)
[![Python](https://img.shields.io/pypi/pyversions/cc-relay)](https://pypi.org/project/cc-relay/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Relay 是一个支持 Claude Code 和 Codex 的自适应中断层。它通过 hook 拦截工具调用，从你的审批历史中学习，自动决定哪些操作直接执行、哪些需要暂停——只在真正需要你决策时才打断你，并发送桌面通知，让你不会错过任何需要处理的时刻。

**核心价值：** 其他权限工具用静态规则或每次调用 LLM 判断，Relay 追踪你对每类操作的实际批准率，随时间自动适应。批准 `git commit` 十次之后，它就不再问了。高风险操作始终拦截——其他操作会随着使用越来越安静。

[English](README.md) | [日本語](README.ja.md) | [한국어](README.ko.md)

## 为什么选 cc-relay

| | 静态白名单 | LLM 分类器 | **cc-relay** |
|---|---|---|---|
| 配置成本 | 手动维护规则 | 需要 API Key | 零配置 |
| 从你的行为学习 | 否 | 否 | **是** |
| 每次决策成本 | 免费 | ~$0.001/次 | 免费 |
| 适应你的工作流 | 否 | 否 | **是** |
| 离线可用 | 是 | 否 | **是** |

## 工作原理

```
Agent 准备执行工具（Write、Bash、Edit、shell command 等）
    ↓
PreToolUse hook 触发 → relay hook pre
    ↓
查询历史批准率 + 评估风险等级
    ↓
allow → 工具直接执行，自动记录为已批准
interrupt → 工具暂停或被阻止，写入待处理记录，发送桌面通知，客户端请求你决策
    ↓
用户确认后 agent 继续，PostToolUse hook 将待处理记录标记为已批准
用户拒绝后会话结束
    ↓
Stop hook 触发 → 将待处理记录标记为已拒绝 + 发送任务完成通知
    ↓
历史积累 → 下次同类操作判断更准确
```

## 决策逻辑

| 条件 | 结果 |
|---|---|
| 高风险操作（删文件、force push、drop 表、写系统路径） | 始终拦截 |
| 低风险，有效权重 < 4 | 直接执行（无需建立基线） |
| 低风险，有效权重 ≥ 4，批准率 ≥ 90% | 自动执行 |
| 中风险，有效权重 < 7 | 拦截，建立基线 |
| 中风险，有效权重 ≥ 7，批准率 ≥ 85% | 自动执行 |
| 其他情况 | 拦截 |

批准率采用**指数时间衰减**（半衰期 7 天）——近期决策的权重高于旧记录。如果你开始拒绝之前一直批准的操作，加权批准率会在几天内快速下降，Relay 会重新开始询问。旧的批准记录自然衰减，系统不会永久锁定在自动通过状态。

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

Relay 同时支持 **Claude Code** 和 **Codex**。把 MCP server 添加到对应客户端配置后，Relay 首次启动会自动为两个客户端安装 hook：

- Claude Code hook：`~/.claude/settings.json`
- Codex hook：`~/.codex/config.toml`

**Claude Code 全局配置**——将以下内容添加到 **`~/.claude.json`** 的 `mcpServers` 字段：

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

**Codex 全局配置**——将以下内容添加到 **`~/.codex/config.toml`**：

```toml
[mcp_servers.relay]
type = "stdio"
command = "uvx"
args = ["cc-relay@latest"]
```

重启客户端。Relay 作为 MCP server 启动时会自动执行 `--install-all` 行为，保持 Claude Code 和 Codex 的 hook 都是最新版本。

## 卸载

```bash
uvx cc-relay --uninstall-all
```

## 通知支持

Relay 会发送两种桌面通知，通知文字根据系统语言自动切换，目前支持中文、英文、日文、韩文。

- **拦截通知**：当某个操作需要你确认时——提示你返回终端处理
- **完成通知**：当 agent 完成响应时——即使你离开了也能知道任务已结束

| 平台 | 实现 | 说明 |
|---|---|---|
| macOS | `osascript` | 系统内置，开箱即用 |
| Linux | `notify-send` | 需要桌面环境，Ubuntu/GNOME 默认已有 |
| Windows | `plyer` | 开箱即用 |

## MCP 工具（可选）

安装 hook 后 relay 已经自动工作，不需要额外配置。你也可以在 Claude Code 或 Codex 里直接调用以下工具：

| 工具 | 说明 |
|---|---|
| `relay__get_stats_tool` | 查看所有操作类型的审批统计 |
| `relay__get_recent_decisions_tool` | 查看某个操作类型的最近决策记录 |
| `relay__reset_action_type_tool` | 清除某个操作类型的所有历史，重新建立基线 |

## CLI 命令

```bash
# 同时安装 / 卸载 Claude Code 和 Codex hook
uvx cc-relay --install-all
uvx cc-relay --uninstall-all

# 高级用法：只管理某一个客户端
uvx cc-relay --install
uvx cc-relay --install-codex
uvx cc-relay --uninstall
uvx cc-relay --uninstall-codex

# 查看某操作类型的最近决策（默认 20 条）
uvx cc-relay --history bash_write:git
uvx cc-relay --history file_write:code 50

# 清除某操作类型的所有历史
uvx cc-relay --reset bash_write:git
```

## 已知限制

Relay hook 在 `--dangerously-skip-permissions` 模式下不生效（该模式完全跳过 hook 机制）。

Codex 的 PreToolUse hook 不能在原地暂停并弹出交互式审批。Relay 拦截 Codex 操作后，agent 必须停止并等待你的明确指令；如果你明确同意这一次完全相同的操作，agent 重试时 Relay 会把最近那条 rejected 记录反转为 approved，并放行这次重试。

## 本地开发

```bash
git clone https://github.com/solost23/cc-relay
cd cc-relay
uv sync
uv run pytest
uv run mcp dev cc_relay/server.py
```
