# cc-relay

Relay は Claude Code のインテリジェント割り込みレイヤーです。フックを通じてすべてのツール呼び出しをインターセプトし、過去の承認履歴とリスク評価を組み合わせて、どの操作をそのまま実行し、どの操作を確認のために一時停止するかを自動的に判断します。確認が必要な場合はデスクトップ通知を送信します。

**核心的な価値：** AI タスクをバックグラウンドで実行させ、本当に判断が必要なときだけ割り込む。

[中文](README.md) | [English](README.en.md) | [한국어](README.ko.md)

## 仕組み

```
Claude がツールを実行しようとする（Write、Bash、Edit など）
    ↓
PreToolUse フックが起動 → relay hook pre
    ↓
過去の承認率を参照 + リスクレベルを評価
    ↓
allow → ツールをそのまま実行、承認済みとして記録
ask   → ツールを一時停止、保留レコードを書き込み、デスクトップ通知を送信、Claude Code が確認プロンプトを表示
    ↓
ユーザーが確認 → Claude が続行、PostToolUse フックが保留レコードを承認済みとしてマーク
ユーザーが拒否 → セッション終了時に Stop フックが未解決の保留レコードをすべて拒否済みとしてマーク
    ↓
履歴が蓄積 → 同種の操作に対する判断がより正確になる
```

## 判断ロジック

| 条件 | 結果 |
|---|---|
| 高リスク操作（ファイル削除、force push、テーブル削除、システムパスへの書き込み） | 常に割り込む |
| 低リスク、サンプル数 < 5 | 自動承認（ベースライン不要） |
| 低リスク、サンプル数 ≥ 5、承認率 ≥ 90% | 自動承認 |
| 中リスク、サンプル不足（自適応閾値：5〜12 回、使用頻度による） | 割り込んでベースラインを構築 |
| 中リスク、サンプル十分、承認率 ≥ 85% | 自動承認 |
| その他 | 割り込む |

中リスクの自適応閾値は過去 30 日間のアクティブ日数に基づいて動的に調整されます：高頻度（≥7 日）は 5 サンプル、中頻度（2〜6 日）は 8 サンプル、低頻度（≤1 日）は 12 サンプルが必要です。

操作タイプはパスとコマンドで細分化され、それぞれ独立して承認率を蓄積します：

| 操作タイプ | 説明 | リスク |
|---|---|---|
| `file_write:system` | `/etc/`、`/usr/` などへの書き込み | 高 |
| `file_write:config` | `.env`、`.yaml`、`.toml` などの設定ファイルへの書き込み | 中 |
| `file_write:code` | 通常のコードファイルへの書き込み | 中 |
| `bash_write:git` | git commit / push / merge | 中 |
| `bash_write:package_manager` | pip / uv / npm インストール | 中 |
| `bash_write:shell` | mv / cp / chmod などのシェル操作 | 中 |
| `file_delete` | rm、drop table などの削除操作 | 高 |
| `bash_read` / `file_read` | 読み取り専用操作 | 低 |

## インストール

**グローバルインストール**（推奨）— **`~/.claude.json`** の `mcpServers` フィールドに以下を追加してください：

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

**プロジェクト単位のインストール**— プロジェクトルートに **`.mcp.json`** を作成してください：

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

Claude Code を再起動してください。Relay は初回起動時に自動的にフックを `~/.claude/settings.json` に登録します。以降、すべてのツール呼び出しが relay の判断レイヤーを通過します。

## アンインストール

```bash
uvx cc-relay --uninstall
```

## 通知サポート

通知テキストはシステム言語に応じて自動的に切り替わります。現在のサポート言語：中国語、英語、日本語、韓国語。

| プラットフォーム | 実装 | 備考 |
|---|---|---|
| macOS | `osascript` | 組み込み、すぐに使える |
| Linux | `notify-send` | デスクトップ環境が必要、Ubuntu/GNOME ではデフォルトで利用可能 |
| Windows | `plyer` | すぐに使える |

## MCP ツール（オプション）

フックをインストールすれば Relay は自動的に動作し、追加設定は不要です。Claude Code 内で以下のツールを直接呼び出すこともできます：

| ツール | 説明 |
|---|---|
| `relay__get_stats_tool` | すべての操作タイプの承認統計を表示 |
| `relay__get_recent_decisions_tool` | 特定の操作タイプの最近の決定履歴を表示 |
| `relay__reset_action_type_tool` | 操作タイプのすべての履歴を削除してリセット |

## CLI コマンド

```bash
# フックのインストール / アンインストール
uvx cc-relay --install
uvx cc-relay --uninstall

# 操作タイプの最近の決定を表示（デフォルト 20 件）
uvx cc-relay --history bash_write:git
uvx cc-relay --history file_write:code 50

# 操作タイプのすべての履歴を削除
uvx cc-relay --reset bash_write:git
```

## 既知の制限

Relay フックは `--dangerously-skip-permissions` モードでは動作しません（このモードはフック機構を完全にバイパスします）。

## ローカル開発

```bash
git clone https://github.com/solost23/cc-relay
cd cc-relay
uv sync
uv run pytest
uv run mcp dev cc_relay/server.py
```
