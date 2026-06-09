# -*- coding: utf-8 -*-
"""
scrape_distr_pipeline/pipeline.py  ── 파이프라인 진입점

각 모듈을 순서대로 실행하는 통합 함수를 제공합니다.

실행 절차
    1단계  scrape_core.run_scrape()
           구글 시트 로드 → 박스 범위 추출 → 오류항목 파싱
           → (rows_list, parsed_items_list) 반환

    2단계  dist_core.run_distribute()
           원본 엑셀 복사 → A~H 공통정보 기록 → 중복제거·분배 → 4개 시트 L/M/N 기록
           → _자동분류{원본확장자} 저장 → 경로 반환

    3단계  design_core.run_design()
           _자동분류 파일에 테두리·폰트·정렬·행 높이 서식 일괄 적용

공개 함수
    run_pipeline(excel_file, gsheet_index, start_box, end_box, log_callback)
        → 세 단계를 순서대로 실행하고 최종 출력 파일 경로를 반환합니다.

사용 예시
    from scrape_distr_pipeline.pipeline import run_pipeline
    import os

    os.chdir(r"C:\\...\\gsheet_scraping")   # config.json 위치
    result = run_pipeline(
        excel_file   = "0.인쇄자료_매크로.xlsm",
        gsheet_index = 2,          # 부산
        start_box    = "B0001",
        end_box      = "B0050",
    )
    print(result)   # → "0.인쇄자료_매크로_자동분류.xlsm"
"""

import os
import sys
from typing import Callable

# ---------------------------------------------------------------------------
# 형제 모듈 import (같은 패키지 내 scrape_core, dist_core)
# ---------------------------------------------------------------------------
_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_DIR not in sys.path:
    sys.path.insert(0, _PKG_DIR)

from core.scrape_core  import run_scrape      # noqa: E402
from core.dist_core   import run_distribute  # noqa: E402
from core.design_core import run_design      # noqa: E402
from .utils      import default_log_callback  # noqa: E402


# ---------------------------------------------------------------------------
# 공개 API
# ---------------------------------------------------------------------------

def run_pipeline(
    excel_file: str,
    gsheet_index: int,
    start_box: str,
    end_box: str,
    log_callback: Callable = None,
) -> str:
    """1단계(scrape_core) → 2단계(dist_core)를 순서대로 실행합니다.

    Args:
        excel_file:   작업 대상 엑셀 파일 (.xlsx 또는 .xlsm)
        gsheet_index: 구글 시트 인덱스 (1=서울, 2=부산, 3=디파)
        start_box:    시작 박스 번호 문자열 (예: "B0001")
        end_box:      종료 박스 번호 문자열 (예: "B0010")
        log_callback: log_callback(status: str, message: str) 패턴

    Returns:
        최종 서식까지 적용된 _자동분류 파일 경로

    Raises:
        RuntimeError: 구글 시트 연결·파일 열기·저장 실패 시
        ValueError:   박스 번호 미존재·시트 구조 불일치 시
        FileNotFoundError: excel_file 미존재 시

    주의:
        load_gsheet_data()가 cwd 기준 'config.json'을 읽으므로,
        호출 전 cwd를 gsheet_scraping 디렉터리로 변경하거나
        호출자가 절대 경로 처리를 해야 합니다.
    """
    log_callback = log_callback or default_log_callback

    log_callback("info", "=" * 50)
    log_callback("info", "🚀 파이프라인 시작")
    log_callback("info", "=" * 50)

    # ── 1단계: 구글 시트 스크래핑 ─────────────────────────────────────────
    log_callback("info", "[ 1단계 ] 구글 시트 스크래핑")
    rows_list, parsed_items_list = run_scrape(
        gsheet_index = gsheet_index,
        start_box    = start_box,
        end_box      = end_box,
        log_callback = log_callback,
    )

    # ── 2단계: 오류항목 자동분배 ───────────────────────────────────────────
    log_callback("info", "[ 2단계 ] 오류항목 자동분배")
    dst_path = run_distribute(
        rows_list          = rows_list,
        parsed_items_list  = parsed_items_list,
        excel_file         = excel_file,
        log_callback       = log_callback,
    )

    # ── 3단계: 서식 일괄 적용 ─────────────────────────────────────────────
    log_callback("info", "[ 3단계 ] 서식 일괄 적용")
    run_design(
        excel_file   = dst_path,
        log_callback = log_callback,
    )

    log_callback("info", "=" * 50)
    log_callback("info", f"✅ 파이프라인 완료 → '{dst_path}'")
    log_callback("info", "=" * 50)

    return dst_path
