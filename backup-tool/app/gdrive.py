import os
import mimetypes
import importlib.util
from pathlib import Path
from typing import Callable

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

LogCallback = Callable[[str], None]
ErrorCallback = Callable[[str], None]


def _emit(cb, message: str) -> None:
    if cb is None:
        return
    try:
        cb(message)
    except Exception:
        pass


# '내 드라이브' 루트를 가리키는 Drive API 별칭. 업로드 대상 폴더가
# 지정되지 않았을 때의 기본 부모 폴더로 쓴다.
ROOT_FOLDER_ID = "root"

_service = None


# 로그인·토큰 관리는 허브의 독립 인증 모듈(hub_auth)에 위임한다.
# backup-tool 은 허브 루트(auto/) 아래에서 실행되므로 parents[2] 가 허브 루트다.
# 다른 앱도 같은 hub_auth 모듈을 가져다 동일한 세션을 공유한다.
_hub_auth = None


def _auth():
    """허브 인증 모듈(hub_auth)을 지연 로딩해 반환한다.

    모듈 임포트 시점에 실패하지 않도록, 처음 인증이 필요할 때 로드한다.
    파일을 찾지 못하면 ImportError 를 던진다.
    """
    global _hub_auth
    if _hub_auth is not None:
        return _hub_auth
    auth_path = Path(__file__).resolve().parents[2] / "hub_auth.py"
    if not auth_path.exists():
        raise ImportError(
            f"허브 인증 모듈을 찾을 수 없습니다: {auth_path}\n"
            "backup-tool 은 허브(auto/) 아래에서 실행되어야 합니다."
        )
    spec = importlib.util.spec_from_file_location("hub_auth", auth_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _hub_auth = module
    return module


def is_logged_in() -> bool:
    """허브 토큰 파일이 존재하는지 검사한다 (네트워크 호출 없음)."""
    return _auth().is_logged_in()


def login() -> str:
    """허브 OAuth 로그인을 수행하고(필요 시 브라우저) 로그인된 이메일을 반환한다.

    캐시된 토큰이 유효하면 브라우저 없이 즉시 이메일을 돌려준다.
    """
    global _service
    email = _auth().login()
    _service = None  # 새 자격증명으로 서비스 재생성을 유도
    return email


def get_email() -> str:
    """캐시된 토큰만으로 현재 이메일을 반환한다(브라우저 없음). 무효면 PermissionError."""
    return _auth().get_email()


def cancel_login() -> None:
    """진행 중인 허브 로그인 흐름을 취소한다."""
    _auth().cancel_login()


def _get_service():
    """Drive API 서비스 객체를 반환한다. 유효한 토큰이 없으면 PermissionError."""
    global _service
    if _service is not None:
        return _service
    creds = _auth().get_credentials()
    if creds is None:
        raise PermissionError("구글 드라이브 토큰이 없습니다. 다시 로그인해 주세요.")
    _service = build('drive', 'v3', credentials=creds)
    return _service


def list_files_in_folder(folder_id, log_cb: LogCallback | None = None,
                         error_cb: ErrorCallback | None = None):
    _emit(log_cb, f"폴더 ID '{folder_id}'의 내용을 읽어오는 중...")
    try:
        service = _get_service()
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(
            q=query, pageSize=100,
            fields="nextPageToken, files(id, name, mimeType)"
        ).execute()
        items = results.get('files', [])
        if not items:
            _emit(log_cb, '폴더가 비어있거나 파일을 찾을 수 없습니다.')
        else:
            _emit(log_cb, '--- 폴더 내 파일 목록 ---')
            for item in items:
                item_type = "폴더" if item['mimeType'] == 'application/vnd.google-apps.folder' else "파일"
                _emit(log_cb, f"[{item_type}] 이름: {item['name']} | ID: {item['id']}")
    except Exception as e:
        _emit(error_cb, f"API 호출 중 오류가 발생했습니다: {e}")


def list_subfolders(parent_id=ROOT_FOLDER_ID):
    """parent_id 하위의 (휴지통이 아닌) 폴더 목록을 [(id, name), ...] 로 반환한다.

    폴더 선택 대화상자가 Drive 트리를 탐색할 때 사용한다. parent_id 를
    'root' 로 주면 '내 드라이브' 최상위의 폴더들을 돌려준다.
    """
    service = _get_service()
    query = (
        f"'{parent_id}' in parents"
        f" and mimeType = 'application/vnd.google-apps.folder'"
        f" and trashed = false"
    )
    folders: list[tuple[str, str]] = []
    page_token = None
    while True:
        results = service.files().list(
            q=query,
            pageSize=100,
            fields="nextPageToken, files(id, name)",
            orderBy="name",
            pageToken=page_token,
        ).execute()
        for f in results.get('files', []):
            folders.append((f['id'], f['name']))
        page_token = results.get('nextPageToken')
        if not page_token:
            break
    return folders


def _get_or_create_drive_folder(name, parent_id):
    service = _get_service()
    query = (
        f"'{parent_id}' in parents"
        f" and name = '{name}'"
        f" and mimeType = 'application/vnd.google-apps.folder'"
        f" and trashed = false"
    )
    results = service.files().list(q=query, fields='files(id, name)').execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    metadata = {
        'name': name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id],
    }
    folder = service.files().create(body=metadata, fields='id').execute()
    return folder['id']


