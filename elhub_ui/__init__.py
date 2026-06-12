# -*- coding: utf-8 -*-
"""el-hub 워크스페이스 공용 디자인 시스템.

허브(`hub.py`)와 세 서브앱(`backup-tool`, `scrape_dist_app`, `error_list_dist`)이
공유하는 디자인 토큰·QSS·DWM 헬퍼·공용 위젯의 단일 소스.

서브앱은 cwd 가 자기 폴더라 `auto/` 가 sys.path 에 없으므로, 각 앱이 리포 루트를
sys.path 에 추가한 뒤 `import elhub_ui` 로 로드한다(허브는 루트에서 실행되어 바로 해석됨).
"""
