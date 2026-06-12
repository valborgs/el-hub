# -*- coding: utf-8 -*-
"""공용 도움말·환경설정 다이얼로그.

- HelpDialog(readme_path)       : README.md 를 마크다운 렌더링 (밝은 배경 고정)
- SettingsDialog(load/save 콜백) : 테마 행을 가진 베이스. 앱이 확장 훅으로 추가 행을 끼움
"""

import re

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QRadioButton, QSizePolicy, QSpacerItem,
    QTextBrowser, QVBoxLayout, QWidget,
)

from .icons import make_emoji_icon
from .palette import HELP_ACCENT, HELP_MUTED


# ---------------------------------------------------------------------------
# 도움말 팝업
# ---------------------------------------------------------------------------
_HELP_HTML_STYLE = f"""
<style>
  body   {{ font-family: 'Malgun Gothic', sans-serif; font-size: 13px;
           line-height: 1.7; background: transparent; margin: 12px; }}
  h1     {{ font-size: 18px; border-bottom: 2px solid {HELP_ACCENT}; padding-bottom: 6px; }}
  h2     {{ font-size: 15px; border-bottom: 1px solid {HELP_MUTED}; padding-bottom: 4px; margin-top: 20px; }}
  h3     {{ font-size: 13px; margin-top: 14px; }}
  code   {{ background: rgba(123,138,110,0.15); padding: 1px 5px;
           border-radius: 3px; font-family: Consolas, monospace; }}
  pre    {{ background: rgba(123,138,110,0.10); padding: 10px; border-radius: 4px;
           font-family: Consolas, monospace; font-size: 12px; }}
  table  {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
  th, td {{ border: 1px solid {HELP_MUTED}; padding: 5px 10px; }}
  th     {{ background: rgba(123,138,110,0.15); }}
  blockquote {{ border-left: 3px solid {HELP_ACCENT}; margin: 4px 0;
               padding: 4px 12px; color: #6B6B6B; }}
</style>
"""


class HelpDialog(QDialog):
    def __init__(self, readme_path: str, parent=None):
        super().__init__(parent)
        self._readme_path = readme_path
        self.setWindowTitle("사용설명서")
        self.resize(680, 620)
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(0)

        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        # 도움말 창은 테마와 무관하게 항상 밝은 배경 유지
        browser.setStyleSheet(
            "QTextBrowser { background-color: #FAFAFA; color: #1A1A1A; border: none; }"
        )
        browser.setHtml(self._load_html())
        layout.addWidget(browser)

        close_btn = QPushButton("닫기")
        close_btn.setFixedWidth(80)
        close_btn.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close_btn)
        btn_row.setContentsMargins(0, 0, 12, 0)
        layout.addLayout(btn_row)

    def _load_html(self) -> str:
        import markdown as _md
        from markdown.extensions.toc import slugify_unicode
        try:
            with open(self._readme_path, "r", encoding="utf-8") as f:
                text = f.read()
            body = _md.markdown(
                text,
                extensions=["tables", "fenced_code", "toc"],
                extension_configs={"toc": {"slugify": slugify_unicode}},
            )
            body = re.sub(
                r'<(h[1-6]) id="([^"]+)">',
                r'<\1><a name="\2"></a>',
                body,
            )
        except FileNotFoundError:
            body = "<p>README.md 파일을 찾을 수 없습니다.</p>"
        return _HELP_HTML_STYLE + body


# ---------------------------------------------------------------------------
# 환경 설정 팝업 (베이스)
# ---------------------------------------------------------------------------
class SettingsDialog(QDialog):
    """테마 선택 행을 가진 환경설정 베이스 다이얼로그.

    `load_cfg()` / `save_cfg(cfg)` 콜백으로 설정을 읽고 쓴다. 앱별 추가 항목은
    `add_extra_rows` / `read_extra` / `write_extra` 훅을 오버라이드해 확장한다.
    """

    theme_changed = Signal(str)
    LABEL_WIDTH = 60

    def __init__(self, current_theme: str, load_cfg, save_cfg, parent=None):
        super().__init__(parent)
        self._current_theme = current_theme
        self._load_cfg = load_cfg
        self._save_cfg = save_cfg
        self.setWindowTitle("환경 설정")
        self.setWindowIcon(make_emoji_icon("⚙️", 64))
        self.setMinimumWidth(380)
        self._init_ui()
        self._load_settings()

    def _make_row(self, label_text: str, widget) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        lbl = QLabel(label_text)
        lbl.setFixedWidth(self.LABEL_WIDTH)
        lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        row.addWidget(lbl)
        row.addWidget(widget, 1)
        return row

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(16)
        layout.setContentsMargins(24, 24, 24, 20)

        # 앱별 추가 행(테마 행보다 위)
        self.add_extra_rows(layout, self._make_row)

        # 테마
        self._theme_group = QButtonGroup(self)
        self._radio_dark  = QRadioButton("다크")
        self._radio_light = QRadioButton("라이트")
        self._theme_group.addButton(self._radio_dark,  0)
        self._theme_group.addButton(self._radio_light, 1)

        theme_widget = QWidget()
        theme_inner  = QHBoxLayout(theme_widget)
        theme_inner.setContentsMargins(0, 0, 0, 0)
        theme_inner.setSpacing(20)
        theme_inner.addWidget(self._radio_dark)
        theme_inner.addWidget(self._radio_light)
        theme_inner.addStretch()
        layout.addLayout(self._make_row("테마:", theme_widget))

        layout.addItem(QSpacerItem(0, 8, QSizePolicy.Minimum, QSizePolicy.Fixed))

        # 버튼
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        save_btn   = QPushButton("저장")
        save_btn.setObjectName("primary")
        save_btn.setDefault(True)
        save_btn.setFixedHeight(36)
        cancel_btn = QPushButton("취소")
        cancel_btn.setFixedHeight(36)
        save_btn.clicked.connect(self._save_settings)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(save_btn)
        layout.addLayout(btn_row)

    def _load_settings(self):
        cfg = self._load_cfg()
        saved_theme = cfg.get("theme", "dark")
        (self._radio_dark if saved_theme == "dark" else self._radio_light).setChecked(True)
        self.read_extra(cfg)

    def _save_settings(self):
        selected_theme = "dark" if self._radio_dark.isChecked() else "light"
        cfg = self._load_cfg()
        cfg["theme"] = selected_theme
        self.write_extra(cfg)
        try:
            self._save_cfg(cfg)
        except Exception as e:
            QMessageBox.warning(self, "오류", f"설정 저장 중 오류:\n{e}")
            return
        if selected_theme != self._current_theme:
            self._current_theme = selected_theme
            self.theme_changed.emit(selected_theme)
        QMessageBox.information(self, "저장 완료", "설정이 저장되었습니다.")
        self.accept()

    # ── 확장 훅 (서브클래스에서 오버라이드) ────────────────────────────────

    def add_extra_rows(self, layout: QVBoxLayout, make_row) -> None:
        """테마 행 위에 앱별 추가 행을 끼운다. `make_row(label, widget)` 사용."""

    def read_extra(self, cfg: dict) -> None:
        """로드한 cfg 로 추가 위젯 상태를 채운다."""

    def write_extra(self, cfg: dict) -> None:
        """추가 위젯 값을 cfg 에 기록한다."""
