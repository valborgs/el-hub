# -*- coding: utf-8 -*-
"""공용 위젯 컴포넌트.

- DotIndicator   : 원형 상태 표시 도트 (허브 카드·계정 행)
- make_wave_frames: 실행 중 파도 애니메이션 프레임 생성기
- LogPanel       : 접이식 로그 패널 (scrape·error_list 공통)
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPlainTextEdit, QSizePolicy, QToolButton,
    QVBoxLayout, QWidget,
)

from .palette import LOG_COLORS, PALETTE


# ── 상태 도트 ────────────────────────────────────────────────────────────────

class DotIndicator(QWidget):
    """원형 상태 표시 도트 (실행 중=green, 대기=text_muted)."""

    def __init__(self, theme: str = "dark", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(10, 10)
        self._theme = theme
        self._running = False
        self._color = QColor(PALETTE.get(theme, PALETTE["dark"])["text_muted"])

    def set_running(self, running: bool) -> None:
        self._running = running
        p = PALETTE.get(self._theme, PALETTE["dark"])
        self._color = QColor(p["green"] if running else p["text_muted"])
        self.update()

    def set_theme(self, theme: str) -> None:
        self._theme = theme
        self.set_running(self._running)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(self._color)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(0, 0, 10, 10)


# ── 파도 애니메이션 프레임 ───────────────────────────────────────────────────

def make_wave_frames(slots: int = 5, n_frames: int = 16) -> list[str]:
    """사인 파도 애니메이션 프레임을 생성한다. 파도는 오른쪽으로 흐른다."""
    levels = "▁▂▃▄▅▆▇█"
    n = len(levels)
    period = 4.0  # 파장 (슬롯 단위)
    frames = []
    for p in range(n_frames):
        shift = p * period / n_frames
        row = ""
        for i in range(slots):
            val = 0.5 + 0.5 * math.sin(2 * math.pi * (i - shift) / period)
            row += levels[min(n - 1, round(val * (n - 1)))]
        frames.append(row)
    return frames


# ── 접이식 로그 패널 ─────────────────────────────────────────────────────────

class LogPanel(QWidget):
    """헤더 클릭으로 펼치고 접는 로그 패널.

    scrape·error_list 의 `_build_log_section`/`_toggle_log`/`_log` 를 캡슐화한다.
    `file_logger` 속성에 FileLogger 를 지정하면 append 시 함께 기록한다.
    """

    def __init__(
        self,
        title: str = "진행 상황",
        mono: str = "Consolas",
        min_height: int = 260,
        theme: str = "dark",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme = theme
        self.file_logger = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        # 토글 헤더
        header = QWidget()
        header.setCursor(Qt.PointingHandCursor)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(2, 4, 2, 4)
        header_row.setSpacing(6)

        self._toggle_btn = QToolButton()
        self._toggle_btn.setArrowType(Qt.RightArrow)
        self._toggle_btn.setStyleSheet(
            "QToolButton { border: none; background: transparent; }"
        )

        log_title = QLabel(title)
        log_title.setObjectName("title")

        header_row.addWidget(self._toggle_btn)
        header_row.addWidget(log_title)
        header_row.addStretch()

        self._toggle_btn.clicked.connect(self.toggle)
        header.mousePressEvent = lambda _: self.toggle()
        vbox.addWidget(header)

        # 로그 본문 (초기 닫힘)
        self._log = QPlainTextEdit()
        self._log.setObjectName("log")
        self._log.setReadOnly(True)
        self._log.setMinimumHeight(min_height)
        self._log.setFont(QFont(mono, 10))
        self._log.setVisible(False)
        vbox.addWidget(self._log)

        self._size_before: object = None

    # ── 상태 ──────────────────────────────────────────────────────────────

    def is_open(self) -> bool:
        return self._log.isVisible()

    def set_theme(self, theme: str) -> None:
        self._theme = theme

    def toggle(self) -> None:
        win = self.window()
        closing = self._log.isVisible()
        if not closing and win is not None:
            self._size_before = win.size()
        self._log.setVisible(not closing)
        self._toggle_btn.setArrowType(Qt.RightArrow if closing else Qt.DownArrow)
        self.setSizePolicy(
            QSizePolicy.Expanding,
            QSizePolicy.Fixed if closing else QSizePolicy.Expanding,
        )
        if closing and self._size_before is not None and win is not None:
            saved = self._size_before
            QTimer.singleShot(0, lambda: win.resize(saved))

    # ── 로그 ──────────────────────────────────────────────────────────────

    def clear(self) -> None:
        self._log.clear()

    def append(self, status: str, message: str) -> None:
        colors = LOG_COLORS.get(self._theme, LOG_COLORS["dark"])
        color = colors.get(status, colors["info"])
        escaped = (
            message
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        self._log.appendHtml(f'<span style="color:{color};">{escaped}</span>')
        self._log.verticalScrollBar().setValue(
            self._log.verticalScrollBar().maximum()
        )
        if self.file_logger is not None:
            self.file_logger.log(status, message)
