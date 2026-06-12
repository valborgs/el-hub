# -*- coding: utf-8 -*-
"""QSS 적용 — 공용 베이스(elhub_ui) + 이 앱 고유 셀렉터.

앱 고유 위젯(파일 선택 버튼·선택 필·파일명 라벨 등)만 `_extra_qss` 로 정의하고,
나머지는 elhub_ui 의 베이스 QSS 와 DWM 헬퍼를 그대로 쓴다.
"""

from . import paths  # noqa: F401  (sys.path 부트스트랩)
from elhub_ui.palette import PALETTE
from elhub_ui.style import apply_theme as _apply_theme
from elhub_ui.style import set_titlebar_color  # noqa: F401  (app.py 재노출용)


def _extra_qss(theme: str, mono: str) -> str:
    p = PALETTE.get(theme, PALETTE["dark"])
    return f"""
/* ── 강조 점 · 파일명 라벨 ─────────────────────────────────────── */
QLabel#accent-dot {{
    color: {p['accent']};
    font-size: 16px;
    font-weight: bold;
}}
QLabel#filename {{
    color: {p['text']};
    font-size: 13px;
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
"""


def apply_theme(app, theme: str, sans: str = "Malgun Gothic", mono: str = "Consolas") -> None:
    _apply_theme(app, theme, sans, mono, extra_qss=_extra_qss(theme, mono))
