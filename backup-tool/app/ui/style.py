# -*- coding: utf-8 -*-
"""QSS 생성·적용, Windows 11 DWM 창 장식 유틸리티."""

import sys

from PySide6.QtWidgets import QApplication

from .palette import PALETTE


def make_qss(theme: str, sans: str = "Malgun Gothic", mono: str = "Consolas") -> str:
    p = PALETTE.get(theme, PALETTE["dark"])
    return f"""
/* ── 기반 ─────────────────────────────────────────────────────── */
QWidget {{
    background-color: {p['bg']};
    color: {p['text']};
    font-family: '{sans}', 'Malgun Gothic', sans-serif;
    font-size: 13px;
    outline: none;
}}
QDialog {{
    background-color: {p['bg']};
}}

/* ── 카드 프레임 ───────────────────────────────────────────────── */
QFrame#card {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 10px;
}}

/* ── 라벨 ─────────────────────────────────────────────────────── */
QLabel {{
    background-color: transparent;
    border: none;
    color: {p['text']};
}}
QLabel#title {{
    font-weight: 600;
    font-size: 12px;
}}
QLabel#muted {{
    color: {p['text_muted']};
    font-size: 11px;
}}

/* ── 일반 버튼 ─────────────────────────────────────────────────── */
QPushButton {{
    background-color: transparent;
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 5px 14px;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: rgba(128,128,128,0.08);
    border-color: {p['accent']};
}}
QPushButton:pressed {{
    background-color: rgba(128,128,128,0.14);
}}
QPushButton:checked {{
    border-color: {p['accent']};
    background-color: rgba(128,128,128,0.10);
}}
QPushButton:disabled {{
    color: {p['text_muted']};
    border-color: {p['border']};
    background-color: transparent;
}}

/* ── 디렉토리 찾아보기 버튼 ────────────────────────────────────── */
QPushButton#browse-btn {{
    background-color: {p['btn_bg']};
    border-color: {p['border']};
    padding: 5px 2px;
}}
QPushButton#browse-btn:hover {{
    background-color: {p['accent']};
    color: {p['accent_fg']};
    border-color: {p['accent']};
}}
QPushButton#browse-btn:pressed {{
    background-color: {p['accent_hover']};
    color: {p['accent_fg']};
}}
QPushButton#browse-btn:disabled {{
    background-color: {p['surface_alt']};
    color: {p['text_muted']};
}}

/* ── 커스텀 타이틀바 ─────────────────────────────────────────── */
QWidget#title-bar {{
    background-color: {p['bg']};
    border-bottom: 1px solid {p['border']};
}}
QLabel#title-text {{
    font-size: 12px;
    font-weight: 500;
    color: {p['text_muted']};
    background: transparent;
    padding-left: 4px;
}}
QPushButton#wm-btn {{
    border: none;
    border-radius: 0;
    background-color: transparent;
    color: {p['text']};
    font-family: "Segoe MDL2 Assets";
    font-size: 10px;
    padding: 0;
}}
QPushButton#wm-btn:hover {{
    background-color: rgba(128,128,128,0.15);
}}
QPushButton#wm-btn:pressed {{
    background-color: rgba(128,128,128,0.25);
}}
QPushButton#wm-close {{
    border: none;
    border-radius: 0;
    background-color: transparent;
    color: {p['text']};
    font-family: "Segoe MDL2 Assets";
    font-size: 10px;
    padding: 0;
}}
QPushButton#wm-close:hover {{
    background-color: #e81123;
    color: #ffffff;
}}
QPushButton#wm-close:pressed {{
    background-color: #c50f1f;
    color: #ffffff;
}}

/* ── 툴바 아이콘 버튼 (설정 / 제외 / 테마) ───────────────────── */
QPushButton#toolbar-btn {{
    border: 1px solid transparent;
    border-radius: 6px;
    background-color: transparent;
    padding: 0;
    font-size: 14px;
}}
QPushButton#toolbar-btn:hover {{
    background-color: rgba(128,128,128,0.12);
    border-color: {p['border']};
}}
QPushButton#toolbar-btn:pressed {{
    background-color: rgba(128,128,128,0.20);
}}
QPushButton#toolbar-btn:checked {{
    background-color: {p['accent']};
    color: {p['accent_fg']};
    border-color: {p['accent']};
}}

/* ── 구글 드라이브 아이콘 토글 버튼 ──────────────────────────── */
QPushButton#gdrive-toggle {{
    border: 1px solid {p['border']};
    border-radius: 6px;
    background-color: {p['surface']};
    padding: 0;
}}
QPushButton#gdrive-toggle:hover {{
    border-color: {p['accent']};
    background-color: {p['surface']};
}}
QPushButton#gdrive-toggle:checked {{
    border: 2px solid {p['accent']};
    background-color: {p['surface_alt']};
}}
QPushButton#gdrive-toggle:disabled {{
    background-color: {p['surface_alt']};
    border-color: {p['border']};
}}

/* ── 입력 필드 ────────────────────────────────────────────────── */
QLineEdit {{
    background-color: {p['surface_alt']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 13px;
    selection-background-color: {p['accent']};
    selection-color: {p['accent_fg']};
}}
QLineEdit:focus {{ border-color: {p['accent']}; }}
QLineEdit:read-only {{
    background-color: {p['surface']};
    color: {p['text_muted']};
}}
QLineEdit:disabled {{
    background-color: {p['surface']};
    color: {p['text_muted']};
}}

/* ── 그룹박스 ────────────────────────────────────────────────── */
QGroupBox {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 10px;
    margin-top: 20px;
    font-weight: 600;
    font-size: 12px;
    color: {p['text']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    top: 0;
    left: 8px;
    padding: 0 2px;
    color: {p['text']};
    background-color: transparent;
}}

/* ── 목록 위젯 ────────────────────────────────────────────────── */
QListWidget {{
    background-color: {p['surface_alt']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 4px;
    outline: none;
}}
QListWidget::item {{
    border-radius: 4px;
    padding: 3px 6px;
}}
QListWidget::item:selected {{
    background-color: {p['accent']};
    color: {p['accent_fg']};
}}
QListWidget::item:hover:!selected {{
    background-color: rgba(128,128,128,0.08);
}}

/* ── 로그 뷰 ─────────────────────────────────────────────────── */
QPlainTextEdit#log {{
    background-color: {p['surface_alt']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 8px;
    font-family: '{mono}', 'Consolas', monospace;
    font-size: 10pt;
    selection-background-color: {p['accent']};
    selection-color: {p['accent_fg']};
}}

/* ── 진행 다이얼로그 ─────────────────────────────────────────── */
QProgressDialog {{
    background-color: {p['bg']};
}}
QProgressDialog QLabel {{
    color: {p['text']};
}}
QProgressBar {{
    background-color: {p['surface_alt']};
    border: 1px solid {p['border']};
    border-radius: 4px;
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: {p['accent']};
    border-radius: 4px;
}}

/* ── 메시지박스 ──────────────────────────────────────────────── */
QMessageBox {{
    background-color: {p['bg']};
}}
QMessageBox QPushButton {{
    min-width: 72px;
    padding: 5px 16px;
}}

/* ── 스크롤바 ────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
    border: none;
}}
QScrollBar::handle:vertical {{
    background: {p['border']};
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{ background: {p['text_muted']}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
    border: none;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

/* ── 메뉴 ────────────────────────────────────────────────────── */
QMenu {{
    background-color: {p['surface']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 20px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: rgba(128,128,128,0.10);
    color: {p['accent']};
}}
QMenu::separator {{
    height: 1px;
    background: {p['border']};
    margin: 4px 8px;
}}
"""


