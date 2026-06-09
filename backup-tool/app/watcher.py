"""watchdog 기반 실시간 파일 변경 감시 래퍼.

이벤트 핸들러의 모든 콜백은 try/except 로 감싸 예외가 watchdog 의 Observer
스레드를 죽이지 않게 한다. 오류는 error_cb 로 UI 에 전달한다.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from .backup_engine import copy_file, dated_root, is_excluded, is_included, is_temp_artifact
from .config import BackupConfig
from .errors import BackupError, SyncError

LogCallback = Callable[[str], None]
ErrorCallback = Callable[[str], None]
BackupCallback = Callable[[str], None]
# 백업된 파일의 절대경로(백업 디렉토리 아래)를 알리는 콜백 — Drive 업로드 큐에 사용
PathCallback = Callable[[Path], None]

# 같은 파일에 대한 중복 이벤트를 무시하는 최소 간격(초).
# 에디터가 저장 시 modified 이벤트를 여러 번 쏘는 것을 완화한다.
_DEBOUNCE_SECONDS = 0.5


class BackupEventHandler(FileSystemEventHandler):
    """파일 생성/수정/이동 시 백업 폴더로 복사하는 핸들러.

    누적 모드이므로 on_deleted 는 처리하지 않는다(백업본 보존).
    """

    def __init__(
        self,
        config: BackupConfig,
        log_cb: LogCallback,
        error_cb: ErrorCallback,
        backup_cb: BackupCallback,
        path_cb: PathCallback | None = None,
    ):
        super().__init__()
        self._source = Path(config.source_dir).resolve()
        self._backup = Path(config.backup_dir).resolve()
        self._excludes = list(config.excludes)
        self._includes = list(config.includes)
        self._log_cb = log_cb
        self._error_cb = error_cb
        self._backup_cb = backup_cb
        self._path_cb = path_cb
        self._last_handled: dict[str, float] = {}

    def _rel_path(self, abs_path: str) -> str | None:
        """절대경로를 대상 디렉토리 기준 상대경로(posix)로 변환한다."""
        try:
            return Path(abs_path).resolve().relative_to(self._source).as_posix()
        except ValueError:
            return None

    def _should_skip(self, rel: str) -> bool:
        """임시 파일, 제외/지정 패턴, 디바운스에 의해 건너뛸지 판단한다."""
        if is_temp_artifact(rel):
            return True
        if is_excluded(rel, self._excludes):
            return True
        if not is_included(rel, self._includes):
            return True
        now = time.monotonic()
        last = self._last_handled.get(rel)
        if last is not None and now - last < _DEBOUNCE_SECONDS:
            return True
        self._last_handled[rel] = now
        return False

    def _backup_path(self, abs_path: str, action: str) -> None:
        """단일 파일을 백업 폴더로 복사하고 결과를 로그로 남긴다."""
        rel = self._rel_path(abs_path)
        if rel is None:
            return
        if self._should_skip(rel):
            return
        try:
            # 변경이 발생한 날짜의 하위 폴더(YYYYMMDD)로 백업한다.
            target = dated_root(self._backup)
            copy_file(self._source, target, rel)
            self._backup_cb(f"{action}: {rel}")
            if self._path_cb is not None:
                try:
                    self._path_cb(target / rel)
                except Exception:
                    pass  # 콜백 오류가 감시를 멈추지 않게 한다
        except SyncError as err:
            self._error_cb(err.detail())

    # --- watchdog 콜백. 각 메서드 전체를 try/except 로 감싼다. ---

    def on_created(self, event: FileSystemEvent) -> None:
        try:
            if event.is_directory:
                return
            self._backup_path(event.src_path, "생성")
        except Exception as err:  # 어떤 예외도 Observer 스레드를 죽이지 않게
            self._error_cb(f"파일 생성 이벤트 처리 중 오류: {err}")

    def on_modified(self, event: FileSystemEvent) -> None:
        try:
            if event.is_directory:
                return
            self._backup_path(event.src_path, "수정")
        except Exception as err:
            self._error_cb(f"파일 수정 이벤트 처리 중 오류: {err}")

    def on_moved(self, event: FileSystemEvent) -> None:
        try:
            if event.is_directory:
                return
            # 누적 모드: 이전 위치의 백업본은 그대로 두고, 새 위치로 복사한다.
            self._backup_path(event.dest_path, "이동")
        except Exception as err:
            self._error_cb(f"파일 이동 이벤트 처리 중 오류: {err}")


class WatcherService:
    """watchdog Observer 의 시작/중지를 관리한다. stop() 은 멱등하다."""

    def __init__(self) -> None:
        self._observer: Observer | None = None

    @property
    def is_running(self) -> bool:
        return self._observer is not None

    def start(
        self,
        config: BackupConfig,
        log_cb: LogCallback,
        error_cb: ErrorCallback,
        backup_cb: BackupCallback,
        path_cb: PathCallback | None = None,
    ) -> None:
        """감시를 시작한다. 이미 실행 중이면 먼저 중지한다.

        Observer 시작 실패는 BackupError 로 변환해 던진다.
        """
        if self._observer is not None:
            self.stop()

        handler = BackupEventHandler(config, log_cb, error_cb, backup_cb, path_cb)
        observer = Observer()
        try:
            observer.schedule(handler, config.source_dir, recursive=True)
            observer.start()
        except OSError as err:
            raise BackupError(
                f"실시간 감시를 시작할 수 없습니다: {config.source_dir}"
            ) from err
        except Exception as err:
            raise BackupError("실시간 감시를 시작하는 중 오류가 발생했습니다.") from err

        self._observer = observer
        log_cb("실시간 감시를 시작했습니다.")

    def stop(self) -> None:
        """감시를 중지한다. 실행 중이 아니어도 안전하게 동작한다."""
        observer = self._observer
        self._observer = None
        if observer is None:
            return
        try:
            observer.stop()
            observer.join(timeout=5)
        except Exception:
            # 종료 중 발생하는 오류는 무시한다 — 이미 멈추는 중이다.
            pass
