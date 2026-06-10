# -*- coding: utf-8 -*-
"""허브 공유 구글 OAuth 모듈.

backup-tool 의 oauth_client.json / token.json 을 공유해
두 앱(backup-tool, scrape_dist_app) 이 같은 세션을 사용한다.
"""

from __future__ import annotations

import os
import threading
import urllib.parse
import urllib.request
import webbrowser
import wsgiref.simple_server
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

HERE = Path(__file__).parent

CLIENT_SECRET_FILE = HERE / "credentials" / "oauth_client.json"
TOKEN_FILE         = HERE / "credentials" / "token.json"

# drive: Drive 백업 + 파일 복사·삭제
# spreadsheets: gspread 시트 읽기
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
]

# login() 진행 중 cancel_login() 으로 세트되면 OAuth 루프가 즉시 종료된다.
_cancel_event = threading.Event()


def is_logged_in() -> bool:
    """캐시된 토큰 파일이 존재하는지 검사한다 (네트워크 호출 없음)."""
    return TOKEN_FILE.exists()


def _try_cached_credentials() -> Credentials | None:
    """캐시된 토큰을 읽고, 필요 시 자동 갱신해서 반환한다. 브라우저는 띄우지 않는다."""
    if not TOKEN_FILE.exists():
        return None
    try:
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
    except Exception:
        return None

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            TOKEN_FILE.write_text(creds.to_json(), encoding='utf-8')
            return creds
        except Exception:
            return None

    return None


# ---------------------------------------------------------------------------
# 취소 가능한 OAuth 로컬 서버
# ---------------------------------------------------------------------------

class _SilentHandler(wsgiref.simple_server.WSGIRequestHandler):
    """콘솔 로그를 억제한 WSGI 핸들러."""
    def log_message(self, *args):
        pass


class _RedirectCapture:
    """OAuth 리다이렉트 URI 를 캡처하는 최소 WSGI 앱."""

    def __init__(self):
        self.redirect_uri: str | None = None

    def __call__(self, environ, start_response):
        qs = environ.get('QUERY_STRING', '')
        path = environ.get('PATH_INFO', '/')
        self.redirect_uri = (
            f"http://{environ['HTTP_HOST']}{path}"
            + (f"?{qs}" if qs else "")
        )
        start_response('200 OK', [('Content-Type', 'text/html; charset=utf-8')])
        html = '<html><body><p>로그인 완료. 이 탭을 닫아도 됩니다.</p></body></html>'
        return [html.encode('utf-8')]


def _run_oauth_flow() -> Credentials:
    """취소 가능한 OAuth 로컬 서버를 직접 구동해 Credentials 를 반환한다.

    _cancel_event 가 세트되면 루프를 즉시 종료하고 ValueError 를 던진다.
    서버 소켓은 timeout=0.5 s 로 폴링하므로 취소 반응 시간은 최대 0.5 초다.
    """
    if not CLIENT_SECRET_FILE.exists():
        raise FileNotFoundError(
            f"OAuth 클라이언트 파일을 찾을 수 없습니다: {CLIENT_SECRET_FILE}\n"
            "backup-tool/credentials/oauth_client.json 을 확인해 주세요."
        )

    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)

    capture = _RedirectCapture()
    server = wsgiref.simple_server.make_server(
        'localhost', 0, capture, handler_class=_SilentHandler
    )
    server.timeout = 0.5  # 취소 이벤트 폴링 간격

    port = server.server_address[1]
    flow.redirect_uri = f'http://localhost:{port}/'

    auth_url, _ = flow.authorization_url(prompt='consent')
    webbrowser.open(auth_url, new=1, autoraise=True)

    try:
        while not _cancel_event.is_set():
            server.handle_request()
            if capture.redirect_uri is not None:
                break
    finally:
        server.server_close()

    if _cancel_event.is_set():
        raise ValueError("로그인이 취소되었습니다.")

    # localhost 리다이렉트는 HTTP 를 사용하므로 HTTPS 강제 검사를 비활성화한다.
    os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'
    flow.fetch_token(authorization_response=capture.redirect_uri)
    creds = flow.credentials
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(creds.to_json(), encoding='utf-8')
    return creds


def cancel_login() -> None:
    """진행 중인 OAuth 흐름을 취소한다. 최대 0.5 초 내에 서버가 종료된다."""
    _cancel_event.set()


def login() -> str:
    """OAuth 흐름을 수행(필요 시 브라우저)하고 로그인된 계정의 이메일을 반환한다."""
    _cancel_event.clear()

    creds = _try_cached_credentials()
    if creds is None:
        creds = _run_oauth_flow()

    service = build('drive', 'v3', credentials=creds)
    about = service.about().get(fields='user').execute()
    return about.get('user', {}).get('emailAddress', '')


def get_email() -> str:
    """캐시된 토큰만으로 현재 사용자의 이메일을 반환한다 (브라우저 흐름 없음).

    토큰이 없거나 갱신 불가하면 PermissionError 를 던진다.
    """
    creds = _try_cached_credentials()
    if creds is None:
        raise PermissionError("저장된 로그인 정보가 유효하지 않습니다. 다시 로그인해 주세요.")
    service = build('drive', 'v3', credentials=creds)
    about = service.about().get(fields='user').execute()
    return about.get('user', {}).get('emailAddress', '')


def get_credentials() -> Credentials | None:
    """캐시된(필요 시 자동 갱신된) 자격증명을 반환한다. 브라우저는 띄우지 않는다.

    다른 앱이 이 모듈로 인증을 위임할 때, 직접 Drive/Sheets 서비스를 만들 수
    있도록 Credentials 를 노출한다. 유효한 토큰이 없으면 None 을 반환한다.
    """
    return _try_cached_credentials()


def logout() -> None:
    """저장된 토큰을 폐기하고 파일을 삭제한다. 폐기는 실패해도 무시한다."""
    if TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)
            token = getattr(creds, 'token', None)
        except Exception:
            token = None
        if token:
            try:
                data = urllib.parse.urlencode({'token': token}).encode()
                req = urllib.request.Request(
                    'https://oauth2.googleapis.com/revoke',
                    data=data,
                    headers={'Content-Type': 'application/x-www-form-urlencoded'},
                )
                urllib.request.urlopen(req, timeout=5).read()
            except Exception:
                pass
        try:
            TOKEN_FILE.unlink()
        except OSError:
            pass
