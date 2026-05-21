# cc-relay

[![PyPI version](https://img.shields.io/pypi/v/cc-relay)](https://pypi.org/project/cc-relay/)
[![Python](https://img.shields.io/pypi/pyversions/cc-relay)](https://pypi.org/project/cc-relay/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Relay は Claude Code の自適応割り込みレイヤーです。フックを通じてすべてのツール呼び出しをインターセプトし、承認履歴から学習して、どの操作をそのまま実行し、どの操作を一時停止するかを自動的に判断します。本当に判断が必要なときだけ割り込み、デスクトップ通知を送るのでタスクが止まっても気づけます。

**核心的な価値：** 他のツールは静的ルールや毎回 LLM を呼び出す方式を使いますが、Relay は操作タイプごとの実際の承認率を追跡し、時間とともに自動的に適応します。`git commit` を 10 回承認すれば、もう聞いてきません。高リスク操作は常に割り込み——それ以外は使えば使うほど静かになります。

[中文](README.zh.md) | [English](README.md) | [한국어](README.ko.md)

## なぜ cc-relay か

| | 静的許可リスト | LLM 分類器 | **cc-relay** |
|---|---|---|---|
| セットアップ | 手動でルール管理 | API キーが必要 | ゼロ設定 |
| あなたから学習 | いいえ | いいえ | **はい** |
| 判断コスト | 無料 | ~$0.001/回 | 無料 |
| ワークフローに適応 | いいえ | いいえ | **はい** |
| オフライン動作 | はい | いいえ | **はい** |

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
ユーザーが拒否 → セッション終了
    ↓
Stop フックが起動 → 保留レコードを拒否済みとしてマーク + タスク完了通知を送信
    ↓
履歴が蓄積 → 同種の操作に対する判断がより正確になる
```

## 判断ロジック

| 条件 | 結果 |
|---|---|
| 高リスク操作（ファイル削除、force push、テーブル削除、システムパスへの書き込み） | 常に割り込む |
| 低リスク、有効ウェイト < 4 | 自動承認（ベースライン不要） |
| 低リスク、有効ウェイト ≥ 4、承認率 ≥ 90% | 自動承認 |
| 中リスク、有効ウェイト < 7 | 割り込んでベースラインを構築 |
| 中リスク、有効ウェイト ≥ 7、承認率 ≥ 85% | 自動承認 |
| その他 | 割り込む |

承認率は**指数時間減衰**（半減期：7日）を使用します——最近の判断は古い記録より高いウェイトを持ちます。以前は常に承認していた操作を拒否し始めると、加重承認率は数日以内に急速に低下し、Relay は再び割り込むようになります。古い承認記録は自然に減衰するため、システムが永続的に自動承認状態に固定されることはありません。

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
      "args": ["cc-relay@latest"]
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
      "args": ["cc-relay@latest"]
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

Relay は 2 種類のデスクトップ通知を送信します。通知テキストはシステム言語に応じて自動的に切り替わります。現在のサポート言語：中国語、英語、日本語、韓国語。

- **割り込み通知**：操作の承認が必要なとき——ターミナルに戻るよう促します
- **完了通知**：Claude が応答を完了したとき——その場を離れていてもタスクの終了を把握できます

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
