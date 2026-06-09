# -*- coding: utf-8 -*-
"""
scrape_distr_pipeline/utils.py  ── 파싱 유틸리티

오류항목/수정내역 텍스트 파싱에 사용하는 공유 함수 모음.
scrape_core.py / dist_core.py 양쪽에서 임포트합니다.
"""

import re
from typing import List, Optional, Tuple

import pandas as pd

from .constants import ARROWS


def get_val(row: list, idx: int) -> str:
    """row[idx] 값을 안전하게 문자열로 반환."""
    if idx >= len(row):
        return ""
    v = row[idx]
    return str(v).strip() if pd.notna(v) else ""


def default_log_callback(status: str, message: str) -> None:
    """log_callback 미지정 시 사용하는 기본 콘솔 출력 함수."""
    print(f"[{status.upper()}] {message}")


def normalize_error_type(v: str) -> str:
    """오류 유형 문자열을 정규화된 내부 키로 변환합니다."""
    v = (v or "").strip()
    if v in ("링크오류", "링크수정"):
        return "링크"
    elif v in ("단계오류", "단계수정"):
        return "단계"
    elif v in ("책갈피오류", "석점줄임"):
        return "책갈피수정"
    elif v in ("추가", "삭제", "책갈피추가", "책갈피삭제"):
        return "추가·삭제"
    elif v in ("띄워쓰기", "띄여쓰기"):
        return "띄어쓰기"
    else:
        return v


def split_lines(val) -> List[str]:
    """셀 값을 \\r\\n / \\n / \\r 기준으로 줄 분리하고 빈 줄을 제거합니다."""
    if val is None:
        return []
    parts = re.split(r"\r\n|\n|\r", str(val))
    return [p.strip() for p in parts if p.strip()]


def parse_fix_text(raw_fix: str) -> Tuple[Optional[str], str, str]:
    """수정내역 한 줄에서 (arrow, before, after)를 파싱합니다.

    ⌄/⌴ 공백 정규화 후 ARROWS 중 첫 매칭으로 좌우를 분리합니다.
    "-  >" / "=  >" 처럼 화살표 중간에 공백이 낀 오타도 정규화합니다.
    화살표가 없으면 (None, "", normalized.strip()).
    """
    normalized = (raw_fix or "").replace("⌄", " ").replace("⌴", " ")
    normalized = re.sub(r"-\s+>", "->", normalized)
    normalized = re.sub(r"=\s+>", "=>", normalized)
    found_arrow = next((a for a in ARROWS if a in normalized), None)
    if found_arrow:
        left, right = normalized.split(found_arrow, 1)
        return found_arrow, left.strip(), right.strip()
    return None, "", normalized.strip()


def split_fix_lines(val) -> List[str]:
    """수정내역 셀을 항목 단위로 분리합니다.

    화살표(→, ->, =>) 바로 앞뒤의 줄바꿈은 항목 내부로 처리합니다.
    """
    if val is None:
        return []
    raw = [p.strip() for p in re.split(r"\r\n|\n|\r", str(val)) if p.strip()]
    if not raw:
        return []
    merged = [raw[0]]
    for line in raw[1:]:
        prev = merged[-1]
        # 화살표 중간에 줄바꿈이 낀 경우: "- \n >" 또는 "= \n >"
        split_arrow = re.search(r"[-=]\s*$", prev) and re.match(r"^\s*>", line)
        if any(prev.endswith(a) for a in ARROWS) or any(line.startswith(a) for a in ARROWS) or split_arrow:
            merged[-1] = prev + " " + line
        else:
            merged.append(line)
    return merged
