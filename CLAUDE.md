# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`el-hub` (점검 납품) is a **workspace of independent PySide6 desktop tools** for a thesis-review/delivery pipeline, plus a launcher (`hub.py`) that runs and monitors them and shares one Google OAuth session across them. The three tools live in subdirectories and are otherwise standalone projects:

- `backup-tool/` — real-time folder backup + hourly Google Drive sync
- `scrape_dist_app/` — Google Sheets scraping → Excel auto-distribution/formatting
- `error_list_dist/` — Excel error-list merge, classification, and Rich Text diff

Each subproject has its **own** `CLAUDE.md`/`README.md` and its own dependency setup — read those before working inside one. This file covers only the hub and the cross-cutting mechanisms that tie the workspace together.

## Commands

```bash
uv sync              # install hub deps into ./.venv (Python 3.14)
uv run python hub.py # run the launcher (from repo root)
```

There is **no build step, test suite, or linter**. The whole workspace is now **uv-based and pinned to Python 3.14**: the hub has its own `pyproject.toml`/`uv.lock`/`.venv` at the repo root, and each subproject (`backup-tool`, `scrape_dist_app`, `error_list_dist`) is an **independent** uv project with its own `pyproject.toml`/`uv.lock`/`.venv`. There is intentionally **no uv workspace** — the four projects are resolved and locked separately, so run uv commands from each project's directory (or with `--directory`). The hub depends on `PySide6`, `google-auth`, `google-auth-oauthlib`, `google-api-python-client`, `keyring`, and `pywin32`.

This is a **Windows-only** workspace in practice: process detection, window focusing, and token encryption all use Win32 APIs via `ctypes`/`pywin32`. Non-win32 branches exist as no-op fallbacks but the app is not exercised there.

## Hub architecture

`hub.py` is a single-window PySide6 dashboard. `HubWindow` builds one `AppCard` per tool plus a Google-account row and a 출퇴근 (clock-in/out) row. Shared root modules carry all the cross-app coordination:

| Module | Role |
|--------|------|
| `hub.py` | Launcher UI, per-app cards, auth/commute rows, all Win32 window-focusing logic |
| `hub_auth.py` | Cancelable Google OAuth flow; login/logout/get_email/get_credentials |
| `secure_store.py` | DPAPI-encrypt the OAuth token and store it in Windows Credential Manager |
| `proc_state.py` | Read/write `runtime_state.json` to detect whether an app is running |
| `elhub_ui/` | **Shared design system** (palette, base QSS, DWM helpers, fonts, icons, dialogs, widgets) used by the hub *and* all three subapps |

### How a card decides "실행" vs "열기"

An `AppCard` polls once per second. It treats an app as running if **either** the hub's own `subprocess.Popen` is alive **or** the app left a live `runtime_state.json`. The latter is how the hub detects instances it didn't launch (e.g. started directly). Clicking "열기" focuses the existing window via `_focus_pid_window` (enumerates the process tree, picks the largest Python top-level window, handles minimized/tray-hidden cases — tray restore is posted as a `RegisterWindowMessage` the app listens for, keyed by `restore_msg_key`).

`_resolve_app_cmd` picks each subapp's interpreter: prefer its `.venv\Scripts\python.exe`, else `uv run python`, else the current interpreter. All three subapps (including `backup-tool`) now go through this and run from their own `.venv`, so the hub's environment no longer needs to satisfy any subapp's imports.

### Shared OAuth session (the central design point)

All apps share **one** Google login. The token is stored DPAPI-encrypted in Windows Credential Manager under service `AutoHub-GoogleOAuth` (not a plaintext file), via `secure_store.py`. `hub_auth.is_logged_in()` just checks for the credential's presence (no network), which the hub polls every 3 s to stay in sync when *another* app logs in/out. Only the `refresh_token` and client fields are persisted (to fit the Credential Manager blob size limit); access tokens are re-minted on demand and the rotated refresh token is written back.

Two constraints that are easy to break:

