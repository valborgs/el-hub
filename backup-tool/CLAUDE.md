# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

`backup-tool` is one of the standalone apps in the `el-hub` workspace (see `../CLAUDE.md`); it shares that workspace's Google session.

## Commands

```bash
uv sync                 # install deps into .venv (Python 3.14): PySide6, watchdog, google-*, keyring, pywin32
uv run python main.py   # run the app
```

This is an **independent uv project** (its own `pyproject.toml`/`uv.lock`/`.venv`), not part of a uv workspace. The hub launches it via its `.venv` interpreter like the other subapps.

No build step, test suite, or linter is configured.

## Architecture

Real-time folder backup desktop app (Python + PySide6). Monitors a source directory and copies changed files to a dated backup folder (`backup_dir/YYYYMMDD/`). Deleted source files are **never removed** from the backup (safe/accumulative mode). Optionally mirrors the local backup to Google Drive on a 1-hour cadence, uploading only files changed since the previous cycle.

### Module responsibilities

| Module | Role |
|--------|------|
| `main.py` | Entry point — registers Windows AppUserModelID (toast name), installs excepthook, starts Qt |
| `app/config.py` | `BackupConfig` dataclass — JSON load/save, `validate()` (path existence + no source/backup overlap) |
| `app/errors.py` | Exception hierarchy (`BackupError`, `ConfigError`, `ValidationError`, `SyncError`) |
| `app/backup_engine.py` | `copy_file`, `initial_sync`, include/exclude filtering, emits `path_cb` per copy |
| `app/watcher.py` | `WatcherService` — wraps `watchdog.Observer`, emits `path_cb` per copy |
| `app/gdrive.py` | Drive upload; **auth delegated to shared `hub_auth`** (see below) |
| `app/logger.py` | `SessionLogger` — daily rotating logs under `log/` |
| `app/runtime_state.py` | Writes `runtime_state.json` so the hub can detect this app (see below) |
| `app/ui/signals.py` | `WorkerSignals` — Qt signals bridging background threads → main thread |
| `app/ui/main_window.py` | Full PySide6 UI, state machine, system tray, Drive integration |

> `app/ui/main_window_backup.py` is a stale, unused copy of an earlier `main_window`. `main.py` imports `app.ui.main_window`; the `_backup` file is dead — don't edit it.

### Threading model

Background threads (initial sync, watchdog observer, Drive login/logout/upload) must **never** touch Qt widgets directly. All cross-thread communication goes through `WorkerSignals` (`app/ui/signals.py`): `log`, `error`, `backup` (one-line event), `path_backed_up` (abs path → Drive upload queue), `sync_finished(success, failed, fatal_msg)`, `gdrive_login_finished(success, email_or_err)`.

### Include / exclude filtering

`backup_engine._match_single_pattern` governs both lists with path-aware glob semantics:
- pattern with `/` → matched against the full relative path (`temp/cache` covers everything under it)
- pattern with a wildcard (`* ? [`) → applied to every path component (`*.py` at any depth)
- plain name → directory names match at any depth; bare file names match only at the root
`includes` (when non-empty) whitelists; an empty `includes` means "all files". `excludes` then removes. On top of both, `is_temp_artifact` always drops Office temp/lock files: `~$*`, `*.tmp`, and 8-hex-digit extensionless names.

### Google Drive integration

- **OAuth desktop flow** (personal Gmail); service accounts are not used (no storage quota).
- **Auth is delegated to the shared `hub_auth` module** (`../hub_auth.py`), lazy-loaded via `importlib` from `parents[2]/hub_auth.py` in `gdrive._auth()`, then delegating `is_logged_in`/`login`/`get_email`/`cancel_login`/`get_credentials`. `hub_auth` reads `oauth_client.json` under `auto/credentials/` and stores the token **DPAPI-encrypted in Windows Credential Manager** (service `AutoHub-GoogleOAuth`) — shared across the workspace apps, auto-refreshed, no plaintext token file.
- Toggle ON runs `_gdrive_login_worker` on a thread: validates the cached token via `gdrive.get_email()`, and on `PermissionError` falls back to `gdrive.login()` (opens browser; cancelable via `QProgressDialog` → `gdrive.cancel_login()`). Success reveals the upload-folder picker; failure/cancel reverts the toggle. Toggle OFF hides the picker and stops the timer — it does **not** revoke the token (logout is the hub's job).
- The 1-hour `QTimer` (`_GDRIVE_INTERVAL_MS`) starts after `_on_sync_finished` succeeds and fires `_run_gdrive_upload` immediately + hourly. It snapshots `_gdrive_pending` (queued backup paths), clears it, makes them relative to `backup_dir`, and calls `gdrive.upload_files(parent_folder_id=...)`. Failed paths are re-emitted via `path_backed_up` for next-cycle retry.
- The upload **target folder** is user-chosen via `_GDriveFolderDialog` (browses Drive via `gdrive.list_subfolders`), persisted to `config.json` as `gdrive_folder_id` / `gdrive_folder_path`; empty id falls back to `gdrive.ROOT_FOLDER_ID` ("root" = My Drive). `upload_files` caches intermediate folder IDs within a cycle and reuses same-named folders/files instead of duplicating.

### Hub integration (runtime state)

`config.json` is persistent settings; `runtime_state.json` is *live* state for the current process. `app/runtime_state.py` wraps the workspace-root `proc_state` module (lazy `importlib`-loaded from `parents[2]/proc_state.py`) and records `{pid, create_time, watching, gdrive_enabled}`. `main_window` calls `_update_runtime_state()` on every state change and `runtime_state.clear()` on exit. The hub reads this to show running status and, crucially, checks `gdrive_enabled` to warn before a logout that would break an active Drive backup. All writes fail silently — the app runs fine standalone. `runtime_state.json` is gitignored.

### Input lock during a session

While initial sync or watching is active, `_set_inputs_enabled(False)` disables all editable controls (source/backup line edits, both 찾아보기 buttons, include/exclude lists and their add/delete buttons, the Drive toggle); they re-enable on stop.
