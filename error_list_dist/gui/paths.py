# -*- coding: utf-8 -*-
"""프로젝트 경로 상수 및 sys.path 부트스트랩."""

import os
import sys

if getattr(sys, "frozen", False):
    # PyInstaller EXE 실행: 읽기 전용 번들 데이터는 _MEIPASS, 쓰기 가능 파일은 exe 옆
    _BUNDLE_DIR  = sys._MEIPASS
    _WRITABLE_DIR = os.path.dirname(sys.executable)
else:
    _BUNDLE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    _WRITABLE_DIR = _BUNDLE_DIR

# config.json 은 exe 옆(쓰기 가능) 위치
PROJECT_ROOT = _WRITABLE_DIR
# fonts/, README.md 는 번들에 포함된 읽기 전용 데이터
FONT_DIR    = os.path.join(_BUNDLE_DIR, "fonts")
README_PATH = os.path.join(_BUNDLE_DIR, "README.md")
CONFIG_FILE = os.path.join(_WRITABLE_DIR, "config.json")

if _BUNDLE_DIR not in sys.path:
    sys.path.insert(0, _BUNDLE_DIR)
if _WRITABLE_DIR not in sys.path:
    sys.path.insert(0, _WRITABLE_DIR)
