# -*- coding: utf-8 -*-
"""메인 GUI 창과 진입점 main()."""

import ctypes
import os
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QFileDialog, QFrame, QHBoxLayout,
    QLabel, QLineEdit, QMessageBox, QPushButton,
    QRadioButton, QSizePolicy, QVBoxLayout, QWidget,
)

from .config import load_config
from .dialogs import HelpDialog, SettingsDialog
from .fonts import load_application_fonts
from .utils import make_emoji_icon
from .style import apply_theme, set_titlebar_color
from .worker import PipelineWorker
from elhub_ui.components import LogPanel

from common.logger import FileLogger  # noqa: E402  (paths.py에서 sys.path 부트스트랩됨)

_HUB_RESTORE_MSG: int = (
    ctypes.windll.user32.RegisterWindowMessageW("ScrapeDistApp.Restore")
    if sys.platform == "win32" and hasattr(ctypes, "windll")
    else 0
)

if sys.platform == "win32" and hasattr(ctypes, "windll"):
    class _WinMSG(ctypes.Structure):
        _fields_ = [
            ("hwnd",    ctypes.c_void_p),
            ("message", ctypes.c_uint),
            ("wParam",  ctypes.c_size_t),
            ("lParam",  ctypes.c_ssize_t),
            ("time",    ctypes.c_ulong),
            ("pt_x",    ctypes.c_long),
            ("pt_y",    ctypes.c_long),
        ]
else:
    _WinMSG = None  # type: ignore[assignment,misc]

_SHEET_LABELS = {1: "서울", 2: "부산", 3: "디파"}


