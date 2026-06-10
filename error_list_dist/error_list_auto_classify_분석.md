# error_list_auto_classify.py 코드 분석

## 개요
이 스크립트는 학위논문 오류 리스트를 자동으로 분류하고 여러 검토 단계(1차, 2차, 3차, 품질점검)로 분배하는 Excel 파일 처리 도구입니다. CLI 단독 실행 가능하며, `error_list_gui.py`에서 공개 API(`process_error_list`)를 호출하여 GUI로도 사용합니다.

## 주요 기능
- Excel 파일에서 오류 데이터를 읽어 4개 시트에 자동 분배
- **1차 점검과 2차 점검 시트의 raw 입력 데이터를 제어번호(B열) 기준으로 병합한 후 분배**
- **동일 제어번호가 여러 행으로 분산되어 있어도(신규 1행=1오류 포맷) 한 행으로 합쳐서 처리**
- 오류 유형별 제한과 우선순위 적용
- 동일·유사 항목 중복 제거(유사도 85% 이상 자동 제거)
- 수정 내역에 diff 스타일 시각화 적용 (변경된 부분 빨간색 표시, 단일 항목일 때 Rich Text)

## 설정 및 상수

### 파일 경로 설정
CLI 실행 시 인자로 입력한 원본 경로에서 자동으로 출력 경로를 생성합니다.

```python
base, ext = os.path.splitext(src_path)
dst_path = f"{base}_자동분류{ext}"
```

### 시트 구성
```python
SHEETS = ["1차 점검", "2차 점검", "3차 점검", "품질점검"]
```

### 데이터 구조
- **데이터 시작 행**: 8행부터
- **B열 (2)**: 제어번호 — 병합 키
- **A~K열**: 공통 정보 (모든 시트에 동일하게 복사)
- **L열 (12)**: 오류항목 (여러 줄 가능)
- **M열 (13)**: 페이지번호 (여러 줄 가능)
- **N열 (14)**: 수정내역 (여러 줄, "이전 → 이후" 형식)

### 입력 시트(병합 대상)
- **1차 점검 시트**: raw 입력 데이터 보유
- **2차 점검 시트**: raw 입력 데이터 보유 (병합 대상에 포함)
- **품질점검 시트**: raw 입력 데이터 보유 (병합 대상에 포함)
- 세 시트의 L/M/N 데이터를 제어번호 기준으로 통합한 뒤 4개 시트에 재분배함

### 행 구조 호환성
- **기존(구) 포맷**: 1개 제어번호 = 1행, L/M/N 셀 내 줄바꿈으로 여러 오류 묶음
- **신규 포맷**: 1개 오류 = 1행, 동일 제어번호가 여러 행에 분산 가능
- 두 포맷 모두 `merge_inputs_from_ws1_ws2_ws4`가 자연스럽게 처리

### 분배 규칙
```python
MAX_PER_ERR_KIND = 5      # 오류 종류별 최대 5개
MAX_PER_ROW_TOTAL = 5     # 행당 전체 최대 5개
ALLOWED_TYPES_LATE = {"오탈자", "띄어쓰기"}  # 3차/품질점검 허용 유형
SIMILARITY_THRESHOLD = 0.85  # 85% 이상 유사하면 중복으로 판단
```

## 핵심 함수

### 1. `normalize_error_type(v: str) -> str`
- 오류 유형 정규화
- "링크오류" → "링크"
- "책갈피추가" → "추가·삭제"

### 2. `split_lines(val) -> List[str]`
- 셀 내용을 줄 단위로 분리
- `\r\n`, `\n`, `\r` 모든 줄바꿈 문자 처리
- 빈 줄 제거 및 공백 정리

### 3. `apply_rich_diff_for_bidir(cell, items)`
- 수정 내역에 diff 스타일 적용
- 항목이 1개일 때만 Rich Text(diff) 적용, 여러 개면 줄바꿈 텍스트로 기록
- 변경되지 않은 부분: 검은색, 변경된 부분: 빨간색, 화살표(→): 회색
- 오류유형이 "추가·삭제"인 경우 `after` 앞에 "추가 " 접두사를 강제 부여하고, "추가 " 부분을 빨간색으로 강조
- `CellRichText`, `TextBlock`, `InlineFont`, `SequenceMatcher` 사용

### 4. `compute_last_row(ws1) -> int`
- 실제 데이터가 있는 마지막 행 계산
- L, M, N 열에 값이 있는 행까지 확인

### 5. `merge_inputs_from_ws1_ws2_ws4(ws1, ws2, ws4) -> List[Dict]`
- **1차 점검·2차 점검·품질점검 시트의 L/M/N 입력 데이터를 제어번호(B열) 기준으로 메모리상에서 병합**
- 시트에는 아무것도 쓰지 않고, 순수 in-memory 리스트만 반환
- 반환 형태:
  ```python
  [{"a_to_k": [v1..v11], "err": [str,...], "page": [str,...], "fix": [str,...]}, ...]
  ```
