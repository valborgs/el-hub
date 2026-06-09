"""감시 세션별 로그 파일 기록.

감시를 시작할 때마다 프로젝트 최상위의 log/ 폴더에 타임스탬프가 붙은 새 로그
파일을 만들고, UI 로그가 갱신될 때마다 같은 내용을 파일에도 덧붙인다.

UI 로그 콜백은 모두 Qt 메인 스레드에서 실행되므로 별도 잠금은 두지 않는다.
로그 기록 실패가 백업 자체를 막아서는 안 되므로, 쓰기 단계의 예외는 삼킨다.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .errors import BackupError

# 로그 폴더: 프로젝트 최상위(backup-tool/) 아래 log/
LOG_DIR = Path(__file__).resolve().parent.parent / "log"


class SessionLogger:
    """감시 세션 하나에 대응하는 로그 파일을 관리한다."""

    def __init__(self, log_dir: Path = LOG_DIR):
        self._log_dir = log_dir
        self._file = None
        self._path: Path | None = None

    @property
    def path(self) -> Path | None:
        """현재 열려 있는 로그 파일 경로. 열려 있지 않으면 None."""
        return self._path

    def start(self) -> Path:
        """log/ 폴더에서 오늘 날짜 로그 파일을 열어 이어쓴다. 이미 열려 있으면 먼저 닫는다.

        파일명은 backup_YYYYMMDD.log 형식이라 하루에 몇 번을 재시작해도 같은 파일에
        모든 로그가 누적된다. 파일이 이미 있으면 append 모드로 끝에 이어쓴다.

        폴더 생성이나 파일 열기에 실패하면 BackupError 를 던진다.
        """
        self.stop()
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d")
            path = self._log_dir / f"backup_{stamp}.log"
            self._file = open(path, "a", encoding="utf-8")
        except OSError as err:
            raise BackupError(
                f"로그 파일을 만들 수 없습니다: {self._log_dir}"
            ) from err
        self._path = path
        self.write(f"=== 감시 시작: {datetime.now():%Y-%m-%d %H:%M:%S} ===")
        return path

    def write(self, message: str) -> None:
        """로그 한 줄을 파일에 덧붙인다.

        파일이 열려 있지 않거나 쓰기에 실패하면 조용히 넘어간다 — 로그 기록
        실패 때문에 백업이 멈춰서는 안 되기 때문이다.
        """
        if self._file is None:
            return
        try:
            self._file.write(message + "\n")
            self._file.flush()
        except OSError:
            pass

    def stop(self) -> None:
        """로그 파일을 닫는다. 열려 있지 않아도 안전하다(멱등)."""
        if self._file is None:
            return
        try:
            self._file.write(
                f"=== 감시 종료: {datetime.now():%Y-%m-%d %H:%M:%S} ===\n"
            )
            self._file.close()
        except OSError:
            pass
        finally:
            self._file = None
            self._path = None
