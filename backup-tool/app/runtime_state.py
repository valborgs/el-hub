"""백업툴의 '현재 실행 상태'를 파일로 남겨 외부 프로세스(허브 등)가 읽을 수 있게 한다.

config.json 은 '영속 설정'인 반면, 이 파일은 '이 프로세스가 살아 있는 동안의 실시간 상태'다.
허브를 나중에 켜더라도 이 파일을 읽어 백업툴이 실행 중인지·구글 드라이브 연동 중인지 알 수 있다.

pid·생성시각 기록과 생존 판별 같은 공통 로직은 허브 루트(auto/)의 ``proc_state`` 모듈에
위임한다(hub_auth 와 동일한 방식으로 importlib 로드). 이 래퍼는 백업툴 고유 상태
(watching, gdrive_enabled)를 함께 기록할 뿐이다.

- 정상 종료(_cleanup) 시 파일을 삭제한다.
- 비정상 종료로 파일이 남더라도, 읽는 쪽에서 (pid + 생성시각) 으로 동일 프로세스인지
  확인하므로 'pid 재사용'으로 인한 오판을 막을 수 있다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

# backup-tool/runtime_state.json — config.json 과 같은 폴더에 둔다.
RUNTIME_STATE_PATH = Path(__file__).resolve().parent.parent / "runtime_state.json"

_proc_state = None


def _ps():
    """허브 루트의 proc_state 모듈을 지연 로딩해 반환한다."""
    global _proc_state
    if _proc_state is not None:
        return _proc_state
    path = Path(__file__).resolve().parents[2] / "proc_state.py"
    spec = importlib.util.spec_from_file_location("proc_state", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _proc_state = module
    return module


def write(
    *,
    watching: bool,
    gdrive_enabled: bool,
    path: Path = RUNTIME_STATE_PATH,
) -> None:
    """현재 프로세스의 실행 상태를 파일로 기록한다. 실패는 조용히 무시한다."""
    try:
        _ps().write(path, watching=bool(watching), gdrive_enabled=bool(gdrive_enabled))
    except Exception:
        pass


def clear(path: Path = RUNTIME_STATE_PATH) -> None:
    """종료 시 런타임 상태 파일을 제거한다. 실패는 조용히 무시한다."""
    try:
        _ps().clear(path)
    except Exception:
        pass