- 알고리즘:
  1. `compute_last_row`로 ws1·ws2·ws4 각각의 마지막 행 산출
  2. dict로 그룹화: 키 = `str(B열).strip()`, 빈 제어번호는 `("__nokey__", sheet_id, r)` 고유키로 처리(절대 다른 행과 병합 안 됨)
  3. ws1을 먼저 스캔하며 첫 등장 시 A~K 캡처, L/M/N은 `split_lines`로 누적
  4. ws2를 스캔하며 동일 키는 L/M/N만 누적, 신규 키는 A~K도 캡처
  5. ws4를 스캔하며 동일 키는 L/M/N만 누적, 신규 키는 A~K도 캡처
  6. `groups.values()`를 리스트로 반환 (ws1 등장 순서가 앞, ws2-only, ws4-only가 차례로 뒤)
- 특징:
  - 동일 제어번호가 **비인접 위치**에 있어도 모두 한 그룹으로 합쳐짐
  - 세 시트에 동일 제어번호가 있으면 세 시트의 L/M/N 항목이 모두 누적됨
  - A~K열은 모든 시트가 동일 내용이라는 전제 하에 첫 등장값을 사용(검증 없음)
  - 완전 빈 행(B/L/M/N 모두 비어있음)은 무시
  - 시트를 전혀 수정하지 않으므로 후속 단계에서 4개 시트를 자유롭게 클리어/재기록 가능

### 6. 중복 제거
- 동일/유사 항목을 자동으로 제거하여 과도한 중복 분배를 방지
- 기준: 오류유형이 동일하고, `before`·`after`의 평균 유사도 ≥ 0.85
- 구현: `SequenceMatcher.ratio()`의 평균값 사용

## 메인 처리 로직

### 1단계: 파일 로드 및 검증
```python
wb = openpyxl.load_workbook(SRC_PATH)
for s in SHEETS:
    if s not in wb.sheetnames:
        raise RuntimeError(f"시트 '{s}'를 찾을 수 없습니다.")
```

### 2단계: 입력 시트 병합 (메모리 전용)
```python
merged = merge_inputs_from_ws1_ws2_ws4(ws1, ws2, ws4)
total_rows = len(merged)
if total_rows == 0:
    # 병합 결과가 비었으면 그대로 저장 후 종료
    ...
```
- **1차 점검·2차 점검·품질점검 시트의 L/M/N 데이터를 제어번호 기준으로 통합하여 메모리 리스트로 반환**
- 시트는 전혀 수정하지 않음 — 어떤 곳에도 중간 결과를 되쓰지 않음
- 동일 제어번호의 분산 행, 세 시트의 같은 제어번호 항목, ws2-only·ws4-only 제어번호 모두 처리됨

### 3단계: 4개 시트 데이터 영역 클리어
```python
new_last_row = DATA_START_ROW + total_rows - 1
for ws in (ws1, ws2, ws3, ws4):
    clear_to = max(ws.max_row, new_last_row)
    for r in range(DATA_START_ROW, clear_to + 1):
        for c in range(1, 16):
            ws.cell(r, c).value = None
```
- 4개 시트의 8행~기존 max_row(또는 new_last_row 중 큰 값)까지 모든 셀 값을 `None`으로 초기화
- 구조 변경(`delete_rows`/`insert_rows`)을 쓰지 않고 셀 값만 클리어하여 행 높이/테두리/기타 서식 보존
- 직후 단계에서 메모리 리스트의 데이터로 새로 채울 예정

### 4단계: 메모리 데이터로부터 직접 분배
각 병합 결과(`mrow`)에 대해 다음 단계를 수행:

1. **A~K 기록 (모든 시트 동일)**
   ```python
   for ws in (ws1, ws2, ws3, ws4):
       for c, val in enumerate(mrow["a_to_k"], start=1):
           ws.cell(r, c).value = val
   ```
   - 메모리 리스트의 캡처 A~K 값을 4개 시트에 동일하게 기록

2. **데이터 파싱**
   - `mrow["err"]`, `mrow["page"]`, `mrow["fix"]`를 그대로 사용 (이미 split된 리스트)

3. **원시 아이템 구성**
   ```python
   raw_items = [{
       "err": 오류유형,
       "page": 페이지,
       "before": 수정전,
       "after": 수정후
   }]
   ```

4. **중복 제거**
- 동일/유사 항목 제거(유사도 85% 이상)

5. **종류별 제한 적용**
- 각 오류 유형별로 최대 5개까지만 유지(순서 보존)

6. **전체 개수 제한**
- 행당 최대 5개 항목까지만 처리

