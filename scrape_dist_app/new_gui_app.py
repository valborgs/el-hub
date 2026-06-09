# -*- coding: utf-8 -*-
"""new_gui 패키지 진입 shim.

`python new_gui_app.py` 또는 `python -m gui` 둘 다 사용 가능.
실제 구현은 gui/ 디렉터리 안에 있다.
"""

from gui.app import main


if __name__ == "__main__":
    main()
