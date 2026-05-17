# Relay

Relay는 Claude Code의 지능형 인터럽트 레이어입니다. 훅을 통해 모든 도구 호출을 가로채고, 과거 승인 기록과 위험도 평가를 결합하여 어떤 작업을 바로 실행하고 어떤 작업을 확인을 위해 일시 중지할지 자동으로 결정합니다. 확인이 필요한 경우 데스크톱 알림을 전송합니다.

**핵심 가치:** AI 작업을 백그라운드에서 실행하고, 실제로 판단이 필요할 때만 알림을 받으세요.

[中文](README.md) | [English](README.en.md) | [日本語](README.ja.md)

## 작동 방식

```
Claude가 도구를 실행하려 함 (Write, Bash, Edit 등)
    ↓
PreToolUse 훅 실행 → relay hook pre
    ↓
과거 승인율 조회 + 위험 수준 평가
    ↓
allow → 도구 즉시 실행, 승인됨으로 기록
ask   → 도구 일시 중지, 데스크톱 알림 전송, Claude Code가 확인 프롬프트 표시
    ↓
사용자 확인 → Claude 계속 진행, PostToolUse 훅이 결과 기록
    ↓
기록 누적 → 동일 유형 작업에 대한 판단이 더 정확해짐
```

## 결정 로직

| 조건 | 결과 |
|---|---|
| 고위험 작업 (파일 삭제, force push, 테이블 삭제, 시스템 경로 쓰기) | 항상 인터럽트 |
| 저위험 + 과거 승인율 ≥ 90% | 항상 자동 승인 |
| 해당 작업 유형 최초 발생 (기록 없음) | 저위험: 자동 승인, 그 외: 한 번 인터럽트하여 기준선 구축 |
| 그 외 | 승인율 < 80%이면 인터럽트 |

작업 유형은 경로와 명령어에 따라 세분화되며, 각각 독립적으로 승인율을 누적합니다:

| 작업 유형 | 설명 | 위험도 |
|---|---|---|
| `file_write:system` | `/etc/`, `/usr/` 등 시스템 경로 쓰기 | 높음 |
| `file_write:config` | `.env`, `.yaml`, `.toml` 등 설정 파일 쓰기 | 중간 |
| `file_write:code` | 일반 코드 파일 쓰기 | 중간 |
| `bash_write:git` | git commit / push / merge | 중간 |
| `bash_write:package_manager` | pip / uv / npm 설치 | 중간 |
| `bash_write:shell` | mv / cp / chmod 등 셸 작업 | 중간 |
| `file_delete` | rm, drop table 등 삭제 작업 | 높음 |
| `bash_read` / `file_read` | 읽기 전용 작업 | 낮음 |

## 설치

**전역 설치** (권장) — **`~/.claude/settings.json`** 의 `mcpServers` 필드에 다음을 추가하세요:

```json
{
  "mcpServers": {
    "relay": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/solost23/relay", "relay"]
    }
  }
}
```

**프로젝트별 설치** — 프로젝트 루트에 **`.mcp.json`** 을 생성하세요:

```json
{
  "mcpServers": {
    "relay": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", "git+https://github.com/solost23/relay", "relay"]
    }
  }
}
```

Claude Code를 재시작하세요. Relay는 첫 번째 시작 시 자동으로 훅을 `~/.claude/settings.json`에 등록합니다. 이후 모든 도구 호출이 relay 결정 레이어를 통과합니다.

## 제거

```bash
uvx --from git+https://github.com/solost23/relay relay --uninstall
```

## 알림 지원

알림 텍스트는 시스템 언어에 따라 자동으로 전환됩니다. 현재 지원 언어: 중국어, 영어, 일본어, 한국어.

| 플랫폼 | 구현 | 비고 |
|---|---|---|
| macOS | `osascript` | 내장, 바로 사용 가능 |
| Linux | `notify-send` | 데스크톱 환경 필요, Ubuntu/GNOME에서 기본 제공 |
| Windows | `plyer` | 바로 사용 가능 |

## MCP 도구 (선택 사항)

훅을 설치하면 Relay가 자동으로 작동하며 추가 설정이 필요 없습니다. 승인 통계를 확인하려면 Claude Code 내에서 `relay__get_stats_tool`을 호출하세요.

## 알려진 제한 사항

Relay 훅은 `--dangerously-skip-permissions` 모드에서 작동하지 않습니다 (해당 모드는 훅 메커니즘을 완전히 우회합니다).

## 로컬 개발

```bash
git clone https://github.com/solost23/relay
cd relay
uv sync
uv run pytest
uv run mcp dev relay/server.py
```