7. **시트별 분배(현재 로직)**
- **1차 점검**: 앞의 1개 항목
- **2차 점검**: 남은 항목 중 1개 + 이후 단계에서 허용되지 않은 항목을 수용
- **3차 점검**: 남은 항목 중 "오탈자/띄어쓰기" 우선 1개 (없으면 2차로 이동)
- **품질점검**: 남은 항목 중 "오탈자/띄어쓰기" 우선 1개 (없으면 2차로 이동)

8. **L/M/N 값만 기록 (스타일은 마지막 일괄 단계에서 처리)**
   ```python
   for ws, items in ((ws1, items_1), (ws2, items_2), (ws3, items_3), (ws4, items_4)):
       if not items: continue
       ws.cell(r, COL_ERR).value  = "\n".join(it["err"] for it in items)
       ws.cell(r, COL_PAGE).value = "\n".join(str(it["page"]) for it in items)
       apply_rich_diff_for_bidir(ws.cell(r, COL_FIX), items)
   ```

### 5단계: 스타일 일괄 적용 (마지막 단계)
```python
thin_border = Border(left=Side(style='thin'), right=Side(style='thin'),
                     top=Side(style='thin'), bottom=Side(style='thin'))
center_top = Alignment(wrap_text=True, horizontal='center', vertical='top')
left_top   = Alignment(wrap_text=True, vertical='top')

for sheet in (ws1, ws2, ws3, ws4):
    for row_num in range(DATA_START_ROW, new_last_row + 1):
        sheet.row_dimensions[row_num].auto_size = True
        for col_num in range(1, 16):
            sheet.cell(row_num, col_num).border = thin_border
        sheet.cell(row_num, COL_ERR).alignment  = center_top
        sheet.cell(row_num, COL_PAGE).alignment = center_top
        sheet.cell(row_num, COL_FIX).alignment  = left_top
```
- 데이터 기록과 스타일 적용을 분리하여 마지막에 4개 시트 × 데이터 행 전체에 일괄 적용
- 적용 항목: 행 높이 자동 맞춤 / A~O열 얇은 테두리 / L·M·N 정렬(중앙/좌측 + 자동 줄바꿈 + top)

## 주요 특징

### 1. 우선순위 기반 분배
- 3차/품질점검은 "오탈자", "띄어쓰기"만 허용
- 허용되지 않는 유형은 2차 점검으로 이동

### 2. 시각적 개선
- 수정 내역에서 변경된 부분만 빨간색으로 표시(Rich Text, 단일 항목 시)
- "추가·삭제" 유형은 `after`에 "추가 " 접두사 자동 부여 및 해당 부분 강조
- 줄바꿈 기반 멀티라인 표시 및 모든 셀 텍스트 래핑 적용

### 3. 데이터 무결성
- 원본 순서 보존(ws1 순서 우선, ws2-only 제어번호는 뒤에 추가)
- 빈 데이터 처리(완전 빈 행 자동 무시)
- 오류 유형 정규화
- 중복 항목 제거(유사도 기반)
- **제어번호 기준 행 병합으로 신/구 포맷 호환**(1행=1오류, 1행=다오류 모두 지원)
- **비인접 위치의 동일 제어번호도 한 행으로 통합**

### 4. 제한사항 관리
- 종류별 최대 개수 제한으로 균형있는 분배
- 전체 개수 제한으로 처리 효율성 확보

## 후처리(서식)
- 데이터 기록과 스타일 적용을 분리하여, 5단계에서 한 번에 일괄 처리
- 8행부터 마지막 데이터 행까지 행 높이 자동 맞춤 설정
- 8행부터 O열(15열)까지 얇은 테두리 적용
- L/M/N 정렬도 같은 패스에서 적용(중앙/좌측 + 자동 줄바꿈)

## 출력
- 원본 파일명에 "_자동분류" 접미사가 추가된 새 Excel 파일 생성
- 4개 시트 모두에 적절히 분배된 오류 항목들이 기록됨
- 처리 진행률 콜백 지원(%) 및 상태 메시지 제공

## 사용 시나리오 및 실행 방법
학위논문 검토 과정에서 발견된 모든 오류들을 효율적으로 여러 검토 단계에 분배하여, 각 단계별 담당자가 적절한 분량의 작업을 수행할 수 있도록 지원합니다.

### CLI
```bash
python error_list_auto_classify.py "입력파일.xlsx"
```

### GUI
- `python error_list_gui.py`로 실행하거나, `dist/error_list_gui.exe` 실행
- 현재 디렉토리의 `.xlsx` 목록에서 파일 선택 후 "작업 시작" 클릭
- 진행률과 로그가 우측 패널에 표시되며, 완료 후 결과 파일을 자동으로 엽니다(가능한 경우)
