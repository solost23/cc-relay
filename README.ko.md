# cc-relay

[![PyPI version](https://img.shields.io/pypi/v/cc-relay)](https://pypi.org/project/cc-relay/)
[![Python](https://img.shields.io/pypi/pyversions/cc-relay)](https://pypi.org/project/cc-relay/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Relay는 Claude Code의 적응형 인터럽트 레이어입니다. 훅을 통해 모든 도구 호출을 가로채고, 승인 기록에서 학습하여 어떤 작업을 바로 실행하고 어떤 작업을 일시 중지할지 자동으로 결정합니다. 실제로 판단이 필요할 때만 알림을 보내므로, 작업이 멈춰도 놓치는 일이 없습니다.

**핵심 가치:** 다른 도구들은 정적 규칙이나 매번 LLM을 호출하는 방식을 사용하지만, Relay는 작업 유형별 실제 승인율을 추적하고 시간이 지남에 따라 자동으로 적응합니다. `git commit`을 10번 승인하면 더 이상 묻지 않습니다. 고위험 작업은 항상 인터럽트하고, 나머지는 사용할수록 조용해집니다.

[中文](README.zh.md) | [English](README.md) | [日本語](README.ja.md)

## 왜 cc-relay인가

| | 정적 허용 목록 | LLM 분류기 | **cc-relay** |
|---|---|---|---|
| 설정 | 수동 규칙 관리 | API 키 필요 | 설정 불필요 |
| 학습 여부 | 아니오 | 아니오 | **예** |
| 결정당 비용 | 무료 | ~$0.001/회 | 무료 |
| 워크플로 적응 | 아니오 | 아니오 | **예** |
| 오프라인 동작 | 예 | 아니오 | **예** |

## 작동 방식

```
Claude가 도구를 실행하려 함 (Write, Bash, Edit 등)
    ↓
PreToolUse 훅 실행 → relay hook pre
    ↓
과거 승인율 조회 + 위험 수준 평가
    ↓
allow → 도구 즉시 실행, 승인됨으로 기록
ask   → 도구 일시 중지, 보류 레코드 기록, 데스크톱 알림 전송, Claude Code가 확인 프롬프트 표시
    ↓
사용자 확인 → Claude 계속 진행, PostToolUse 훅이 보류 레코드를 승인됨으로 표시
사용자 거부 → 세션 종료 시 Stop 훅이 미해결 보류 레코드를 모두 거부됨으로 표시
    ↓
기록 누적 → 동일 유형 작업에 대한 판단이 더 정확해짐
```

## 결정 로직

| 조건 | 결과 |
|---|---|
| 고위험 작업 (파일 삭제, force push, 테이블 삭제, 시스템 경로 쓰기) | 항상 인터럽트 |
| 저위험, 샘플 수 < 5 | 자동 승인 (기준선 불필요) |
| 저위험, 샘플 수 ≥ 5, 승인율 ≥ 90% | 자동 승인 |
| 중위험, 샘플 부족 (적응형 임계값: 5–12회, 사용 빈도에 따라) | 인터럽트하여 기준선 구축 |
| 중위험, 샘플 충분, 승인율 ≥ 85% | 자동 승인 |
| 그 외 | 인터럽트 |

중위험 적응형 임계값은 최근 30일간 활성 일수에 따라 동적으로 조정됩니다: 고빈도(≥7일)는 5회, 중빈도(2–6일)는 8회, 저빈도(≤1일)는 12회가 필요합니다.

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

**전역 설치** (권장) — **`~/.claude.json`** 의 `mcpServers` 필드에 다음을 추가하세요:

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

**프로젝트별 설치** — 프로젝트 루트에 **`.mcp.json`** 을 생성하세요:

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

Claude Code를 재시작하세요. Relay는 첫 번째 시작 시 자동으로 훅을 `~/.claude/settings.json`에 등록합니다. 이후 모든 도구 호출이 relay 결정 레이어를 통과합니다.

## 제거

```bash
uvx cc-relay --uninstall
```

## 알림 지원

알림 텍스트는 시스템 언어에 따라 자동으로 전환됩니다. 현재 지원 언어: 중국어, 영어, 일본어, 한국어.

| 플랫폼 | 구현 | 비고 |
|---|---|---|
| macOS | `osascript` | 내장, 바로 사용 가능 |
| Linux | `notify-send` | 데스크톱 환경 필요, Ubuntu/GNOME에서 기본 제공 |
| Windows | `plyer` | 바로 사용 가능 |

## MCP 도구 (선택 사항)

훅을 설치하면 Relay가 자동으로 작동하며 추가 설정이 필요 없습니다. Claude Code 내에서 다음 도구를 직접 호출할 수도 있습니다:

| 도구 | 설명 |
|---|---|
| `relay__get_stats_tool` | 모든 작업 유형의 승인 통계 조회 |
| `relay__get_recent_decisions_tool` | 특정 작업 유형의 최근 결정 기록 조회 |
| `relay__reset_action_type_tool` | 작업 유형의 모든 기록을 삭제하고 초기화 |

## CLI 명령어

```bash
# 훅 설치 / 제거
uvx cc-relay --install
uvx cc-relay --uninstall

# 작업 유형의 최근 결정 조회 (기본 20개)
uvx cc-relay --history bash_write:git
uvx cc-relay --history file_write:code 50

# 작업 유형의 모든 기록 삭제
uvx cc-relay --reset bash_write:git
```

## 알려진 제한 사항

Relay 훅은 `--dangerously-skip-permissions` 모드에서 작동하지 않습니다 (해당 모드는 훅 메커니즘을 완전히 우회합니다).

## 로컬 개발

```bash
git clone https://github.com/solost23/cc-relay
cd cc-relay
uv sync
uv run pytest
uv run mcp dev cc_relay/server.py
```
