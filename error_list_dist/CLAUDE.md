# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`error_list_dist` is one of the standalone tools in the `el-hub` workspace (see `../CLAUDE.md`). It reads a thesis error-list `.xlsx`, **merges and re-distributes** error items across four review sheets by quota, and writes a `_자동분류.xlsx` output with Rich Text diff highlighting. PySide6 GUI + a CLI entry point; pure `openpyxl`, no Google/network dependencies.

## Commands

```bash
uv sync                              # install deps (PySide6, openpyxl, markdown, pyinstaller)
uv run python error_list_gui.py      # run GUI (also: uv run gui)
uv run python error_list_auto_classify.py "오류리스트.xlsx"   # CLI on one file
uv run pyinstaller error_list_gui.spec                       # build the exe
```

No test suite or linter is configured. To exercise the engine directly without the GUI, call `process_error_list(src_path, on_progress=None)` from `error_list_auto_classify.py`.

## Architecture

Three layers, GUI on top of a single-file engine:

```
error_list_gui.py        진입 shim → gui.app.main()
gui/                      PySide6 GUI package
    app.py               ErrorListApp 창 + main(); lists cwd .xlsx, runs worker, opens result
    worker.py            ClassifyWorker (QThread) → wraps process_error_list, emits log/finished
    paths.py             sys.path bootstrap (frozen-exe aware) — makes the engine importable
    config.py            config.json load/save (only key: "theme")
    style.py palette.py fonts.py dialogs.py utils.py   테마·폰트·도움말·아이콘
error_list_auto_classify.py   the whole classification/distribution/diff engine (CLI + process_error_list)
```

**The engine is `error_list_auto_classify.py` — almost all real logic lives there.** The GUI is a thin runner; `worker.py` just calls `process_error_list` on a thread and forwards its `on_progress(pct, msg)` callback to the log view.

### Engine pipeline (`process_error_list`)

1. **Merge** `1차 점검`, `2차 점검`, `품질점검` sheets in-memory by 제어번호 (B열), preserving first-seen order. `merge_inputs_from_ws1_ws2_ws4`. (`3차 점검` is an output-only sheet.)
2. **Clear** the data area (row 8 down, cols A~O) of all four sheets — values only, styles preserved.
3. Per 제어번호 row: parse each fix line into `{err, page, before, after, raw_fix}`, normalize the error type, then **dedup** (`remove_duplicates`: change-pattern signature, cross-script conversion signature, 85% similarity, consecutive-list-number collapse).
4. **Distribute** deduped items across the 4 sheets by quota (`SHEET_TARGET_RATIO`): 1차 is the unbounded catch-all; 2/3/4차 fill toward a paced ratio target; 3/4차 only accept `ALLOWED_TYPES_LATE` (오탈자/띄어쓰기).
5. **Render** each cell's 수정내역 (N열) as `CellRichText` with changed characters in red (`apply_rich_diff_for_bidir` → `render_fix_blocks` → `append_diff_blocks`).
6. **Bulk style** all four sheets (맑은 고딕 10pt, thin borders, alignment, auto row height), then save `{base}_자동분류.xlsx`.

### Layout constants (top of the engine)

`SHEETS` = the four required sheet names · `DATA_START_ROW = 8` · columns L/M/N = 오류항목(12) / 페이지(13) / 수정내역(14) · `SHEET_TARGET_RATIO` quotas · `SIMILARITY_THRESHOLD = 0.85`. Input files **must** contain all four sheets or `process_error_list` raises.

## Gotchas

- **Rich Text whitespace preservation.** openpyxl 3.1.5 drops `xml:space="preserve"` on runs that contain only whitespace, so Excel trims leading/trailing spaces and newlines. The engine works around this by never emitting a whitespace-only run: space-only diffs absorb a neighbor char (`append_diff_blocks`), and line breaks are prepended to the next non-empty run (`apply_rich_diff_for_bidir`). Preserve this when touching diff rendering.
- **cwd-relative file listing.** The GUI lists `.xlsx` from `os.getcwd()` (excluding `~$*` temp files and `_자동분류` outputs). Output is always written next to the source file.
- **Hub integration.** `main()` calls `_register_runtime_state()`, which `importlib`-loads `../proc_state.py` and writes `runtime_state.json` (cleared on exit via `atexit`) so the hub can detect this app even when launched directly. All failures there are swallowed — the app runs fine standalone. `runtime_state.json` is gitignored.
- **`paths.py` must import before the engine.** `worker.py` imports `from . import paths` first so the `sys.path` bootstrap runs and `import error_list_auto_classify` resolves (both in dev and in the PyInstaller bundle, where writable files sit beside the exe and read-only data under `_MEIPASS`).

> Note: `README.md` still describes a Tkinter GUI and a flat file structure; the GUI was rewritten to PySide6 under `gui/`. Trust this file and the source over that README.
