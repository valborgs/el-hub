# -*- coding: utf-8 -*-
"""
scrape_distr_pipeline/scrape_core.py  ── 1단계: 구글 시트 스크래핑

구글 시트에서 지정된 박스 범위의 데이터를 로드하고,
1차/2차/3차/품질점검 컬럼에 분산된 수정내역 데이터를 행별로 하나의 리스트로 수집합니다.

공개 함수
    run_scrape(gsheet_index, start_box, end_box, log_callback)
        → 구글 시트 로드 → 박스 범위 추출 → 오류항목 파싱
        → (rows_list, parsed_items_list) 반환

    rows_list:          원본 행 데이터 (A~H 공통정보 기록용)
    parsed_items_list:  행별 파싱된 오류항목 (L/M/N 분배용)

    반환값은 dist_core.run_distribute() 에 그대로 전달합니다.

주의
    load_gsheet_data()는 내부에서 cwd 기준 'config.json'을 읽습니다.
    호출 전 cwd를 gsheet_scraping 디렉터리로 변경하거나
    호출자가 절대 경로 처리를 해야 합니다.
"""

import json
import re
from datetime import date
from pathlib import Path
from typing import Callable, Dict, List, Tuple

import gspread
import pandas as pd
from gspread.exceptions import APIError, WorksheetNotFound

from common.constants import GROUPS
from common.utils import default_log_callback, get_val, normalize_error_type, parse_fix_text, split_lines, split_fix_lines


# ---------------------------------------------------------------------------
# 상수 (scrape_core 전용)
# ---------------------------------------------------------------------------

# 허브 공유 토큰: hub.py 와 같은 auto/ 레벨의 credentials/token.json
_HUB_TOKEN_FILE = Path(__file__).resolve().parents[2] / "credentials" / "token.json"
_OAUTH_SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
]


# ---------------------------------------------------------------------------
# 내부 함수
# ---------------------------------------------------------------------------

_DEFAULT_CONFIG = {"SPREADSHEET_URL": "", "theme": "light", "run_diff": True}

def _read_spreadsheet_url() -> str:
    """cwd의 config.json에서 SPREADSHEET_URL을 읽어 반환합니다."""
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(_DEFAULT_CONFIG, f, ensure_ascii=False, indent=2)
        config = _DEFAULT_CONFIG.copy()
    except json.JSONDecodeError as e:
        raise ValueError(f"config.json 파싱 오류: {e}")
    return config.get("SPREADSHEET_URL", "")