class PipelineApp(QWidget):
    def __init__(self, sans: str = "Malgun Gothic", mono: str = "Consolas"):
        super().__init__()
        self.selected_excel_file: str | None = None
        self._theme = load_config().get("theme", "dark")
        self._sans  = sans
        self._mono  = mono
        self._init_ui()

    def _init_ui(self):
        self.setWindowTitle("오류리스트 작업")
        self.setWindowIcon(make_emoji_icon("🗂️", 64))
        self.setMinimumWidth(500)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        # 상단 2열 카드 행
        top_row = QHBoxLayout()
        top_row.setSpacing(10)
        top_row.addWidget(self._build_file_card(), 1)
        top_row.addWidget(self._build_sheet_card(), 0)
        root.addLayout(top_row)

        root.addWidget(self._build_box_card())
        root.addLayout(self._build_action_row())

        # 접이식 로그 패널 (공용 컴포넌트, 초기 닫힘)
        self.log_panel = LogPanel(mono=self._mono, min_height=260, theme=self._theme)
        root.addWidget(self.log_panel)

    # ── 섹션 빌더 ─────────────────────────────────────────────────────────

    def _build_file_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(14, 12, 14, 12)
        inner.setSpacing(8)

        title = QLabel("작업할 엑셀 파일")
        title.setObjectName("title")
        inner.addWidget(title)

        self.load_file_btn = QPushButton("📋  파일 선택")
        self.load_file_btn.setObjectName("file-select")
        self.load_file_btn.setFixedHeight(36)
        self.load_file_btn.clicked.connect(self._load_excel_file)
        inner.addWidget(self.load_file_btn)

        # 선택된 파일 표시 필 (파일 선택 전 숨김)
        self._file_pill = QFrame()
        self._file_pill.setObjectName("file-pill")
        pill_row = QHBoxLayout(self._file_pill)
        pill_row.setContentsMargins(8, 4, 4, 4)
        pill_row.setSpacing(6)

        dot = QLabel("•")
        dot.setObjectName("accent-dot")
        dot.setFixedWidth(14)

        self._file_name_label = QLabel()
        self._file_name_label.setObjectName("filename")
        self._file_name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        clear_btn = QPushButton("×")
        clear_btn.setObjectName("file-clear")
        clear_btn.setFixedSize(22, 22)
        clear_btn.clicked.connect(self._clear_file)

        pill_row.addWidget(dot)
        pill_row.addWidget(self._file_name_label, 1)
        pill_row.addWidget(clear_btn)
        self._file_pill.setVisible(False)
        inner.addWidget(self._file_pill)

        hint = QLabel(".xlsx  .xlsm   (.xls 미지원)")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignRight)
        inner.addWidget(hint)

        return card

    def _build_sheet_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
        card.setMinimumWidth(120)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(14, 12, 14, 12)
        inner.setSpacing(6)

        title = QLabel("종류 선택")
        title.setObjectName("title")
        inner.addWidget(title)

        self.radio_group = QButtonGroup(self)
        for btn_id, label in _SHEET_LABELS.items():
            rb = QRadioButton(label)
            if btn_id == 1:
                rb.setChecked(True)
                self.radio_seoul = rb
            elif btn_id == 2:
                self.radio_busan = rb
            else:
                self.radio_dipa = rb
            self.radio_group.addButton(rb, btn_id)
            inner.addWidget(rb)

        return card

    def _build_box_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(14, 12, 14, 12)
        inner.setSpacing(8)

        # 헤더 행
        header_row = QHBoxLayout()
        section_title = QLabel("작업 범위")
        section_title.setObjectName("title")
        header_row.addWidget(section_title)
        header_row.addStretch()
        inner.addLayout(header_row)

        # 입력 행
        input_row = QHBoxLayout()
        input_row.setSpacing(8)

        start_col = QVBoxLayout()
        start_col.setSpacing(4)
        start_lbl = QLabel("시작")
        start_lbl.setObjectName("muted")
        self.start_input = QLineEdit()
        self.start_input.setPlaceholderText("B0001")
        start_col.addWidget(start_lbl)
        start_col.addWidget(self.start_input)

        dash = QLabel("—")
        dash.setAlignment(Qt.AlignHCenter | Qt.AlignBottom)
        dash.setContentsMargins(0, 0, 0, 8)

        end_col = QVBoxLayout()
        end_col.setSpacing(4)
        end_lbl = QLabel("종료")
        end_lbl.setObjectName("muted")
        self.end_input = QLineEdit()
        self.end_input.setPlaceholderText("B0010")
        end_col.addWidget(end_lbl)
        end_col.addWidget(self.end_input)

        input_row.addLayout(start_col, 1)
        input_row.addWidget(dash)
        input_row.addLayout(end_col, 1)
        inner.addLayout(input_row)

        return card

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self.run_btn = QPushButton("▶️  실행")
        self.run_btn.setObjectName("primary")
        self.run_btn.setFixedHeight(40)
        self.run_btn.clicked.connect(self._start_pipeline)

        self.reset_btn = QPushButton("🔄  초기화")
        self.reset_btn.setObjectName("ghost")
        self.reset_btn.setFixedHeight(40)
        self.reset_btn.clicked.connect(self._reset_ui)

        self.settings_btn = QPushButton("⚙")
        self.settings_btn.setObjectName("icon")
        self.settings_btn.setFixedSize(40, 40)
        self.settings_btn.setToolTip("환경 설정")
        self.settings_btn.clicked.connect(self._open_settings)

        self.help_btn = QPushButton("❓")
        self.help_btn.setObjectName("icon")
        self.help_btn.setFixedSize(40, 40)
        self.help_btn.setToolTip("사용설명서")
        self.help_btn.clicked.connect(self._open_help)

        row.addWidget(self.run_btn, 3)
        row.addWidget(self.reset_btn, 2)
        row.addStretch()
        row.addWidget(self.settings_btn)
        row.addWidget(self.help_btn)
        return row

    # ── 테마 ──────────────────────────────────────────────────────────────

    def nativeEvent(self, event_type: bytes, message: int):
        if _HUB_RESTORE_MSG and _WinMSG is not None:
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(_WinMSG)).contents
                if msg.message == _HUB_RESTORE_MSG:
                    self._restore_window()
                    return True, 0
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    def _restore_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def showEvent(self, event):
        super().showEvent(event)
        set_titlebar_color(int(self.winId()), self._theme)

    def apply_theme(self, mode: str) -> None:
        self._theme = mode
        apply_theme(QApplication.instance(), mode, self._sans, self._mono)
        self.log_panel.set_theme(mode)
        set_titlebar_color(int(self.winId()), mode)

    # ── 슬롯 ──────────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(current_theme=self._theme, parent=self)
        dlg.theme_changed.connect(self.apply_theme)
        dlg.exec()

    def _open_help(self):
        HelpDialog(parent=self).exec()

    def _load_excel_file(self):
        from .paths import PROJECT_ROOT
        file_path, _ = QFileDialog.getOpenFileName(
            self, "엑셀 파일 선택", PROJECT_ROOT,
            "Excel Files (*.xlsx *.xlsm)",
        )
        if not file_path:
            return
        self.selected_excel_file = file_path
        name = os.path.basename(file_path)
        display = name if len(name) <= 32 else name[:15] + "…" + name[-14:]
        self._file_name_label.setText(display)
        self._file_name_label.setToolTip(file_path)
        self._file_pill.setVisible(True)

    def _clear_file(self):
        self.selected_excel_file = None
        self._file_pill.setVisible(False)
        self._file_name_label.setText("")
        self._file_name_label.setToolTip("")

    def _reset_ui(self):
        self._clear_file()
        self.radio_seoul.setChecked(True)
        self.start_input.clear()
        self.end_input.clear()
        self.log_panel.clear()

    def _log(self, status: str, message: str) -> None:
        self.log_panel.append(status, message)
        if getattr(self, "file_logger", None) is not None:
            self.file_logger.log(status, message)

    def _set_controls_enabled(self, enabled: bool):
        self.run_btn.setEnabled(enabled)
        self.reset_btn.setEnabled(enabled)
        self.settings_btn.setEnabled(enabled)
        self.help_btn.setEnabled(enabled)
        self.load_file_btn.setEnabled(enabled)
        self.run_btn.setText("▶️  실행" if enabled else "⏳  실행 중...")

    def _start_pipeline(self):
        if not self.selected_excel_file:
            QMessageBox.warning(self, "파일 오류", "작업할 엑셀 파일을 먼저 선택해주세요.")
            return
        if not os.path.exists(self.selected_excel_file):
            QMessageBox.warning(self, "파일 오류", "선택한 파일을 찾을 수 없습니다.")
            return
        start_box = self.start_input.text().strip()
        end_box   = self.end_input.text().strip()
        if not start_box or not end_box:
            QMessageBox.warning(self, "입력 오류", "시작 박스와 종료 박스 번호를 모두 입력해주세요.")
            return

        gsheet_idx = self.radio_group.checkedId()
        run_diff   = load_config().get("run_diff", True)

        self.log_panel.clear()
        if not self.log_panel.is_open():
            self.log_panel.toggle()

        self._set_controls_enabled(False)
        self.file_logger = FileLogger()
        self._log("info", "🚀 파이프라인을 시작합니다...")
        self._log("info", f"📂 대상 파일: {os.path.basename(self.selected_excel_file)}")
        self._log("info", f"📊 시트: {_SHEET_LABELS.get(gsheet_idx, '?')}  |  범위: {start_box} ~ {end_box}")
        self._log("info", f"🎨 diff 강조: {'ON' if run_diff else 'OFF'}")

        self.worker = PipelineWorker(
            gsheet_idx, start_box, end_box, self.selected_excel_file, run_diff
        )
        self.worker.log_signal.connect(self._log)
        self.worker.finished_signal.connect(self._on_pipeline_finished)
        self.worker.start()

    def _on_pipeline_finished(self, dst_path: str):
        self._set_controls_enabled(True)
        if getattr(self, "file_logger", None) is not None:
            self.file_logger.close()
            self.file_logger = None

        if dst_path:
            self._log("success", "\n✅ 모든 작업이 완료되었습니다.")
            self._log("info",    f"📁 출력 파일: {os.path.basename(dst_path)}")
            QMessageBox.information(self, "작업 완료", "모든 작업이 완료되었습니다.")
            try:
                if sys.platform.startswith("win"):
                    os.startfile(dst_path)
                elif sys.platform == "darwin":
                    os.system(f"open '{dst_path}'")
                else:
                    os.system(f"xdg-open '{dst_path}'")
            except Exception:
                pass
        else:
            self._log("error", "\n❌ 파이프라인이 오류로 종료되었습니다.")


