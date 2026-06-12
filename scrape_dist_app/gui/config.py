# -*- coding: utf-8 -*-
"""config.json 읽기/쓰기 헬퍼 — 공용 구현(elhub_ui)에 CONFIG_FILE 주입."""

from . import paths  # noqa: F401  (sys.path 부트스트랩)
from elhub_ui.config import load_config as _load
from elhub_ui.config import save_config as _save
from .paths import CONFIG_FILE


def load_config() -> dict:
    return _load(CONFIG_FILE)


def save_config(cfg: dict) -> None:
    _save(CONFIG_FILE, cfg)
