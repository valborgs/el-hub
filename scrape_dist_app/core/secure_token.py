# -*- coding: utf-8 -*-
"""허브 공유 토큰 보안 저장 헬퍼 — 루트 secure_store.py 위임 로더.

예전에는 별도 exe(dataclip) 패키징 때문에 허브 루트 모듈을 가져올 수 없어
secure_store.py 의 상수·로직을 이 파일에 복제했었다. 이제 소스 실행만 하므로,
허브 루트(auto/)의 ``secure_store`` 를 importlib 로 지연 로딩해 그대로 위임한다
(backup-tool 이 hub_auth/proc_state 를 로드하는 방식과 동일). 이로써 _SERVICE /
_ACCOUNT / _ENTROPY 상수와 암·복호화 로직이 secure_store.py 단일 소스로 통합된다.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

_secure_store = None


def _ss():
    """허브 루트의 secure_store 모듈을 지연 로딩해 반환한다."""
    global _secure_store
    if _secure_store is not None:
        return _secure_store
    path = Path(__file__).resolve().parents[2] / "secure_store.py"   # auto/secure_store.py
    spec = importlib.util.spec_from_file_location("secure_store", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _secure_store = module
    return module


def save_token(token_json: str) -> None:
    """토큰 JSON 문자열을 DPAPI 로 암호화해 자격 증명 관리자에 저장한다."""
    _ss().save_token(token_json)


def load_token() -> str | None:
    """자격 증명 관리자에서 토큰을 읽어 복호화한 JSON 문자열을 반환한다 (없으면 None)."""
    return _ss().load_token()


def has_token() -> bool:
    """저장된 토큰이 존재하는지 검사한다 (네트워크 호출 없음)."""
    return _ss().has_token()


def delete_token() -> None:
    """저장된 토큰을 삭제한다. 항목이 없으면 무시한다."""
    _ss().delete_token()
