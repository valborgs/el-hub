# -*- coding: utf-8 -*-
"""메인 GUI 창과 진입점 main()."""

import os
import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QListWidget,
    QListWidgetItem, QMessageBox, QPlainTextEdit, QPushButton,
    QSizePolicy, QToolButton, QVBoxLayout, QWidget,
)

from .config import load_config
from .dialogs import HelpDialog, SettingsDialog
from .fonts import load_application_fonts
from .utils import make_emoji_icon
from .palette import LOG_COLORS
from .style import apply_theme, set_titlebar_color
from .worker import ClassifyWorker


def list_xlsx_files(directory: str) -> list[str]:
    """디렉터리의 작업 대상 .xlsx 파일 목록(정렬). 임시·출력 파일은 제외."""
    files = []
    try:
        for name in os.listdir(directory):
            if not name.lower().endswith(".xlsx"):
                continue
            if name.startswith("~$"):
                continue  # Excel 임시 파일 제외
            base, _ext = os.path.splitext(name)
            if base.endswith("_자동분류"):
                continue  # 출력물은 선택 목록에서 제외
            files.append(name)
    except Exception:
        pass
    return sorted(files)


class ErrorListApp(QWidget):
    def __init__(self, sans: str = "Malgun Gothic", mono: str = "Consolas"):
        super().__init__()
        self._theme = load_config().get("theme", "dark")
        self._sans  = sans
        self._mono  = mono
        self._workdir = os.getcwd()
        self.worker: ClassifyWorker | None = None
        self._init_ui()
        self._refresh_file_list()

    def _init_ui(self):
        self.setWindowTitle("오류리스트 자동분류")
        self.setWindowIcon(make_emoji_icon("🗂️", 64))
        self.setMinimumWidth(500)

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        root.addWidget(self._build_file_card())
        root.addLayout(self._build_action_row())
        root.addWidget(self._build_log_section())

        # 초기: 로그창 닫힘
        self.log_output.setVisible(False)
        self._log_toggle_btn.setArrowType(Qt.RightArrow)
        self._log_container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # ── 섹션 빌더 ─────────────────────────────────────────────────────────

    def _build_file_card(self) -> QFrame:
        card = QFrame()
        card.setObjectName("card")
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        inner = QVBoxLayout(card)
        inner.setContentsMargins(14, 12, 14, 12)
        inner.setSpacing(8)

        # 헤더 행: 제목 + 새로고침
        header_row = QHBoxLayout()
        title = QLabel("작업할 엑셀 파일")
        title.setObjectName("title")
        header_row.addWidget(title)
        header_row.addStretch()
        self.refresh_btn = QPushButton("🔄  새로고침")
        self.refresh_btn.setObjectName("subtle")
        self.refresh_btn.clicked.connect(self._refresh_file_list)
        header_row.addWidget(self.refresh_btn)
        inner.addLayout(header_row)

        # 파일 목록
        self.file_list = QListWidget()
        self.file_list.setObjectName("file-list")
        self.file_list.setMinimumHeight(180)
        self.file_list.itemDoubleClicked.connect(lambda _i: self._start_classify())
        inner.addWidget(self.file_list, 1)

        hint = QLabel("현재 폴더의 .xlsx 파일   (출력물·임시파일 제외)")
        hint.setObjectName("muted")
        hint.setAlignment(Qt.AlignRight)
        inner.addWidget(hint)

        return card

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(8)

        self.run_btn = QPushButton("▶️  실행")
        self.run_btn.setObjectName("primary")
        self.run_btn.setFixedHeight(40)
        self.run_btn.clicked.connect(self._start_classify)

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

    def _build_log_section(self) -> QWidget:
        container = QWidget()
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._log_container = container

        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        # 토글 헤더
        header = QWidget()
        header.setCursor(Qt.PointingHandCursor)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(2, 4, 2, 4)
        header_row.setSpacing(6)

        self._log_toggle_btn = QToolButton()
        self._log_toggle_btn.setArrowType(Qt.RightArrow)
        self._log_toggle_btn.setStyleSheet(
            "QToolButton { border: none; background: transparent; }"
        )

        log_title = QLabel("진행 상황")
        log_title.setObjectName("title")

        header_row.addWidget(self._log_toggle_btn)
        header_row.addWidget(log_title)
        header_row.addStretch()

        self._log_toggle_btn.clicked.connect(self._toggle_log)
        header.mousePressEvent = lambda _: self._toggle_log()
        vbox.addWidget(header)

        # 로그 본문
        self.log_output = QPlainTextEdit()
        self.log_output.setObjectName("log")
        self.log_output.setReadOnly(True)
        self.log_output.setMinimumHeight(220)
        self.log_output.setFont(QFont(self._mono, 10))
        vbox.addWidget(self.log_output)

        return container

    # ── 로그 토글 ──────────────────────────────────────────────────────────

    def _toggle_log(self) -> None:
        closing = self.log_output.isVisible()
        if not closing:
            self._size_before_log = self.size()
        self.log_output.setVisible(not closing)
        self._log_toggle_btn.setArrowType(Qt.RightArrow if closing else Qt.DownArrow)
        self._log_container.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed if closing else QSizePolicy.Expanding,
        )
        if closing and hasattr(self, "_size_before_log"):
            saved = self._size_before_log
            QTimer.singleShot(0, lambda: self.resize(saved))

    # ── 테마 ──────────────────────────────────────────────────────────────

    def showEvent(self, event):
        super().showEvent(event)
        set_titlebar_color(int(self.winId()), self._theme)

    def apply_theme(self, mode: str) -> None:
        self._theme = mode
        apply_theme(QApplication.instance(), mode, self._sans, self._mono)
        self.log_output.setFont(QFont(self._mono, 10))
        set_titlebar_color(int(self.winId()), mode)

    # ── 슬롯 ──────────────────────────────────────────────────────────────

    def _open_settings(self):
        dlg = SettingsDialog(current_theme=self._theme, parent=self)
        dlg.theme_changed.connect(self.apply_theme)
        dlg.exec()

    def _open_help(self):
        HelpDialog(parent=self).exec()

    def _refresh_file_list(self):
        self._workdir = os.getcwd()
        files = list_xlsx_files(self._workdir)
        self.file_list.clear()
        for f in files:
            QListWidgetItem(f, self.file_list)
        self._log("info", f"📂 {os.path.basename(self._workdir) or self._workdir} · .xlsx 파일 {len(files)}개")

    def _selected_file(self) -> str | None:
        item = self.file_list.currentItem()
        return item.text() if item else None

    def _reset_ui(self):
        self.file_list.clearSelection()
        self.file_list.setCurrentItem(None)
        self.log_output.clear()
        self._refresh_file_list()

    def _log(self, status: str, message: str) -> None:
        colors = LOG_COLORS.get(self._theme, LOG_COLORS["dark"])
        color  = colors.get(status, colors["info"])
        escaped = (
            message
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        self.log_output.appendHtml(f'<span style="color:{color};">{escaped}</span>')
        self.log_output.verticalScrollBar().setValue(
            self.log_output.verticalScrollBar().maximum()
        )

    def _set_controls_enabled(self, enabled: bool):
        self.run_btn.setEnabled(enabled)
        self.reset_btn.setEnabled(enabled)
        self.refresh_btn.setEnabled(enabled)
        self.settings_btn.setEnabled(enabled)
        self.help_btn.setEnabled(enabled)
        self.file_list.setEnabled(enabled)
        self.run_btn.setText("▶️  실행" if enabled else "⏳  실행 중...")

    def _start_classify(self):
        if self.worker is not None and self.worker.isRunning():
            return
        sel = self._selected_file()
        if not sel:
            QMessageBox.warning(self, "알림", "작업할 .xlsx 파일을 선택해주세요.")
            return
        src_path = os.path.join(self._workdir, sel)
        if not os.path.exists(src_path):
            QMessageBox.warning(self, "파일 오류", "선택한 파일을 찾을 수 없습니다.")
            self._refresh_file_list()
            return

        self.log_output.clear()
        if not self.log_output.isVisible():
            self._toggle_log()

        self._set_controls_enabled(False)
        self._log("info", "🚀 자동분류를 시작합니다...")
        self._log("info", f"📂 대상 파일: {sel}")

        self.worker = ClassifyWorker(src_path)
        self.worker.log_signal.connect(self._log)
        self.worker.finished_signal.connect(self._on_finished)
        self.worker.start()

    def _on_finished(self, result):
        self._set_controls_enabled(True)

        if result is None:
            self._log("error", "\n❌ 작업이 오류로 종료되었습니다.")
            QMessageBox.critical(self, "오류", "작업 중 오류가 발생했습니다.\n진행 상황 로그를 확인해주세요.")
            self._refresh_file_list()
            return

        dst_path = result.get("dst_path")
        total = result.get("total_rows", 0)
        copied = result.get("copied_without_processing", False)

        self._log("info", "")
        if copied:
            self._log("warning", "ℹ️  처리할 데이터가 없어 원본을 복사하여 저장했습니다.")
        else:
            self._log("success", f"✅ 총 {total}행 처리 완료.")
        if dst_path:
            self._log("info", f"📁 출력 파일: {os.path.basename(dst_path)}")

        # 결과 파일 열기
        try:
            if sys.platform.startswith("win"):
                os.startfile(dst_path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f"open '{dst_path}'")
            else:
                os.system(f"xdg-open '{dst_path}'")
        except Exception:
            pass

        self._refresh_file_list()


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

        app_dir = Path(__file__).resolve().parents[1]   # error_list_dist/
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
    window = ErrorListApp(sans=sans, mono=mono)
    window.show()
    sys.exit(app.exec())
