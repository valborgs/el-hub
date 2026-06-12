# -*- coding: utf-8 -*-
"""fonts/ 디렉터리의 폰트를 앱에 등록 — 공용 구현(elhub_ui) 위임."""

from . import paths  # noqa: F401  (sys.path 부트스트랩)
from elhub_ui.fonts import load_application_fonts as _load
from .paths import FONT_DIR


def load_application_fonts() -> tuple[str, str]:
    """fonts/ 의 .ttf/.otf 를 등록하고 (sans_family, mono_family) 반환."""
    return _load(FONT_DIR)
