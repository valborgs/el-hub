"""백업 복사 로직: 제외 필터, 단일 파일 복사, 초기 전체 동기화.

백업 방식은 '누적(안전 모드)'이다. 원본에서 파일이 삭제/이동돼도 백업본은 지우지 않는다.
한 파일의 복사 실패가 전체 백업을 멈추지 않도록, 복사 오류는 파일 단위로 격리한다.
"""

from __future__ import annotations

import fnmatch
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Callable

# 확장자 없는 8자리 대문자 hex 이름 (예: ACA7B500).
# Office 가 저장 중 원본을 잠시 옮겨둘 때 쓰는 임시 파일 형식이다.
_HEX_TEMP_RE = re.compile(r"^[0-9A-F]{8}$")

from .config import BackupConfig
from .errors import SyncError

# 로그/오류를 UI 로 전달하기 위한 콜백 타입
LogCallback = Callable[[str], None]
ErrorCallback = Callable[[str], None]
# 백업된 파일의 절대경로(백업 디렉토리 아래)를 알리는 콜백 — Drive 업로드 큐에 사용
PathCallback = Callable[[Path], None]


def _match_single_pattern(rel: str, pattern: str) -> bool:
    """단일 패턴이 상대경로에 매칭되는지 검사한다.

    패턴 종류에 따라 매칭 범위가 다르다:
    - 경로 구분자('/')가 있으면 전체 경로 기준으로만 비교한다.
      예) 'src/*.py' → src/ 바로 아래 .py 파일, 'temp/cache' → temp/cache/ 하위 전체
    - 와일드카드('*', '?', '[')가 있으면 모든 경로 구성요소에 적용한다.
      예) '*.py' → 어느 깊이의 .py 파일이든 포함, '~$*' → 어느 깊이든 포함
    - 순수 이름 패턴(구분자·와일드카드 없음)은 디렉토리 이름은 어느 깊이에서든
      매칭하되, 파일 이름은 루트 직속(구성요소 1개)일 때만 매칭한다.
      예) 'node_modules' → node_modules/ 하위 파일 모두 포함 (디렉토리 명 매칭)
          '보고서.xlsx'  → 루트 직속 파일만 매칭, 하위 디렉토리의 동명 파일 제외
    """
    norm = rel.replace("\\", "/")
    parts = norm.split("/")
    pat = pattern.replace("\\", "/").rstrip("/")
    if not pat:
        return False

    # 전체 경로 fnmatch (경로 포함 패턴 및 루트 직속 파일 모두 처리)
    if fnmatch.fnmatch(norm, pat):
        return True

    has_sep = "/" in pat
    if has_sep:
        # 경로 구분자가 있으면 전체 경로 비교만 허용
        # 디렉토리 접두사 매칭: "temp/cache" → "temp/cache/data.json" 포함
        return norm.startswith(pat + "/")

    has_wildcard = any(c in pat for c in "*?[")
    if has_wildcard:
        # 와일드카드 패턴: 모든 경로 구성요소에 적용
        return any(fnmatch.fnmatch(part, pat) for part in parts)

    # 순수 이름 패턴: 디렉토리 구성요소(마지막 제외)는 어느 깊이에서든 매칭
    # 파일 이름(마지막 구성요소)은 루트 직속(parts 길이 1)일 때만 → 위 fnmatch에서 처리됨
    dir_parts = parts[:-1]
    return any(fnmatch.fnmatch(part, pat) for part in dir_parts)


_PATTERN_REPORT_MAX = 5


def _log_pattern_report(
    rels: list[str],
    patterns: list[str],
    label: str,
    log_cb: LogCallback,
) -> None:
    """패턴별 매칭 결과를 로그로 출력한다.

    매칭된 파일이 있으면 상위 디렉토리 단위로 요약하고, 없으면 '매칭 없음'을 기록한다.
    """
    for pat in patterns:
        matched = [r for r in rels if _match_single_pattern(r, pat)]
        if not matched:
            log_cb(f"[{label}] '{pat}': 매칭 없음")
            continue

        # 같은 최상위 디렉토리 아래 파일들은 디렉토리로 묶어 표시한다
        dirs: dict[str, int] = {}
        standalone: list[str] = []
        for r in matched:
            parts = r.split("/")
            if len(parts) > 1:
                dirs[parts[0]] = dirs.get(parts[0], 0) + 1
            else:
                standalone.append(r)

        items: list[str] = [f"{d}/ ({cnt}개 파일)" for d, cnt in dirs.items()]
        items.extend(standalone)

        log_cb(f"[{label}] '{pat}': {len(matched)}개 파일 매칭")
        for item in items[:_PATTERN_REPORT_MAX]:
            log_cb(f"  └ {item}")
        if len(items) > _PATTERN_REPORT_MAX:
            log_cb(f"  └ ... 외 {len(items) - _PATTERN_REPORT_MAX}개 항목")


def is_included(rel_path: str, includes: list[str]) -> bool:
    """includes 목록이 있을 때 해당 상대경로가 지정 패턴 중 하나에 해당하는지 검사한다.

    includes 가 비어 있으면 항상 True 를 반환한다(전체 허용).
    매칭 규칙은 _match_single_pattern 참고.
    """
    if not includes:
        return True
    return any(_match_single_pattern(rel_path, pat) for pat in includes)


def is_excluded(rel_path: str, excludes: list[str]) -> bool:
    """상대경로가 제외 패턴 중 하나에 해당하는지 검사한다.

    매칭 규칙은 _match_single_pattern 참고.
    """
    return any(_match_single_pattern(rel_path, pat) for pat in excludes)


