import os

def analyze_pdf_txt_folders(base_folder, output_filename="result.txt"):
    # 지정한 상위 폴더(pdf 폴더)가 존재하는지 확인
    if not os.path.exists(base_folder):
        print(f"오류: '{base_folder}' 폴더를 찾을 수 없습니다. 경로를 확인해주세요.")
        return

    results = []

    print("폴더 탐색 및 파일 분석을 시작합니다...")

    # os.walk를 이용해 모든 하위 폴더를 자동으로 탐색
    for root, dirs, files in os.walk(base_folder):
        for filename in files:
            # 확장자가 .txt인 파일만 찾음
            if filename.endswith('.txt') and filename != output_filename:
                file_path = os.path.join(root, filename)
                
                # 파일이 위치한 바로 위 폴더명이 '제어번호'가 됩니다.
                # 예: pdf\C0012\KDMT1198516612\abc.txt -> 제어번호: KDMT1198516612
                control_number = os.path.basename(root)
                
                # 윈도우 인코딩 오류 방지 (utf-8 우선 시도 후 실패 시 cp949 재시도)
                encodings = ['utf-8', 'cp949']
                content = None
                
                for encoding in encodings:
                    try:
                        with open(file_path, 'r', encoding=encoding) as f:
                            content = f.read()
                        break  # 읽기 성공 시 루프 탈출
                    except UnicodeDecodeError:
                        continue
                
                # 파일을 정상적으로 읽은 경우에만 계산
                if content is not None:
                    # 줄 수 계산
                    line_count = len(content.splitlines())
                    # 글자 수 계산 (공백/줄바꿈 포함)
                    char_count = len(content)
                    
                    # 결과 리스트에 추가
                    results.append((control_number, line_count, char_count))
                    print(f"[성공] {control_number} - 줄수: {line_count}, 자수: {char_count}")
                else:
                    print(f"[실패] 인코딩 오류로 파일을 읽을 수 없습니다: {file_path}")

    # 모든 작업이 끝나면 결과를 result.txt 파일로 저장
    try:
        with open(output_filename, 'w', encoding='utf-8') as out_f:
            # 첫 줄 헤더 작성
            out_f.write("제어번호\t줄수\t자수\n")
            
            # 데이터 작성
            for control_no, lines, chars in results:
                out_f.write(f"{control_no}\t{lines}\t{chars}\n")
                
        print(f"\n모든 작업이 완료되었습니다! 결과가 '{output_filename}' 파일에 저장되었습니다.")
    except Exception as e:
        print(f"결과 파일 저장 중 오류가 발생했습니다: {e}")

# --------------------------------------------------
# 사용 예시
# --------------------------------------------------
# 실행할 파이썬 스크립트와 'pdf' 폴더가 같은 위치에 있다면 아래대로 실행하시면 됩니다.
# 만약 다른 경로에 있다면 r"C:\A폴더\B폴더\pdf" 처럼 전체 경로를 적어주세요.
target_folder = "pdf" 

analyze_pdf_txt_folders(target_folder)