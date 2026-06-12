# -*- coding: utf-8 -*-
"""환경 설정·도움말 팝업 — 공용 베이스(elhub_ui) 위에 이 앱 항목을 얹는다."""

from PySide6.QtWidgets import QCheckBox, QLineEdit

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
    """시트 URL · diff 강조 · 테마 설정."""

    LABEL_WIDTH = 110

    def __init__(self, current_theme: str, parent=None):
        super().__init__(current_theme, load_config, save_config, parent)
        self.setMinimumWidth(480)

    def add_extra_rows(self, layout, make_row) -> None:
        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("https://docs.google.com/spreadsheets/d/...")
        layout.addLayout(make_row("시트 URL:", self.url_input))

        self.diff_checkbox = QCheckBox("수정내역 diff 강조 적용")
        layout.addLayout(make_row("diff 강조:", self.diff_checkbox))

    def read_extra(self, cfg: dict) -> None:
        self.url_input.setText(cfg.get("SPREADSHEET_URL", ""))
        self.diff_checkbox.setChecked(cfg.get("run_diff", True))

    def write_extra(self, cfg: dict) -> None:
        cfg["SPREADSHEET_URL"] = self.url_input.text().strip()
        cfg["run_diff"] = self.diff_checkbox.isChecked()
