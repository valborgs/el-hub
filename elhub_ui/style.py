# -*- coding: utf-8 -*-
"""공용 QSS 합성·적용 및 Windows 11 DWM 창 장식 유틸리티.

`make_base_qss` 는 네 프로젝트가 공유하는 셀렉터만 담는다. 앱 고유 셀렉터
(파일 필·툴바·타이틀바·드라이브 토글 등)는 각 앱이 `extra_qss` 로 주입한다.
"""

import sys

from PySide6.QtWidgets import QApplication

from .palette import PALETTE


def make_base_qss(theme: str, sans: str = "Malgun Gothic", mono: str = "Consolas") -> str:
    """네 프로젝트 공통 셀렉터를 담은 베이스 QSS 를 생성한다."""
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
    font-family: '{mono}', 'Consolas', monospace;
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
QPushButton:disabled {{
    color: {p['text_muted']};
    border-color: {p['border']};
    background-color: transparent;
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
QLineEdit:read-only {{
    background-color: {p['surface']};
    color: {p['text_muted']};
}}
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

/* ── 그룹박스 ────────────────────────────────────────────────── */
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
QMessageBox {{
    background-color: {p['bg']};
}}
QMessageBox QPushButton {{
    min-width: 72px;
    padding: 5px 16px;
}}
"""


def apply_theme(
    app: QApplication,
    theme: str,
    sans: str = "Malgun Gothic",
    mono: str = "Consolas",
    extra_qss: str = "",
) -> None:
    """베이스 QSS 에 앱 고유 QSS(`extra_qss`)를 덧붙여 적용한다."""
    app.setStyleSheet(make_base_qss(theme, sans, mono) + (extra_qss or ""))


# ── Windows 11 DWM 창 장식 ──────────────────────────────────────────────────

def _to_colorref(hex_color: str) -> int:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return b << 16 | g << 8 | r


def set_titlebar_color(hwnd: int, theme: str) -> None:
    """타이틀바 배경·텍스트 색을 팔레트에 맞게 설정."""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        p = PALETTE.get(theme, PALETTE["dark"])
        DWMWA_CAPTION_COLOR = 35
        DWMWA_TEXT_COLOR    = 36
        dwmapi = ctypes.windll.dwmapi
        for attr, color in (
            (DWMWA_CAPTION_COLOR, _to_colorref(p["bg"])),
            (DWMWA_TEXT_COLOR,    _to_colorref(p["text"])),
        ):
            dwmapi.DwmSetWindowAttribute(
                hwnd, attr, ctypes.byref(ctypes.c_int(color)),
                ctypes.sizeof(ctypes.c_int),
            )
    except Exception:
        pass


def set_titlebar_dark(hwnd: int, theme: str = "dark") -> None:
    """다크 모드 타이틀바(immersive dark)를 켜고 캡션 색을 맞춘다.

    프레임 있는 일반 창(허브)에서 showEvent 시 호출한다.
    """
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        p = PALETTE.get(theme, PALETTE["dark"])
        dwmapi = ctypes.windll.dwmapi
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        DWMWA_CAPTION_COLOR = 35
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(ctypes.c_int(1)), ctypes.sizeof(ctypes.c_int),
        )
        dwmapi.DwmSetWindowAttribute(
            hwnd, DWMWA_CAPTION_COLOR,
            ctypes.byref(ctypes.c_int(_to_colorref(p["bg"]))),
            ctypes.sizeof(ctypes.c_int),
        )
    except Exception:
        pass


def set_window_rounded(hwnd: int) -> None:
    """창 모서리를 네이티브 둥근 스타일로 설정(프레임리스 창용)."""
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
