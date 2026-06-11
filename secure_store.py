# -*- coding: utf-8 -*-
"""허브 공유 토큰 보안 저장 헬퍼.

구글 OAuth 토큰(JSON 문자열)을 pywin32 의 DPAPI(CryptProtectData) 로 암호화한 뒤
base64 로 인코딩해 keyring 으로 Windows 자격 증명 관리자에 저장한다.
평문 파일(credentials/token.json) 대신 사용한다.

세 앱(hub, backup-tool, scrape_dist_app)이 같은 _SERVICE / _ACCOUNT / _ENTROPY 로
동일한 자격 증명 항목을 공유한다. scrape_dist_app 은 별도 exe 로 패키징되므로
core/secure_token.py 에 이 파일과 동일한 상수·로직을 복제해 둔다. 셋 중 하나라도
상수를 바꾸면 나머지도 반드시 함께 바꿔야 한다.
"""

from __future__ import annotations

import base64

import keyring
from keyring.backends import Windows
import win32crypt

# PyInstaller 번들 등에서 keyring 이 백엔드 자동탐색에 실패해 fail/chainer 백엔드로
# 폴백하는 문제를 막기 위해, 모듈 로드 시 Windows 자격 증명 관리자 백엔드를 강제 지정한다.
keyring.set_keyring(Windows.WinVaultKeyring())

# 자격 증명 관리자 항목 식별자 (세 앱 공유 고정 상수)
_SERVICE = "AutoHub-GoogleOAuth"
_ACCOUNT = "token"

# DPAPI optional entropy(앱 고유 솔트). 같은 PC·계정의 다른 프로세스가 자격 증명을
# 그대로 읽어 무단 복호화하는 것을 막는다. 암·복호화 양쪽에 동일하게 넘겨야 한다.
_ENTROPY = b"AutoHub-GoogleOAuth-Entropy-2026"


def save_token(token_json: str) -> None:
    """토큰 JSON 문자열을 DPAPI 로 암호화해 자격 증명 관리자에 저장한다."""
    blob = win32crypt.CryptProtectData(
        token_json.encode("utf-8"), "GoogleOAuth", _ENTROPY, None, None, 0
    )
    keyring.set_password(_SERVICE, _ACCOUNT, base64.b64encode(blob).decode("ascii"))


def load_token() -> str | None:
    """자격 증명 관리자에서 토큰을 읽어 복호화한 JSON 문자열을 반환한다.

    저장된 값이 없거나 복호화에 실패하면 None 을 반환한다.
    """
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
