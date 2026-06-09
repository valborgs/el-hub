"""실시간 폴더 백업 프로그램 패키지."""

from pathlib import Path

# 앱 아이콘(폴더 + 시계). main.py 와 트레이/창 아이콘에서 공통으로 사용한다.
ICON_PATH = Path(__file__).resolve().parent.parent / "assets" / "icon.svg"