def is_temp_artifact(rel_path: str) -> bool:
    """Office 등이 저장 과정에서 만드는 임시/잠금 파일인지 검사한다.

    사용자가 제외 목록에 넣지 않아도 항상 백업에서 제외한다. 대상:
    - "~$..."        : Excel/Word 의 잠금(소유자) 파일
    - "*.tmp"        : 저장 중 새 내용을 담는 임시 파일
    - 8자리 hex 이름 : 원본을 잠시 옮겨둘 때 쓰는 확장자 없는 임시 파일
    """
    name = rel_path.replace("\\", "/").rsplit("/", 1)[-1]
    if name.startswith("~$"):
        return True
    if name.lower().endswith(".tmp"):
        return True
    if _HEX_TEMP_RE.match(name):
        return True
    return False


def dated_root(backup_dir: str | Path) -> Path:
    """백업 저장 디렉토리 아래의 '오늘 날짜(YYYYMMDD)' 하위 폴더 경로를 반환한다.

    실제 폴더 생성은 copy_file 에서 상위 디렉토리를 만들 때 함께 처리된다.
    """
    return Path(backup_dir) / datetime.now().strftime("%Y%m%d")


def copy_file(src_root: Path, dst_root: Path, rel_path: str) -> None:
    """src_root/rel_path 파일을 dst_root/rel_path 로 복사한다.

    상위 디렉토리는 자동 생성하며, 메타데이터(수정시각 등)를 보존한다.
    모든 입출력 오류는 SyncError 로 변환해 던진다.
    """
    src = src_root / rel_path
    dst = dst_root / rel_path
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    except FileNotFoundError as err:
        # 복사하려는 순간 원본이 사라진 경우
        raise SyncError(
            f"원본 파일을 찾을 수 없어 건너뜁니다: {rel_path}", path=rel_path
        ) from err
    except PermissionError as err:
        raise SyncError(
            f"권한이 없어 복사하지 못했습니다: {rel_path}", path=rel_path
        ) from err
    except OSError as err:
        # 디스크 가득참, 경로 길이 초과, 잠긴 파일 등
        raise SyncError(
            f"복사 중 오류가 발생해 건너뜁니다: {rel_path}", path=rel_path
        ) from err


def initial_sync(
    config: BackupConfig,
    log_cb: LogCallback,
    error_cb: ErrorCallback,
    path_cb: PathCallback | None = None,
) -> tuple[int, int]:
    """대상 디렉토리 전체를 백업으로 복사한다(초기 동기화).

    제외 패턴에 걸리는 파일/디렉토리는 건너뛴다. 파일별로 오류를 격리하므로
    일부 파일이 실패해도 나머지는 계속 복사한다.

    Returns:
        (성공 건수, 실패 건수)
    """
    source = Path(config.source_dir).resolve()
    # 초기 동기화는 한 번의 배치이므로 시작 시점의 날짜 폴더로 통일한다.
    target_root = dated_root(Path(config.backup_dir).resolve())

    success = 0
    failed = 0

    log_cb(f"초기 동기화를 시작합니다: {source} -> {target_root}")

    try:
        walker = list(_iter_files(source))
    except OSError as err:
        # 대상 디렉토리 자체를 순회할 수 없는 경우 — 초기 동기화 중단
        raise SyncError(f"대상 디렉토리를 읽을 수 없습니다: {source}") from err

    # 임시 파일을 제외한 상대경로 목록으로 패턴 매칭 결과를 미리 기록한다
    if config.excludes or config.includes:
        all_rels: list[str] = []
        for f in walker:
            try:
                r = f.relative_to(source).as_posix()
            except ValueError:
                continue
            if not is_temp_artifact(r):
                all_rels.append(r)
        if config.excludes:
            _log_pattern_report(all_rels, config.excludes, "제외 패턴", log_cb)
        if config.includes:
            _log_pattern_report(all_rels, config.includes, "지정 패턴", log_cb)

    for src_file in walker:
        try:
            rel = src_file.relative_to(source).as_posix()
        except ValueError:
            continue
        if is_temp_artifact(rel):
            continue
        if is_excluded(rel, config.excludes):
            continue
        if not is_included(rel, config.includes):
            continue
        try:
            copy_file(source, target_root, rel)
            success += 1
            if path_cb is not None:
                try:
                    path_cb(target_root / rel)
                except Exception:
                    pass  # 콜백 오류가 동기화를 멈추지 않게 한다
        except SyncError as err:
            failed += 1
            error_cb(err.detail())

    if failed:
        log_cb(f"초기 동기화 완료: 성공 {success}건, 실패 {failed}건")
    else:
        log_cb(f"초기 동기화 완료: 성공 {success}건")
    return success, failed


def _iter_files(root: Path):
    """root 하위의 모든 파일을 순회한다. 접근 불가 디렉토리는 건너뛴다."""
    stack = [root]
    while stack:
        current = stack.pop()
        try:
            entries = list(current.iterdir())
        except OSError:
            # 권한 없는 하위 디렉토리 등 — 조용히 건너뛴다(루트는 호출부에서 처리)
            if current == root:
                raise
            continue
        for entry in entries:
            try:
                if entry.is_dir():
                    stack.append(entry)
                elif entry.is_file():
                    yield entry
            except OSError:
                # 심볼릭 링크 깨짐 등
                continue
