# -*- coding: utf-8 -*-
"""QSS 적용 — 공용 베이스(elhub_ui) + 이 앱 고유 셀렉터.

앱 고유 위젯(새로고침 버튼·파일 목록)만 `_extra_qss` 로 정의하고, 나머지는 elhub_ui
의 베이스 QSS 와 DWM 헬퍼를 그대로 쓴다.
"""

from . import paths  # noqa: F401  (sys.path 부트스트랩)
from elhub_ui.palette import PALETTE
from elhub_ui.style import apply_theme as _apply_theme
from elhub_ui.style import set_titlebar_color  # noqa: F401  (app.py 재노출용)


def _extra_qss(theme: str, mono: str) -> str:
    p = PALETTE.get(theme, PALETTE["dark"])
    return f"""
/* ── 새로고침 버튼 (subtle) ───────────────────────────────────── */
QPushButton#subtle {{
    background-color: transparent;
    color: {p['text_muted']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    font-size: 12px;
    padding: 4px 12px;
}}
QPushButton#subtle:hover {{
    border-color: {p['accent']};
    color: {p['accent']};
    background-color: transparent;
}}
QPushButton#subtle:disabled {{
    color: {p['text_muted']};
    border-color: {p['border']};
}}

/* ── 파일 목록 (QListWidget) ──────────────────────────────────── */
QListWidget#file-list {{
    background-color: {p['surface_alt']};
    color: {p['text']};
    border: 1px solid {p['border']};
    border-radius: 8px;
    padding: 4px;
    font-family: '{mono}', 'Consolas', monospace;
    font-size: 12px;
    outline: none;
}}
QListWidget#file-list::item {{
    padding: 5px 8px;
    border-radius: 6px;
}}
QListWidget#file-list::item:hover {{
    background-color: rgba(128,128,128,0.10);
}}
QListWidget#file-list::item:selected {{
    background-color: {p['accent']};
    color: {p['accent_fg']};
}}
"""


def apply_theme(app, theme: str, sans: str = "Malgun Gothic", mono: str = "Consolas") -> None:
    _apply_theme(app, theme, sans, mono, extra_qss=_extra_qss(theme, mono))
