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
python hub.py        # run the launcher (from repo root)
```

There is **no build step, test suite, or linter**, and there is **no root `requirements.txt`** despite the README mentioning one. The hub depends on `PySide6`, `google-auth`, `google-auth-oauthlib`, `google-api-python-client`, `keyring`, and `pywin32`; these must be present in whatever interpreter runs `hub.py`. Subprojects manage their own deps (`backup-tool/requirements.txt`; `scrape_dist_app` and `error_list_dist` use `uv`/`pyproject.toml` + `.venv`).

This is a **Windows-only** workspace in practice: process detection, window focusing, and token encryption all use Win32 APIs via `ctypes`/`pywin32`. Non-win32 branches exist as no-op fallbacks but the app is not exercised there.

## Hub architecture

`hub.py` is a single-window PySide6 dashboard. `HubWindow` builds one `AppCard` per tool plus a Google-account row and a 출퇴근 (clock-in/out) row. Three shared root modules carry all the cross-app coordination:

| Module | Role |
|--------|------|
| `hub.py` | Launcher UI, per-app cards, auth/commute rows, all Win32 window-focusing logic |
| `hub_auth.py` | Cancelable Google OAuth flow; login/logout/get_email/get_credentials |
| `secure_store.py` | DPAPI-encrypt the OAuth token and store it in Windows Credential Manager |
| `proc_state.py` | Read/write `runtime_state.json` to detect whether an app is running |

### How a card decides "실행" vs "열기"

An `AppCard` polls once per second. It treats an app as running if **either** the hub's own `subprocess.Popen` is alive **or** the app left a live `runtime_state.json`. The latter is how the hub detects instances it didn't launch (e.g. started directly). Clicking "열기" focuses the existing window via `_focus_pid_window` (enumerates the process tree, picks the largest Python top-level window, handles minimized/tray-hidden cases — tray restore is posted as a `RegisterWindowMessage` the app listens for, keyed by `restore_msg_key`).

`_resolve_app_cmd` picks each subapp's interpreter: prefer its `.venv\Scripts\python.exe`, else `uv run python`, else the current interpreter. **Exception:** `backup-tool` is launched with `sys.executable` (the hub's own interpreter), so the hub's environment must satisfy backup-tool's imports too.

### Shared OAuth session (the central design point)

All apps share **one** Google login. The token is stored DPAPI-encrypted in Windows Credential Manager under service `AutoHub-GoogleOAuth` (not a plaintext file), via `secure_store.py`. `hub_auth.is_logged_in()` just checks for the credential's presence (no network), which the hub polls every 3 s to stay in sync when *another* app logs in/out. Only the `refresh_token` and client fields are persisted (to fit the Credential Manager blob size limit); access tokens are re-minted on demand and the rotated refresh token is written back.

Two constraints that are easy to break:

1. **`secure_store.py` constants are duplicated.** `scrape_dist_app` packages as a separate exe and keeps a copy of the same logic/constants at `scrape_dist_app/core/secure_token.py`. The `_SERVICE` / `_ACCOUNT` / `_ENTROPY` constants must be **identical** across both, or apps stop sharing the session. Change one → change the other.

2. **Subapps load these root modules by absolute path.** Because each app runs with its cwd in its own subdirectory (not the repo root), `auto/` is not on `sys.path`. So `backup-tool` etc. load `hub_auth`/`secure_store`/`proc_state` via `importlib.util.spec_from_file_location` against the file's real location — not a normal `import`. `hub_auth.py` itself loads `secure_store.py` the same way for the same reason. Don't convert these to plain imports.

### Process liveness via `runtime_state.json`

`proc_state.write(path, **extra)` records `{pid, create_time, ...}`; `read_live(path)` returns the dict **only if** that pid is still alive *and* its process creation time matches (guards against PID reuse). Each app writes this on start and clears it on exit; the hub reads it both to render card state and to check app-specific flags — e.g. `_is_gdrive_backup_active()` reads backup-tool's `gdrive_enabled` flag to warn before logout. `runtime_state.json` is gitignored.

### Threading

All blocking work (OAuth login/logout, email fetch) runs on daemon threads; results come back to the UI through `_AuthSignals` Qt signals. Background threads must never touch widgets directly.

## Secrets & files

- `credentials/oauth_client.json` — Google OAuth desktop-client file (required for login). Gitignored.
- `timesheet.txt` — tab-separated clock-in/out log (`timestamp\temail\t출근|퇴근`), appended by the hub. Gitignored.
- `wordcount.py` — unrelated standalone helper that counts lines/chars in `.txt` files under a `pdf/` tree; not part of the hub.