def _authorize_client_oauth() -> gspread.Client:
    """허브 공유 OAuth 토큰으로 gspread Client를 생성합니다."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials as OAuthCreds

    if not _HUB_TOKEN_FILE.exists():
        raise ValueError(
            "허브 구글 로그인이 필요합니다. hub.py 에서 먼저 로그인해 주세요."
        )
    try:
        creds = OAuthCreds.from_authorized_user_file(str(_HUB_TOKEN_FILE), _OAUTH_SCOPES)
    except Exception as e:
        raise ValueError(f"허브 토큰 파일 오류: {e}")

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            _HUB_TOKEN_FILE.write_text(creds.to_json(), encoding='utf-8')
        except Exception as e:
            raise ValueError(f"허브 토큰 갱신 실패: {e}")

    return gspread.authorize(creds)


def _copy_worksheet(gc: gspread.Client, spreadsheet_url: str, gsheet_index: int):
    """원본 시트를 복사하고 (copy_spreadsheet, worksheet) 를 반환합니다."""
    match = re.search(r'/spreadsheets/d/([a-zA-Z0-9_-]+)', spreadsheet_url)
    if not match:
        raise ValueError(f"유효하지 않은 스프레드시트 URL: {spreadsheet_url}")
    file_id = match.group(1)

    try:
        title = f"[DBⅡ] 오류체크리스트의 사본_{date.today().strftime('%Y%m%d')}"
        copy_ss = gc.copy(file_id, title=title, copy_permissions=False)
    except Exception as e:
        raise ValueError(f"스프레드시트 복사 실패: {e}")

    try:
        worksheet = copy_ss.get_worksheet(gsheet_index)
    except WorksheetNotFound:
        gc.del_spreadsheet(copy_ss.id)
        raise ValueError(f"시트 인덱스 {gsheet_index}를 찾을 수 없습니다.")
    if worksheet is None:
        gc.del_spreadsheet(copy_ss.id)
        raise ValueError(f"시트 인덱스 {gsheet_index}를 찾을 수 없습니다.")

    return copy_ss, worksheet



def _worksheet_to_dataframe(worksheet) -> pd.DataFrame:
    """워크시트의 전체 값을 DataFrame으로 변환합니다 (1행을 헤더로 사용)."""
    try:
        all_data = worksheet.get_all_values()
    except APIError as e:
        raise ValueError(f"시트 데이터 불러오기 실패: {e}")
    if not all_data:
        raise ValueError("시트에 데이터가 없습니다.")
    return pd.DataFrame(all_data[1:], columns=all_data[0])


def _load_gsheet_data(gsheet_index: int, log_callback: Callable = None) -> pd.DataFrame:
    """구글 시트에 연결하여 데이터를 Pandas DataFrame으로 반환.

    허브에 로그인된 구글 계정이 있어야 접근 가능하다.
    토큰이 없으면 로그를 남기고 예외를 발생시킨다.
    """
    spreadsheet_url = _read_spreadsheet_url()
    if not spreadsheet_url:
        raise ValueError("config.json의 SPREADSHEET_URL이 비어 있습니다. 구글 시트 URL을 입력하세요.")

    if not _HUB_TOKEN_FILE.exists():
        log_callback("error", "❌ 구글 계정 로그인이 필요합니다. hub에서 먼저 로그인해 주세요.")
        raise ValueError("구글 계정 로그인이 필요합니다. hub에서 먼저 로그인해 주세요.")

    log_callback("info", "📍 구글 계정으로 인증 중...")
    gc = _authorize_client_oauth()
    log_callback("info", "📍 시트 사본 생성 중...")
    copy_ss, worksheet = _copy_worksheet(gc, spreadsheet_url, gsheet_index)
    log_callback("info", f"✅ 시트 사본 연결: {worksheet.title}")
    log_callback("info", "📍 시트에서 모든 데이터 불러오는 중...")
    return _worksheet_to_dataframe(worksheet)


def _get_valid_box_range(df: pd.DataFrame, start_box: str, end_box: str) -> Tuple[int, int]:
    """시작/종료 박스 번호 문자열을 받아 인덱스를 반환."""
    if df.empty or df.shape[1] == 0:
        raise ValueError("데이터프레임의 구조가 올바르지 않습니다.")

    start_matches = df.index[df.iloc[:, 0] == start_box].tolist()
    end_matches   = df.index[df.iloc[:, 0] == end_box].tolist()

    if not start_matches:
        raise ValueError(f"시작 박스 번호 '{start_box}'를 찾을 수 없습니다.")
    if not end_matches:
        raise ValueError(f"종료 박스 번호 '{end_box}'를 찾을 수 없습니다.")

    start_idx, end_idx = start_matches[0], end_matches[-1]
    if start_idx > end_idx:
        start_idx, end_idx = end_idx, start_idx

    return start_idx, end_idx


def _extract_target_rows(df: pd.DataFrame, start_idx: int, end_idx: int) -> List[list]:
    """DataFrame에서 start_idx ~ end_idx 범위의 행을 리스트로 반환."""
    start_pos = df.index.get_loc(start_idx)
    end_pos   = df.index.get_loc(end_idx)
    if start_pos > end_pos:
        start_pos, end_pos = end_pos, start_pos

    rows_list = df.iloc[start_pos : end_pos + 1].values.tolist()
    if not rows_list:
        raise ValueError("선택한 범위에 추출할 데이터가 없습니다.")
    return rows_list


def _parse_row_items(row: list) -> List[Dict]:
    """단일 행의 GROUPS 컬럼을 순회하여 오류항목 dict 리스트로 수집합니다.

    1차/2차/3차/품질점검 컬럼에 분산된 오류항목/페이지번호/수정내역을
    하나의 플랫 리스트로 합칩니다.
    """
    raw_items: List[Dict] = []
    for col_err, col_page, col_content in GROUPS:
        err_val  = get_val(row, col_err)
        page_val = get_val(row, col_page)
        fix_val  = get_val(row, col_content)

        if not (err_val and page_val and fix_val):
            continue

        err_lines  = split_lines(err_val)
        page_lines = split_lines(page_val)
        fix_lines  = split_fix_lines(fix_val)
        length = min(len(err_lines), len(page_lines), len(fix_lines))

        for i in range(length):
            orig_err = err_lines[i]
            err_type = normalize_error_type(orig_err)
            found_arrow, before, after = parse_fix_text(fix_lines[i])

            raw_items.append({
                "arrow":    found_arrow,
                "err":      err_type,
                "orig_err": orig_err,
                "page":     page_lines[i],
                "before":   before,
                "after":    after,
            })
    return raw_items


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def run_scrape(
    gsheet_index: int,
    start_box: str,
    end_box: str,
    log_callback: Callable = None,
) -> Tuple[List[list], List[List[Dict]]]:
    """구글 시트 데이터를 로드하고 오류항목을 행별로 수집합니다.

    Args:
        gsheet_index: 구글 시트 인덱스 (1=서울, 2=부산, 3=디파)
        start_box:    시작 박스 번호 문자열 (예: "B0001")
        end_box:      종료 박스 번호 문자열 (예: "B0010")
        log_callback: log_callback(status: str, message: str) 패턴

    Returns:
        (rows_list, parsed_items_list):
            rows_list:         구글 시트에서 추출한 원본 행 데이터 목록 (A~H 공통정보용).
            parsed_items_list: 행별 파싱된 오류항목 목록 (L/M/N 분배용).
                               각 원소는 해당 행의 List[Dict].

    주의:
        load_gsheet_data()가 cwd 기준 'config.json'을 읽으므로,
        호출 전 cwd를 gsheet_scraping 디렉터리로 변경하거나
        호출자가 절대 경로 처리를 해야 합니다.
    """
    log_callback = log_callback or default_log_callback

    # ── 1. 구글 시트 로드 ──────────────────────────────────────────────────
    df_all = _load_gsheet_data(gsheet_index, log_callback=log_callback)

    log_callback("info", "📍 작업 범위 확인 중...")
    start_idx, end_idx = _get_valid_box_range(df_all, start_box, end_box)
    rows_list = _extract_target_rows(df_all, start_idx, end_idx)

    # ── 2. 오류항목 파싱 (1차/2차/3차/품질 컬럼 → 행별 단일 리스트) ───────
    log_callback("info", f"📍 총 {len(rows_list)}건 오류항목 수집 중...")
    parsed_items_list = [_parse_row_items(row) for row in rows_list]

    log_callback("info", f"✅ 스크래핑 완료. ({len(rows_list)}건)")
    return rows_list, parsed_items_list
