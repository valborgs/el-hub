# -*- coding: utf-8 -*-
"""파이프라인을 백그라운드 스레드에서 실행하는 워커."""

import os

from PySide6.QtCore import QThread, Signal

# paths import 가 sys.path 부트스트랩을 수행하므로 pipeline import 보다 먼저
from .paths import PROJECT_ROOT

from common.pipeline import run_pipeline  # noqa: E402  (sys.path 부트스트랩 후 import)


class PipelineWorker(QThread):
    log_signal      = Signal(str, str)   # (status, message)
    finished_signal = Signal(str)        # dst_path (빈 문자열이면 실패)

    def __init__(self, gsheet_idx: int, start_box: str, end_box: str,
                 excel_file: str, run_diff: bool = True):
        super().__init__()
        self.gsheet_idx = gsheet_idx
        self.start_box  = start_box
        self.end_box    = end_box
        self.excel_file = excel_file
        self.run_diff   = run_diff

    def run(self):
        def worker_log(status: str, message: str) -> None:
            self.log_signal.emit(status, message)

        original_cwd = os.getcwd()
        os.chdir(PROJECT_ROOT)
        try:
            dst_path = run_pipeline(
                excel_file   = self.excel_file,
                gsheet_index = self.gsheet_idx,
                start_box    = self.start_box,
                end_box      = self.end_box,
                log_callback = worker_log,
                run_diff     = self.run_diff,
            )
            self.finished_signal.emit(dst_path)
        except Exception as e:
            worker_log("error", f"❌ {e}")
            self.finished_signal.emit("")
        finally:
            os.chdir(original_cwd)