def apply_theme(app: QApplication, theme: str,
                sans: str = "Malgun Gothic", mono: str = "Consolas") -> None:
    app.setStyleSheet(make_qss(theme, sans, mono))


def set_window_rounded(hwnd: int) -> None:
    """Windows 11 DWM API로 창 모서리를 네이티브 둥근 스타일로 설정한다."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        DWMWA_WINDOW_CORNER_PREFERENCE = 33
        DWMWCP_ROUND = 2
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_WINDOW_CORNER_PREFERENCE,
            ctypes.byref(ctypes.c_int(DWMWCP_ROUND)),
            ctypes.sizeof(ctypes.c_int),
        )
    except Exception:
        pass


def set_titlebar_color(hwnd: int, theme: str) -> None:
    """Windows 11 DWM API로 타이틀바 배경·텍스트 색을 팔레트에 맞게 설정."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        p = PALETTE.get(theme, PALETTE["dark"])

        def to_colorref(hex_color: str) -> int:
            h = hex_color.lstrip("#")
            r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
            return b << 16 | g << 8 | r

        DWMWA_CAPTION_COLOR = 35
        DWMWA_TEXT_COLOR    = 36
        dwmapi = ctypes.windll.dwmapi
        for attr, color in (
            (DWMWA_CAPTION_COLOR, to_colorref(p["bg"])),
            (DWMWA_TEXT_COLOR,    to_colorref(p["text"])),
        ):
            dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(ctypes.c_int(color)),
                ctypes.sizeof(ctypes.c_int),
            )
    except Exception:
        pass
