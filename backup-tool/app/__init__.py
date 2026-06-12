"""실시간 폴더 백업 프로그램 패키지."""

import sys
from pathlib import Path

# 앱 아이콘(폴더 + 시계). main.py 와 트레이/창 아이콘에서 공통으로 사용한다.
ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon.svg"

# 워크스페이스 루트(auto/)를 sys.path 에 추가해 공용 디자인 패키지(elhub_ui)를 import 가능하게 한다.
# 이 앱은 cwd 가 backup-tool/ 이라 루트가 기본 경로에 없다(hub_auth/proc_state 도 같은 이유로 절대경로 로드).
_REPO_ROOT = str(Path(__file__).resolve().parents[2])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
