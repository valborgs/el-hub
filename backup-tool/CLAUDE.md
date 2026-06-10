# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
pip install -r requirements.txt   # install dependencies (PySide6, watchdog, google-*)
python main.py                    # run the app
```

No build step, test suite, or linter is configured.

## Architecture

Real-time folder backup desktop app (Python + PySide6). Monitors a source directory and copies changed files to a dated backup folder (`backup_dir/YYYYMMDD/`). Deleted source files are **never removed** from the backup (safe/accumulative mode).

Optionally mirrors the local backup to Google Drive on a 1-hour cadence, uploading only files that changed since the previous cycle.

### Module responsibilities

| Module | Role |
|--------|------|
| `main.py` | Entry point — sets Windows AppUserModelID, installs exception hook, starts Qt app |
| `app/config.py` | `BackupConfig` dataclass — JSON load/save, path validation |
| `app/errors.py` | Exception hierarchy (`BackupError`, `ConfigError`, `ValidationError`, `SyncError`) |
| `app/backup_engine.py` | `copy_file`, `initial_sync`, exclusion filtering, emits `path_cb` on each successful copy |
| `app/watcher.py` | `WatcherService` — wraps `watchdog.Observer` for real-time monitoring, emits `path_cb` on each successful copy |
| `app/gdrive.py` | OAuth user-account login (desktop flow), `upload_files` for change-set uploads, `upload_folder` for full-folder uploads, login/logout/token persistence |
| `app/logger.py` | `SessionLogger` — daily rotating log files under `log/` |
| `app/ui/signals.py` | `WorkerSignals` — Qt signals bridging background threads → main thread |
| `app/ui/main_window.py` | Full PySide6 UI, state machine, system tray, Google Drive integration |

### Data flow

```
MainWindow loads config.json
  → if credentials/token.json exists: toggle ON, fetch email in background
  → User clicks "감시 시작"
  → validate() + save config.json
  → clear pending Drive upload queue
  → background thread: initial_sync() copies all non-excluded files,
      each copy emits path_backed_up signal → queue
  → WorkerSignals.sync_finished → main thread
  → WatcherService starts (watchdog.Observer)
  → file event → copy_file() → dated backup folder,
      each copy emits path_backed_up signal → queue
  → if Google Drive toggle is ON:
      _start_gdrive_timer() runs upload immediately + every hour
      upload_files() pushes only queued (changed) files
      failed paths are re-emitted to the queue for next-cycle retry
  → WorkerSignals.log/error/backup → UI log view + log file + tray notification
```

### Threading model

Background threads (initial sync, watchdog observer, Drive login/logout/upload) must never touch Qt widgets directly. All cross-thread communication goes through `WorkerSignals` (defined in `app/ui/signals.py`) which emits Qt signals consumed on the main thread.

Signals currently defined:
- `log(str)`, `error(str)` — log/error messages
- `backup(str)` — one-line backup event message (e.g. `"수정: 문서/보고서.docx"`)
- `path_backed_up(str)` — absolute path of a file that was backed up; consumed to populate the Drive upload queue
- `sync_finished(int, int, str)` — `(success, failed, fatal_msg_or_empty)`
- `gdrive_login_finished(bool, str)` — `(success, email_or_error)`
- `gdrive_logout_finished(bool, str)` — `(success, error_msg)`

### Google Drive integration

- Authentication uses **OAuth desktop flow** (personal Gmail). Service accounts are not used (they have no storage quota).
- `credentials/oauth_client.json` — user-provided OAuth client (download from Google Cloud Console → "Desktop app").
- `credentials/token.json` — auto-generated after first consent; cached and auto-refreshed.
- Toggle state mirrors token presence: turning the toggle ON triggers the OAuth flow; turning it OFF revokes the token and deletes `token.json`.
- The 1-hour timer (`QTimer`, `_GDRIVE_INTERVAL_MS = 60 * 60 * 1000`) starts after `_on_sync_finished` succeeds and fires `_run_gdrive_upload` immediately + every hour.
- `_run_gdrive_upload` snapshots `_gdrive_pending` (set of absolute backup file paths), clears it, converts to paths relative to `backup_dir`, and hands them to `gdrive.upload_files`. Failed paths are re-emitted via `path_backed_up` for retry next cycle.
- The upload **target folder** is user-chosen (not hardcoded): the Drive group's "업로드 폴더 선택" button opens `_GDriveFolderDialog`, which browses the Drive tree via `gdrive.list_subfolders` (lazy, background-threaded with a generation guard). The choice is persisted to `config.json` as `gdrive_folder_id` / `gdrive_folder_path` and passed to `upload_files(parent_folder_id=...)`. An empty id falls back to `gdrive.ROOT_FOLDER_ID` ("root" = My Drive).
- `upload_files` caches intermediate Drive folder IDs within a single cycle and reuses (rather than duplicates) same-named folders/files on Drive.

### Exclusion filtering

`backup_engine.py` applies two layers:
1. User-defined glob patterns from `BackupConfig.excludes`
2. Auto-excluded Office temp artifacts: `~$*`, `*.tmp`, 8-hex-digit filenames

### Input lock during a session

While initial sync or watching is active, `_set_inputs_enabled(False)` disables all editable controls: source/backup line edits, both "찾아보기" buttons, exclude list, exclude add/delete buttons, and the Google Drive toggle. They are re-enabled on stop.
