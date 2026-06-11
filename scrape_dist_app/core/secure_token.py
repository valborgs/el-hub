# -*- coding: utf-8 -*-
"""허브 공유 토큰 보안 저장 헬퍼 (scrape_dist_app 복제본).

허브 루트의 secure_store.py 와 **동일한 _SERVICE / _ACCOUNT / _ENTROPY 상수·로직**을
복제한 것이다. scrape_dist_app 은 별도 exe(dataclip) 로 패키징되어 허브 루트 모듈을
가져올 수 없으므로 자체 사본을 둔다. 셋 중 하나라도 상수를 바꾸면 나머지도 반드시
함께 바꿔야 같은 자격 증명을 공유·복호화할 수 있다.
"""

from __future__ import annotations

import base64

import keyring
from keyring.backends import Windows
import win32crypt

# PyInstaller 번들에서 keyring 이 fail/chainer 백엔드로 폴백하는 문제 방지.
keyring.set_keyring(Windows.WinVaultKeyring())

# 허브(secure_store.py) 와 반드시 일치해야 하는 공유 상수.
_SERVICE = "AutoHub-GoogleOAuth"
_ACCOUNT = "token"
_ENTROPY = b"AutoHub-GoogleOAuth-Entropy-2026"


def save_token(token_json: str) -> None:
    """토큰 JSON 문자열을 DPAPI 로 암호화해 자격 증명 관리자에 저장한다."""
    blob = win32crypt.CryptProtectData(
        token_json.encode("utf-8"), "GoogleOAuth", _ENTROPY, None, None, 0
    )
    keyring.set_password(_SERVICE, _ACCOUNT, base64.b64encode(blob).decode("ascii"))


def load_token() -> str | None:
    """자격 증명 관리자에서 토큰을 읽어 복호화한 JSON 문자열을 반환한다 (없으면 None)."""
    enc = keyring.get_password(_SERVICE, _ACCOUNT)
    if not enc:
        return None
    try:
        _, data = win32crypt.CryptUnprotectData(
            base64.b64decode(enc), _ENTROPY, None, None, 0
        )
        return data.decode("utf-8")
    except Exception:
        return None


def has_token() -> bool:
    """저장된 토큰이 존재하는지 검사한다 (네트워크 호출 없음)."""
    return keyring.get_password(_SERVICE, _ACCOUNT) is not None


def delete_token() -> None:
    """저장된 토큰을 삭제한다. 항목이 없으면 무시한다."""
    try:
        keyring.delete_password(_SERVICE, _ACCOUNT)
    except keyring.errors.PasswordDeleteError:
        pass
