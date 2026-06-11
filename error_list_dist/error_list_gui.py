# -*- coding: utf-8 -*-
import os
import sys
import threading
import queue
import time
import tkinter as tk
from tkinter import ttk, messagebox

from error_list_auto_classify import process_error_list


def list_xlsx_files(directory: str):
    files = []
    try:
        for name in os.listdir(directory):
            if not name.lower().endswith('.xlsx'):
                continue
            if name.startswith('~$'):
                continue  # Excel 임시 파일 제외
            base, ext = os.path.splitext(name)
            if base.endswith('_자동분류'):
                continue  # 출력물은 선택 목록에서 제외
            files.append(name)
    except Exception:
        pass
    return sorted(files)


class StdoutRedirector:
    def __init__(self, q: queue.Queue, prefix: str = ""):
        self.q = q
        self.prefix = prefix

    def write(self, s):
        s = str(s)
        if s:
            self.q.put(self.prefix + s)

    def flush(self):
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("엑셀 오류리스트 자동분류 - GUI")
        self.geometry("820x600")
        self.minsize(760, 520)

        self.stdout_queue = queue.Queue()
        self._orig_stdout = sys.stdout
        self._orig_stderr = sys.stderr
        sys.stdout = StdoutRedirector(self.stdout_queue)
        sys.stderr = StdoutRedirector(self.stdout_queue, prefix="[ERR] ")

        self._build_ui()
        self._start_stdout_pump()
        self._refresh_file_list()

    def destroy(self):
        try:
            sys.stdout = self._orig_stdout
            sys.stderr = self._orig_stderr
        except Exception:
            pass
        return super().destroy()

    def _build_ui(self):
        root = self

        main = ttk.Frame(root)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 상단: 파일 목록 + 조작 버튼
        top = ttk.Frame(main)
        top.pack(fill=tk.BOTH, expand=True)

        left = ttk.Frame(top)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(left, text="현재 디렉토리의 .xlsx 파일").pack(anchor=tk.W)
        self.file_list = tk.Listbox(left, selectmode=tk.SINGLE, height=12)
        self.file_list.pack(fill=tk.BOTH, expand=True)
        # 가로 스크롤바 추가 및 연결
        self.file_list_hscroll = ttk.Scrollbar(left, orient=tk.HORIZONTAL, command=self.file_list.xview)
        self.file_list.configure(xscrollcommand=self.file_list_hscroll.set)
        self.file_list_hscroll.pack(fill=tk.X)

        btns = ttk.Frame(left)
        btns.pack(fill=tk.X, pady=(6, 0))
        self.refresh_btn = ttk.Button(btns, text="새로고침", command=self._refresh_file_list)
        self.refresh_btn.pack(side=tk.LEFT)

        self.start_btn = ttk.Button(btns, text="작업 시작", command=self._on_start)
        self.start_btn.pack(side=tk.RIGHT)

        # 우측: 진행 상황
        right = ttk.Frame(top)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0))
        ttk.Label(right, text="진행 상황").pack(anchor=tk.W)

        text_frame = ttk.Frame(right)
        text_frame.pack(fill=tk.BOTH, expand=True)

        self.progress_text = tk.Text(text_frame, wrap=tk.WORD, height=20)
        self.progress_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll = ttk.Scrollbar(text_frame, command=self.progress_text.yview)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.progress_text.configure(yscrollcommand=scroll.set)
        # 읽기 전용 상태로 설정
        self.progress_text.configure(state=tk.DISABLED)

        # 하단: 상태바
        bottom = ttk.Frame(main)
        bottom.pack(fill=tk.X, pady=(8, 0))
        self.status_var = tk.StringVar(value="준비됨")
        self.status = ttk.Label(bottom, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        self.status.pack(fill=tk.X)

    def _append_log(self, text: str):
        # 일시적으로 활성화 후 로그 추가, 다시 비활성화
        self.progress_text.configure(state=tk.NORMAL)
        self.progress_text.insert(tk.END, text)
        self.progress_text.see(tk.END)
        self.progress_text.configure(state=tk.DISABLED)

    def _start_stdout_pump(self):
        def pump():
            try:
                while True:
                    try:
                        line = self.stdout_queue.get_nowait()
                    except queue.Empty:
                        break
                    self._append_log(line)
            finally:
                self.after(80, pump)

        self.after(80, pump)

    def _refresh_file_list(self):
        curdir = os.getcwd()
        files = list_xlsx_files(curdir)
        self.file_list.delete(0, tk.END)
        for f in files:
            self.file_list.insert(tk.END, f)
        self.status_var.set(f"파일 {len(files)}개")
        # 초기 가로 스크롤 위치를 맨 끝으로 이동
        try:
            self.file_list.xview_moveto(1.0)
        except Exception:
            pass

    def _on_start(self):
        sel = self._get_selected_file()
        if not sel:
            messagebox.showwarning("알림", "작업할 .xlsx 파일을 선택하세요.")
            return

        src_path = os.path.abspath(sel)
        self._run_process(src_path)

    def _get_selected_file(self):
        try:
            idx = self.file_list.curselection()
            if not idx:
                return None
            return self.file_list.get(idx[0])
        except Exception:
            return None

    def _set_controls_enabled(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.start_btn.config(state=state)
        self.refresh_btn.config(state=state)

    def _run_process(self, src_path: str):
        self._set_controls_enabled(False)
        self.status_var.set("작업 중…")
        # 읽기 전용이므로 초기화 시 일시적으로 활성화
        self.progress_text.configure(state=tk.NORMAL)
        self.progress_text.delete("1.0", tk.END)
        self.progress_text.configure(state=tk.DISABLED)

        def on_progress(pct: int, msg: str):
            self.stdout_queue.put(f"[{pct:3d}%] {msg}\n")

        def worker():
            try:
                result = process_error_list(src_path, on_progress=on_progress)
                dst_path = result.get("dst_path")
                total = result.get("total_rows", 0)
                copied = result.get("copied_without_processing", False)

                self.stdout_queue.put("\n")
                if copied:
                    self.stdout_queue.put("처리할 데이터가 없어 원본을 저장했습니다.\n")
                else:
                    self.stdout_queue.put(f"총 {total}행 처리 완료.\n")

                # 결과 파일 열기
                try:
                    if sys.platform.startswith('win'):
                        os.startfile(dst_path)  # type: ignore[attr-defined]
                    elif sys.platform == 'darwin':
                        os.system(f"open '{dst_path}'")
                    else:
                        os.system(f"xdg-open '{dst_path}'")
                except Exception:
                    pass

                # UI 갱신
                self.after(0, self._refresh_file_list)
                self.after(0, lambda: self.status_var.set("완료"))
            except Exception as e:
                self.stdout_queue.put(f"[오류] {e}\n")
                self.after(0, lambda: messagebox.showerror("오류", str(e)))
                self.after(0, lambda: self.status_var.set("오류"))
                # 오류 시에도 파일 목록을 최신 상태로 갱신
                self.after(0, self._refresh_file_list)
            finally:
                self.after(0, lambda: self._set_controls_enabled(True))

        threading.Thread(target=worker, daemon=True).start()


def _register_runtime_state():
    """허브가 외부에서도 실행 여부를 알 수 있도록 실행 상태 파일을 남긴다.

    허브 루트(auto/)의 proc_state 모듈에 위임한다. 종료 시 atexit 로 파일을 지운다.
    프로젝트 구조나 모듈이 없어도 앱 실행에는 지장이 없도록 모든 실패를 무시한다.
    """
    try:
        import atexit
        import importlib.util
        from pathlib import Path

        app_dir = Path(__file__).resolve().parent      # error_list_dist/
        ps_path = app_dir.parent / "proc_state.py"     # auto/proc_state.py
        spec = importlib.util.spec_from_file_location("proc_state", ps_path)
        ps = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ps)
        state_file = app_dir / "runtime_state.json"
        ps.write(state_file)
        atexit.register(lambda: ps.clear(state_file))
    except Exception:
        pass


def main():
    _register_runtime_state()
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()


