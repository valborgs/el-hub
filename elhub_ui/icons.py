# -*- coding: utf-8 -*-
"""아이콘 생성 유틸리티."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap


def make_emoji_icon(emoji: str, size: int = 64) -> QIcon:
    """이모지를 그려 QIcon 으로 반환한다(창/다이얼로그 아이콘용)."""
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    painter = QPainter(px)
    painter.setFont(QFont("Segoe UI Emoji", int(size * 0.7)))
    painter.drawText(px.rect(), Qt.AlignCenter, emoji)
    painter.end()
    return QIcon(px)