# ---------------------------------------------------------------------------
# 진입점
# ---------------------------------------------------------------------------
def _register_runtime_state():
    """허브가 외부에서도 실행 여부를 알 수 있도록 실행 상태 파일을 남긴다.

    허브 루트(auto/)의 proc_state 모듈에 위임한다. 종료 시 atexit 로 파일을 지운다.
    프로젝트 구조나 모듈이 없어도 앱 실행에는 지장이 없도록 모든 실패를 무시한다.
    """
    try:
        import atexit
        import importlib.util
        from pathlib import Path

        app_dir = Path(__file__).resolve().parents[1]   # scrape_dist_app/
        ps_path = app_dir.parent / "proc_state.py"      # auto/proc_state.py
        spec = importlib.util.spec_from_file_location("proc_state", ps_path)
        ps = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ps)
        state_file = app_dir / "runtime_state.json"
        ps.write(state_file)
        atexit.register(lambda: ps.clear(state_file))
    except Exception:
        pass


def main():
    app = QApplication(sys.argv)
    _register_runtime_state()
    sans, mono = load_application_fonts()
    initial_theme = load_config().get("theme", "dark")
    apply_theme(app, initial_theme, sans, mono)
    window = PipelineApp(sans=sans, mono=mono)
    window.show()
    sys.exit(app.exec())
