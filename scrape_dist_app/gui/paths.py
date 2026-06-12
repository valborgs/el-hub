# -*- coding: utf-8 -*-
"""프로젝트 경로 상수 및 sys.path 부트스트랩 (소스 실행 전용)."""

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # scrape_dist_app/
FONT_DIR    = os.path.join(PROJECT_ROOT, "fonts")
README_PATH = os.path.join(PROJECT_ROOT, "README.md")
CONFIG_FILE = os.path.join(PROJECT_ROOT, "config.json")

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 워크스페이스 루트(auto/)를 sys.path 에 추가해 공용 디자인 패키지(elhub_ui)를 import 가능하게 한다.
# 서브앱은 cwd 가 자기 폴더라 루트가 기본 경로에 없다.
_REPO_ROOT = os.path.dirname(PROJECT_ROOT)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
