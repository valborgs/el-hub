# -*- coding: utf-8 -*-
"""fonts/ 디렉터리의 폰트를 앱에 등록."""

import os

from PySide6.QtGui import QFontDatabase

from .paths import FONT_DIR


def load_application_fonts() -> tuple[str, str]:
    """fonts/ 의 .ttf/.otf 를 등록하고 (sans_family, mono_family) 반환."""
    sans_family = "Malgun Gothic"
    mono_family = "Consolas"

    if os.path.isdir(FONT_DIR):
        for fname in sorted(os.listdir(FONT_DIR)):
            if not fname.lower().endswith((".ttf", ".otf")):
                continue
            fid = QFontDatabase.addApplicationFont(os.path.join(FONT_DIR, fname))
            if fid < 0:
                continue
            for fam in QFontDatabase.applicationFontFamilies(fid):
                if "JetBrains" in fam and mono_family == "Consolas":
                    mono_family = fam

    return sans_family, mono_family
