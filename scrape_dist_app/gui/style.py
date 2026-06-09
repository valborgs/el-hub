# -*- coding: utf-8 -*-
"""QSS 생성·적용, Windows 11 DWM 창 장식 유틸리티."""

import sys

from PySide6.QtWidgets import QApplication

from .palette import PALETTE


def make_qss(theme: str, sans: str, mono: str) -> str:
    p = PALETTE.get(theme, PALETTE["dark"])
    return f"""
/* ── 기반 ─────────────────────────────────────────────────────── */
QWidget {{
    background-color: {p['bg']};
    color: {p['text']};
    font-family: 'Malgun Gothic', sans-serif;
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
    font-family: '{mono}', 'Consolas', monospace;
    font-size: 11px;
}}
QLabel#accent-dot {{
    color: {p['accent']};
    font-size: 16px;
    font-weight: bold;
}}
QLabel#filename {{
    color: {p['text']};
    font-size: 13px;
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

/* ── 실행 버튼 (primary) ───────────────────────────────────────── */
QPushButton#primary {{
    background-color: {p['accent']};
    color: {p['accent_fg']};
    border: none;
    border-radius: 10px;
    font-weight: bold;
    font-size: 14px;
    padding: 0 20px;
}}
QPushButton#primary:hover   {{ background-color: {p['accent_hover']}; }}
QPushButton#primary:pressed {{ background-color: {p['accent_hover']}; }}
QPushButton#primary:disabled {{
    background-color: {p['border']};
    color: {p['text_muted']};
}}

/* ── 초기화 버튼 (ghost) ───────────────────────────────────────── */
QPushButton#ghost {{
    background-color: transparent;
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 10px;
    font-size: 13px;
    padding: 0 16px;
}}
QPushButton#ghost:hover {{
    border-color: {p['accent']};
    color: {p['accent']};
    background-color: transparent;
}}
QPushButton#ghost:pressed {{
    background-color: rgba(128,128,128,0.10);
}}
QPushButton#ghost:disabled {{
    color: {p['text_muted']};
    border-color: {p['border']};
}}

/* ── 아이콘 버튼 (⚙, ?) ──────────────────────────────────────── */
QPushButton#icon {{
    background-color: transparent;
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    font-size: 17px;
    padding: 0;
}}
QPushButton#icon:hover {{
    border-color: {p['accent']};
    color: {p['accent']};
    background-color: transparent;
}}
QPushButton#icon:disabled {{
    color: {p['text_muted']};
    border-color: {p['border']};
}}

/* ── 파일 선택 버튼 ───────────────────────────────────────────── */
QPushButton#file-select {{
    background-color: transparent;
    color: {p['text']};
    border: 1.5px dashed {p['border']};
    border-radius: 8px;
    font-size: 13px;
    padding: 6px 14px;
    text-align: center;
}}
QPushButton#file-select:hover {{
    border-color: {p['accent']};
    background-color: transparent;
}}
QPushButton#file-select:disabled {{
    color: {p['text_muted']};
    border-color: {p['border']};
}}

/* ── 파일 제거 × 버튼 ────────────────────────────────────────── */
QPushButton#file-clear {{
    background-color: transparent;
    color: {p['text_muted']};
    border: none;
    font-size: 15px;
    padding: 0 2px;
}}
QPushButton#file-clear:hover {{ color: {p['text']}; }}

/* ── 파일 표시 필 ────────────────────────────────────────────── */
QFrame#file-pill {{
    background-color: {p['surface_alt']};
    border: 1px solid {p['border']};
    border-radius: 6px;
}}

/* ── 입력 필드 ────────────────────────────────────────────────── */
QLineEdit {{
    background-color: {p['surface_alt']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 6px 10px;
    font-family: '{mono}', 'Consolas', monospace;
    font-size: 13px;
    selection-background-color: {p['accent']};
    selection-color: {p['accent_fg']};
}}
QLineEdit:focus {{ border-color: {p['accent']}; }}
QLineEdit:disabled {{
    background-color: {p['surface']};
    color: {p['text_muted']};
}}

/* ── 라디오 버튼 ─────────────────────────────────────────────── */
QRadioButton {{
    color: {p['text']};
    font-size: 13px;
    spacing: 8px;
    background-color: transparent;
}}
QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {p['border']};
    border-radius: 8px;
    background-color: {p['surface']};
}}
QRadioButton::indicator:checked {{
    background-color: {p['accent']};
    border-color: {p['accent']};
}}
QRadioButton::indicator:hover {{ border-color: {p['accent']}; }}

/* ── 체크박스 ────────────────────────────────────────────────── */
QCheckBox {{
    color: {p['text']};
    spacing: 8px;
    background-color: transparent;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {p['border']};
    border-radius: 4px;
    background-color: {p['surface']};
}}
QCheckBox::indicator:checked {{
    background-color: {p['accent']};
    border-color: {p['accent']};
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

/* ── ToolButton ─────────────────────────────────────────────── */
QToolButton {{
    background-color: transparent;
    border: none;
    color: {p['text_muted']};
    font-size: 12px;
    padding: 0;
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

/* ── 그룹박스 (설정창) ───────────────────────────────────────── */
QGroupBox {{
    background-color: {p['surface']};
    border: 1px solid {p['border']};
    border-radius: 10px;
    margin-top: 12px;
    padding-top: 12px;
    font-weight: 600;
    font-size: 12px;
    color: {p['text']};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 12px;
    color: {p['text']};
    background-color: transparent;
}}

/* ── TextBrowser (도움말) ───────────────────────────────────── */
QTextBrowser {{
    background-color: {p['surface']};
    color: {p['text']};
    border: none;
}}

/* ── MessageBox 버튼 ────────────────────────────────────────── */
QMessageBox QPushButton {{
    min-width: 72px;
    padding: 5px 16px;
}}
"""


def apply_theme(app: QApplication, theme: str, sans: str, mono: str) -> None:
    app.setStyleSheet(make_qss(theme, sans, mono))


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
