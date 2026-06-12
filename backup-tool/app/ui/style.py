# -*- coding: utf-8 -*-
"""QSS 적용 — 공용 베이스(elhub_ui) + 이 앱 고유 셀렉터.

커스텀 타이틀바·툴바 버튼·드라이브 토글·메뉴·진행 다이얼로그 등 이 앱만의 위젯을
`_extra_qss` 로 정의하고, 나머지는 elhub_ui 의 베이스 QSS 와 DWM 헬퍼를 쓴다.
"""

from elhub_ui.palette import PALETTE
from elhub_ui.style import apply_theme as _apply_theme
from elhub_ui.style import set_titlebar_color, set_window_rounded  # noqa: F401  (재노출)


def _extra_qss(theme: str) -> str:
    p = PALETTE.get(theme, PALETTE["dark"])
    return f"""
/* ── 일반 버튼 체크 상태 ───────────────────────────────────────── */
QPushButton:checked {{
    border-color: {p['accent']};
    background-color: rgba(128,128,128,0.10);
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

/* ── 그룹박스 (이 앱 전용 마진) ──────────────────────────────── */
QGroupBox {{
    margin-top: 20px;
    padding-top: 0;
}}
QGroupBox::title {{
    top: 0;
    left: 8px;
    padding: 0 2px;
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


def apply_theme(app, theme: str, sans: str = "Malgun Gothic", mono: str = "Consolas") -> None:
    _apply_theme(app, theme, sans, mono, extra_qss=_extra_qss(theme))
