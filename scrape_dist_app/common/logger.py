import os
from datetime import datetime


class FileLogger:
    def __init__(self):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        log_dir = os.path.join(base, "log")
        os.makedirs(log_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._file = open(os.path.join(log_dir, f"{timestamp}.log"), "w", encoding="utf-8")

    def log(self, status: str, message: str) -> None:
        level_map = {"input": "INPUT", "error": "ERROR", "info": "INFO"}
        level = level_map.get(status, "INFO")
        self._file.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] [{level}] {message}\n")
        self._file.flush()

    def close(self) -> None:
        if self._file and not self._file.closed:
            self._file.close()
