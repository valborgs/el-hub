# -*- coding: utf-8 -*-
"""`python -m gui` 진입점."""

import os
import sys

# uv run gui 실행 시 프로젝트 루트가 sys.path에 없을 수 있으므로 보정
_pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _pkg_parent not in sys.path:
    sys.path.insert(0, _pkg_parent)

from gui.app import main  # noqa: E402

if __name__ == "__main__":
    main()
