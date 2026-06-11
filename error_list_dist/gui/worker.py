# -*- coding: utf-8 -*-
"""자동분류를 백그라운드 스레드에서 실행하는 워커."""

from PySide6.QtCore import QThread, Signal

# paths import 가 sys.path 부트스트랩을 수행하므로 분류 모듈 import 보다 먼저
from . import paths  # noqa: F401

from error_list_auto_classify import process_error_list  # noqa: E402


class ClassifyWorker(QThread):
    log_signal      = Signal(str, str)   # (status, message)
    finished_signal = Signal(object)     # 결과 dict (실패 시 None)

    def __init__(self, src_path: str):
        super().__init__()
        self.src_path = src_path

    def run(self):
        def on_progress(pct: int, msg: str) -> None:
            self.log_signal.emit("info", f"[{pct:3d}%] {msg}")

        try:
            result = process_error_list(self.src_path, on_progress=on_progress)
            self.finished_signal.emit(result)
        except Exception as e:
            self.log_signal.emit("error", f"❌ {e}")
            self.finished_signal.emit(None)