def _upload_file(local_path, parent_id):
    service = _get_service()
    name = os.path.basename(local_path)
    mime_type, _ = mimetypes.guess_type(local_path)
    if mime_type is None:
        mime_type = 'application/octet-stream'
    media = MediaFileUpload(local_path, mimetype=mime_type, resumable=True)
    query = (
        f"'{parent_id}' in parents"
        f" and name = '{name}'"
        f" and mimeType != 'application/vnd.google-apps.folder'"
        f" and trashed = false"
    )
    results = service.files().list(q=query, fields='files(id)').execute()
    existing = results.get('files', [])
    if existing:
        service.files().update(fileId=existing[0]['id'], media_body=media).execute()
    else:
        metadata = {'name': name, 'parents': [parent_id]}
        service.files().create(body=metadata, media_body=media, fields='id').execute()


def upload_files(local_root, relative_paths, parent_folder_id=ROOT_FOLDER_ID,
                 log_cb: LogCallback | None = None,
                 error_cb: ErrorCallback | None = None):
    """local_root 아래의 지정된 파일들만 Drive 에 업로드한다."""
    local_root = Path(local_root)
    folder_cache: dict[tuple, str] = {(): parent_folder_id}
    failed: list[str] = []

    for rel in relative_paths:
        rel_path = Path(rel)
        rel_posix = rel_path.as_posix()
        local_path = local_root / rel_path
        if not local_path.is_file():
            continue
        try:
            parent_id = parent_folder_id
            parts = rel_path.parent.parts
            for i, part in enumerate(parts):
                key = parts[: i + 1]
                cached = folder_cache.get(key)
                if cached is None:
                    cached = _get_or_create_drive_folder(part, parent_id)
                    folder_cache[key] = cached
                parent_id = cached
            _upload_file(str(local_path), parent_id)
        except Exception as err:
            _emit(error_cb, f"구글 드라이브 업로드 실패 ({rel_posix}): {err}")
            failed.append(rel_posix)

    return failed


def upload_folder(local_folder_path, parent_folder_id=ROOT_FOLDER_ID,
                  log_cb: LogCallback | None = None,
                  error_cb: ErrorCallback | None = None):
    """로컬 폴더를 Drive의 parent_folder_id 아래에 재귀적으로 업로드합니다."""
    folder_name = os.path.basename(os.path.normpath(local_folder_path))
    _emit(log_cb, f"'{folder_name}' 폴더를 Drive에서 조회 중...")
    drive_folder_id = _get_or_create_drive_folder(folder_name, parent_folder_id)
    for entry in os.scandir(local_folder_path):
        if entry.is_dir(follow_symlinks=False):
            upload_folder(entry.path, drive_folder_id, log_cb, error_cb)
        elif entry.is_file(follow_symlinks=False):
            _emit(log_cb, f"  업로드 중: {entry.path}")
            try:
                _upload_file(entry.path, drive_folder_id)
            except Exception as e:
                _emit(error_cb, f"업로드 오류 ({entry.name}): {e}")
    _emit(log_cb, f"'{folder_name}' 업로드 완료 (Drive ID: {drive_folder_id})")
    return drive_folder_id
