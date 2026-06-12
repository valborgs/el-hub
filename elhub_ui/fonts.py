# -*- coding: utf-8 -*-
"""폰트 디렉터리의 .ttf/.otf 를 앱에 등록."""

import os

from PySide6.QtGui import QFontDatabase


def load_application_fonts(font_dir: str) -> tuple[str, str]:
    """`font_dir` 의 .ttf/.otf 를 등록하고 (sans_family, mono_family) 반환.

    JetBrains 계열 폰트가 있으면 mono 로 채택한다.
    """
    sans_family = "Malgun Gothic"
    mono_family = "Consolas"

    if font_dir and os.path.isdir(font_dir):
        for fname in sorted(os.listdir(font_dir)):
            if not fname.lower().endswith((".ttf", ".otf")):
                continue
            fid = QFontDatabase.addApplicationFont(os.path.join(font_dir, fname))
            if fid < 0:
                continue
            for fam in QFontDatabase.applicationFontFamilies(fid):
                if "JetBrains" in fam and mono_family == "Consolas":
                    mono_family = fam

    return sans_family, mono_family
