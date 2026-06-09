# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Coding Guidelines

### 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

### 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

### 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

### 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

## Overview

구글 시트에서 오류항목을 스크래핑하여 엑셀 파일에 자동 분배·서식 적용하는 Python PySide6 GUI 데스크톱 앱.

## Commands

```bash
# 의존성 설치 (uv 사용)
uv sync

# GUI 앱 실행
uv run python new_gui_app.py
# 또는
uv run gui

# 파이프라인 단독 실행 (테스트)
uv run python -c "
import os; os.chdir(r'C:\...\scrape_dist_app')
from common.pipeline import run_pipeline
run_pipeline('파일.xlsx', gsheet_index=1, start_box='B0001', end_box='B0010')
"
```

## Required Files

- `credentials/google_key.json` — Google 서비스 계정 키 (없으면 실행 불가)
- `config.json` — `SPREADSHEET_URL`, `theme`, `run_diff` 저장; scrape_core가 cwd 기준으로 읽음

## Architecture

```
new_gui_app.py              진입 shim → gui.app.main() 호출
gui/                        실제 GUI 구현 패키지
    app.py                  PySide6 메인 창 (PipelineApp) + main()
    worker.py               PipelineWorker — QThread로 파이프라인 비동기 실행
    config.py               config.json 로드/저장
    paths.py                PROJECT_ROOT 등 경로 상수
    theme.py                테마·색상 적용 (apply_theme, LOG_COLORS)
    fonts.py                폰트 로드 (load_application_fonts)
    dialogs.py              HelpDialog, SettingsDialog
    utils.py                make_emoji_icon 등 GUI 유틸
common/pipeline.py          파이프라인 통합 진입점 (5단계)
common/pipeline_without_diff.py  diff 없이 3단계만 실행하는 대체 진입점
common/constants.py         컬럼 매핑, GROUPS, 시트 이름 등 공유 상수
common/utils.py             문자열 정규화, 줄 분할 등 공통 유틸
common/logger.py            FileLogger — log/ 디렉터리에 실행 로그 기록
core/scrape_core.py         1단계: gspread로 구글 시트 로드 → 박스 범위 추출 → 오류항목 파싱
core/dist_core.py           2단계: 원본 엑셀 복사 → A~H 공통정보 기록 → L/M/N 시트 분배
core/diff_core.py           3단계: N열 단일 항목 셀에 before/after Rich Text diff 강조 적용
core/design_core.py         4단계: 테두리·폰트·정렬·행 높이 서식 일괄 적용
```

### 데이터 흐름 (pipeline.py 기준)

1. `scrape_core.run_scrape()` → `(rows_list, parsed_items_list)` 반환
   - `rows_list`: A~H 공통정보 원본 행 데이터
   - `parsed_items_list`: 행별 파싱된 오류항목 `List[Dict]` (`err`, `page`, `before`, `after`, `arrow`)
2. `dist_core.run_distribute()` → `_자동분류{확장자}` 파일 경로 반환
3. `diff_core.run_diff_highlight()` → N열 단일 항목 셀에 Rich Text diff 적용 (`run_diff=True` 시)
4. `design_core.run_design()` → 동일 파일에 서식 인플레이스 적용
5. `diff_core.patch_xml_space_preserve()` → openpyxl 3.1.5 버그 우회 XML 후처리 (`run_diff=True` 시)

### config.json 키

| 키 | 설명 |
|----|------|
| `SPREADSHEET_URL` | 구글 시트 URL |
| `theme` | `"dark"` 또는 `"light"` |
| `run_diff` | `true`이면 3·5단계 실행, `false`이면 스킵 |

### cwd 의존성 주의

`scrape_core._load_gsheet_data()`와 `_JSON_KEY_FILE`이 모두 **cwd 기준** 상대경로로 파일을 읽습니다. GUI는 `paths.py`의 `PROJECT_ROOT`로 cwd를 고정하지만, 스크립트로 직접 호출할 때는 `os.chdir()`로 패키지 디렉터리를 먼저 설정해야 합니다.
