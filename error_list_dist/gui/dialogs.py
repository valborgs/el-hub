# -*- coding: utf-8 -*-
"""환경 설정·도움말 팝업 — 공용 베이스(elhub_ui) 위임.

이 앱의 설정 항목은 테마뿐이라 베이스 SettingsDialog 를 그대로 쓴다.
"""

from . import paths  # noqa: F401  (sys.path 부트스트랩)
from elhub_ui.dialogs import HelpDialog as _HelpDialog
from elhub_ui.dialogs import SettingsDialog as _SettingsDialog
from .config import load_config, save_config
from .paths import README_PATH


class HelpDialog(_HelpDialog):
    """README.md 도움말 팝업 (이 앱의 README 경로 주입)."""

    def __init__(self, parent=None):
        super().__init__(README_PATH, parent)


class SettingsDialog(_SettingsDialog):
    """테마 설정만 제공."""

    def __init__(self, current_theme: str, parent=None):
        super().__init__(current_theme, load_config, save_config, parent)