1. **`secure_store.py` constants are duplicated.** `scrape_dist_app` packages as a separate exe and keeps a copy of the same logic/constants at `scrape_dist_app/core/secure_token.py`. The `_SERVICE` / `_ACCOUNT` / `_ENTROPY` constants must be **identical** across both, or apps stop sharing the session. Change one → change the other.

2. **Subapps load these root modules by absolute path.** Because each app runs with its cwd in its own subdirectory (not the repo root), `auto/` is not on `sys.path`. So `backup-tool` etc. load `hub_auth`/`secure_store`/`proc_state` via `importlib.util.spec_from_file_location` against the file's real location — not a normal `import`. `hub_auth.py` itself loads `secure_store.py` the same way for the same reason. Don't convert these to plain imports.

### Process liveness via `runtime_state.json`

`proc_state.write(path, **extra)` records `{pid, create_time, ...}`; `read_live(path)` returns the dict **only if** that pid is still alive *and* its process creation time matches (guards against PID reuse). Each app writes this on start and clears it on exit; the hub reads it both to render card state and to check app-specific flags — e.g. `_is_gdrive_backup_active()` reads backup-tool's `gdrive_enabled` flag to warn before logout. `runtime_state.json` is gitignored.

### Shared design system (`elhub_ui/`)

The hub and all three subapps share **one** design system, single-sourced in the root `elhub_ui/` package:

| Module | Provides |
|--------|----------|
| `palette.py` | Unified `PALETTE` (light/dark, all keys merged: common + `btn_bg` + `green`/`red`) and `LOG_COLORS` |
| `style.py` | `make_base_qss(theme, sans, mono)` (common selectors only), `apply_theme(app, theme, sans, mono, extra_qss="")`, and DWM helpers `set_titlebar_color`/`set_titlebar_dark`/`set_window_rounded` |
| `fonts.py` | `load_application_fonts(font_dir)` |
| `icons.py` | `make_emoji_icon` |
| `dialogs.py` | `HelpDialog(readme_path)`; `SettingsDialog` base (theme row + `add_extra_rows`/`read_extra`/`write_extra` hooks) |
| `components.py` | `DotIndicator`, `make_wave_frames`, `LogPanel` (collapsible log) |

How consumers wire in:

- **App-specific QSS** lives at each app, not in the base. `apply_theme` concatenates `make_base_qss(...) + extra_qss`, so each app injects only its own object-name selectors (e.g. scrape's `#file-pill`, error_list's `#file-list`, backup-tool's `#title-bar`/`#gdrive-toggle`). The hub does the same with `_HUB_QSS` (`#launch`, `#cardScroll`).
- **Each subapp's `gui/palette.py`, `gui/style.py`, `gui/fonts.py`, `gui/utils.py`, `gui/dialogs.py`, `gui/config.py` are now thin shims** that re-export / wrap `elhub_ui`, supplying app-local params (FONT_DIR, CONFIG_FILE, README_PATH, the `extra_qss`). The app windows still `from .style import apply_theme` etc. — unchanged.
- **sys.path bootstrap.** Like the other root modules, `auto/` is not on a subapp's path. The scrape/error_list `gui/paths.py` and backup-tool's `app/__init__.py` insert the repo root into `sys.path` so `import elhub_ui` resolves. The hub runs from the root and imports it directly.
- **Source-run only.** The subapps are launched from source via their `.venv` python — there is **no PyInstaller build** in use, so `elhub_ui` needs no spec/bundling changes. (If exe builds resume, add the repo root to the spec `pathex` and `elhub_ui.*` to `hiddenimports`.)

### Threading

All blocking work (OAuth login/logout, email fetch) runs on daemon threads; results come back to the UI through `_AuthSignals` Qt signals. Background threads must never touch widgets directly.

## Secrets & files

- `credentials/oauth_client.json` — Google OAuth desktop-client file (required for login). Gitignored.
- `timesheet.txt` — tab-separated clock-in/out log (`timestamp\temail\t출근|퇴근`), appended by the hub. Gitignored.
- `wordcount.py` — unrelated standalone helper that counts lines/chars in `.txt` files under a `pdf/` tree; not part of the hub.
