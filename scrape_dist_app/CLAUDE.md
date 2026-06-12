# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`scrape_dist_app` is one of the standalone tools in the `el-hub` workspace (see `../CLAUDE.md`). It scrapes error items from a Google Sheet, **auto-distributes** them into a copy of an Excel file across four review sheets, applies Rich Text diff highlighting and formatting, and saves a `_자동분류` output. PySide6 GUI; packaged as a separate exe (`dataclip`).

## Commands

```bash
uv sync                                # install deps
uv run python new_gui_app.py           # run GUI (also: uv run gui)
uv run pyinstaller build.spec          # build the exe

# run the pipeline headless (must chdir to the package so config.json resolves):
uv run python -c "import os; os.chdir(r'C:\\Users\\User\\Desktop\\work\\template\\auto\\scrape_dist_app'); \
from common.pipeline import run_pipeline; \
run_pipeline('파일.xlsx', gsheet_index=2, start_box='B0001', end_box='B0010', run_diff=False)"
```

No test suite or linter is configured.

## Authentication (changed — no more service-account key)

Auth now uses the **shared hub Google OAuth token**, not a `google_key.json` service account. `core/secure_token.py` reads the DPAPI-encrypted token from Windows Credential Manager (service `AutoHub-GoogleOAuth`); `scrape_core` builds a `gspread` client from it and auto-refreshes/rotates the refresh token. **The user must log in via `hub.py` first** — with no stored token the pipeline raises immediately.

`core/secure_token.py` is a **verbatim copy** of `../secure_store.py` (this app packages as its own exe and can't import the workspace root). The `_SERVICE` / `_ACCOUNT` / `_ENTROPY` constants must stay identical across both copies and `../hub_auth.py`, or the apps stop sharing the session.

## Required config

`config.json` (next to the exe / package root, read **cwd-relative**):

| key | meaning |
|-----|---------|
| `SPREADSHEET_URL` | source Google Sheet URL (auto-created with defaults if missing) |
| `theme` | `"dark"` or `"light"` |
| `run_diff` | `true` → run stages 3 & 5 (diff highlight + XML patch); `false` → skip |

## Architecture

```
new_gui_app.py              entry shim → gui.app.main()
gui/                        PySide6 GUI shell (thin runner over the pipeline)
    app.py                  PipelineApp window + main(); box-range inputs, sheet radios, _register_runtime_state()
    worker.py               PipelineWorker (QThread) — chdir(PROJECT_ROOT) then run_pipeline
    paths.py                PROJECT_ROOT + sys.path bootstrap (frozen-exe aware)
    config.py palette.py style.py fonts.py dialogs.py utils.py   thin shims over the shared `elhub_ui` design system (re-export/wrap, injecting this app's FONT_DIR/CONFIG_FILE/README_PATH + app-specific QSS); `gui/paths.py` adds the repo root to sys.path so `import elhub_ui` resolves. See `../CLAUDE.md` › "Shared design system".
common/pipeline.py          run_pipeline() — the 5-stage orchestrator
common/pipeline_without_diff.py   3-stage variant (no diff/XML patch)
common/constants.py         column mapping, GROUPS, sheet names, shared constants
common/utils.py             string normalization, line splitting, parse_fix_text
common/logger.py            FileLogger → log/
core/scrape_core.py         stage 1: gspread load → box range → parse items
core/dist_core.py           stage 2: copy Excel → write A~H → dedup/distribute → L/M/N
core/diff_core.py           stage 3: Rich Text before/after diff on single-item N cells; stage 5 XML patch
core/design_core.py         stage 4: borders/font/alignment/row-height (reloads rich_text=True to keep CellRichText)
core/secure_token.py        shared OAuth token reader (copy of ../secure_store.py)
```

### Pipeline (`run_pipeline`, called on a worker thread)

1. `scrape_core.run_scrape()` → `(rows_list, parsed_items_list)`. `rows_list` = A~H common-info rows; `parsed_items_list` = per-row `List[Dict]` (`err`, `page`, `before`, `after`, `arrow`). `gsheet_index`: 1=서울, 2=부산, 3=디파. It **copies** the source sheet server-side before reading.
2. `dist_core.run_distribute()` → writes `_자동분류{ext}`, returns its path.
3. `diff_core.run_diff_highlight()` — Rich Text diff on N-column single-item cells (only if `run_diff`).
4. `design_core.run_design()` — bulk formatting, in place.
5. `diff_core.patch_xml_space_preserve()` — works around an openpyxl 3.1.5 bug that drops `xml:space="preserve"` (only if `run_diff`).

## Gotchas

- **cwd dependency.** `scrape_core` reads `config.json` cwd-relative. The GUI worker does `os.chdir(PROJECT_ROOT)` (from `paths.py`) before running and restores cwd after; any headless/script call must `os.chdir()` to the package dir first or it won't find `config.json`/the token correctly.
- **`paths.py` must import before `common.pipeline`.** `worker.py` imports `from .paths import PROJECT_ROOT` first so the `sys.path` bootstrap runs and `from common.pipeline import run_pipeline` resolves (in dev and in the bundle, where writable files sit beside the exe and read-only data under `_MEIPASS`).
- **Hub integration.** `gui/app.main()` calls `_register_runtime_state()`, which `importlib`-loads `../proc_state.py` and writes `runtime_state.json` (cleared on exit via `atexit`) so the hub detects this app even when launched directly. All failures swallowed; runs fine standalone. `runtime_state.json` is gitignored.

> Note: `README.md` may describe the older service-account-key auth. Trust this file and the source — auth is via the shared hub login now.
