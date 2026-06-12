# -*- coding: utf-8 -*-
"""두 GUI 앱을 실행하는 허브 런처."""

from __future__ import annotations

import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path

import hub_auth
import proc_state
from elhub_ui.components import DotIndicator, make_wave_frames
from elhub_ui.palette import PALETTE
from elhub_ui.style import apply_theme, set_titlebar_dark
from PySide6.QtCore import QObject, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QMessageBox,
    QPushButton, QScrollArea, QVBoxLayout, QWidget,
)

HERE = Path(__file__).parent
TIMESHEET_FILE = HERE / "timesheet.txt"

# ── 팔레트 (공용 다크 토큰) ──────────────────────────────────────────────────
P = PALETTE["dark"]

# 허브 고유 QSS — 공용 베이스 QSS(elhub_ui.style.make_base_qss) 위에 덧붙는다.
_HUB_QSS = f"""
QFrame#card {{
    border-radius: 12px;
}}
QLabel#name  {{ font-size: 15px; font-weight: 700; }}
QLabel#desc  {{ color: {P['text_muted']}; font-size: 12px; }}
QLabel#status {{ font-size: 11px; }}
QPushButton#launch {{
    background-color: {P['accent']};
    color: {P['accent_fg']};
    border: none;
    border-radius: 8px;
    font-weight: bold;
    font-size: 13px;
    padding: 6px 20px;
    min-width: 80px;
}}
QPushButton#launch:hover   {{ background-color: {P['accent_hover']}; }}
QPushButton#launch:pressed {{ background-color: {P['accent_hover']}; }}
QPushButton#launch:disabled {{
    background-color: {P['border']};
    color: {P['text_muted']};
}}
QScrollArea#cardScroll {{
    background: transparent;
    border: none;
}}
QScrollArea#cardScroll > QWidget > QWidget {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: {P['surface_alt']};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {P['text']};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #FFFFFF;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}
"""


class _AuthSignals(QObject):
    login_done   = Signal(bool, str)   # (success, email_or_err)
    logout_done  = Signal(bool, str)   # (success, err_msg)
    email_ready  = Signal(str)         # email
    auth_invalid = Signal()            # 캐시 토큰이 무효 → 로그아웃 상태로 복원


class AppCard(QFrame):
    """앱 하나를 나타내는 카드 위젯."""

    def __init__(
        self,
        name: str,
        desc: str,
        cwd: Path,
        cmd: list[str],
        restore_msg_key: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("card")
        self._cwd = cwd
        self._cmd = cmd
        self._restore_msg_key = restore_msg_key
        self._proc: subprocess.Popen | None = None
        self._loading = False
        self._anim_frame = 0
        self._running = False  # 카드가 현재 '실행 중'으로 표시되고 있는지
        self._error = False    # 실행 실패 메시지 표시 중인지 (외부 감지로 덮지 않기 위함)
        # 허브가 띄우지 않았지만 외부에서 켜진 인스턴스의 pid (없으면 None).
        self._external_pid: int | None = None
        # 각 앱이 시작 시 기록하는 실행 상태 파일 (proc_state.write/clear).
        self._runtime_file = cwd / "runtime_state.json"

        # ── 레이아웃 ──
        root = QHBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(16)

        # 왼쪽: 도트 + 텍스트
        left = QVBoxLayout()
        left.setSpacing(4)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        self._dot = DotIndicator()
        lbl_name = QLabel(name)
        lbl_name.setObjectName("name")
        name_row.addWidget(self._dot, alignment=Qt.AlignmentFlag.AlignVCenter)
        name_row.addWidget(lbl_name, alignment=Qt.AlignmentFlag.AlignVCenter)
        name_row.addStretch()

        self._lbl_status = QLabel("대기 중")
        self._lbl_status.setObjectName("status")
        self._lbl_status.setStyleSheet(f"color: {P['text_muted']};")

        lbl_desc = QLabel(desc)
        lbl_desc.setObjectName("desc")

        left.addLayout(name_row)
        left.addWidget(lbl_desc)
        left.addWidget(self._lbl_status)

        # 오른쪽: 실행/열기 버튼
        self._btn = QPushButton("실행")
        self._btn.setObjectName("launch")
        self._btn.setFixedHeight(36)
        self._btn.clicked.connect(self._on_btn_clicked)

        root.addLayout(left, stretch=1)
        root.addWidget(self._btn, alignment=Qt.AlignmentFlag.AlignVCenter)

        # 폴링 타이머
        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._poll)
        self._timer.start()

        # 실행 중 프로그레스바 애니메이션 타이머
        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(_ANIM_INTERVAL_MS)
        self._anim_timer.timeout.connect(self._tick_anim)

    def _on_btn_clicked(self) -> None:
        # 허브가 띄운 프로세스든, 외부에서 켜진 인스턴스든 살아 있으면 그 창을 띄운다.
        pid = None
        if self._proc and self._proc.poll() is None:
            pid = self._proc.pid
        elif self._external_pid is not None:
            pid = self._external_pid
        if pid is not None:
            restore_msg = (
                _get_restore_msg(self._restore_msg_key)
                if self._restore_msg_key and sys.platform == "win32"
                else 0
            )
            _focus_pid_window(pid, restore_msg)
        else:
            self._launch()

    def _launch(self) -> None:
        self._error = False
        try:
            self._proc = subprocess.Popen(
                self._cmd, cwd=str(self._cwd),
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
        except FileNotFoundError as e:
            self._set_error(str(e))
            return
        self._loading = True
        self._anim_frame = 0
        self._dot.set_running(True)
        self._lbl_status.setText("실행 중")
        self._lbl_status.setStyleSheet(f"color: {P['green']};")
        self._btn.setText(_PROGRESS_FRAMES[0])
        self._btn.setEnabled(False)
        self._anim_timer.start()

    def _tick_anim(self) -> None:
        self._anim_frame = (self._anim_frame + 1) % len(_PROGRESS_FRAMES)
        self._btn.setText(_PROGRESS_FRAMES[self._anim_frame])

    def _poll(self) -> None:
        # 1) 허브가 직접 띄운 프로세스가 있으면 그 생사를 우선 확인한다.
        if self._proc is not None:
            if self._proc.poll() is None:
                if self._loading and _has_visible_window(self._proc.pid):
                    self._loading = False
                    self._anim_timer.stop()
                    self._set_running(True)
                return
            # 종료됨 — 외부 인스턴스 감지로 넘어간다.
            self._loading = False
            self._anim_timer.stop()
            self._proc = None
        # 2) 허브가 띄우지 않았거나 종료된 경우: 외부에서 켜진 인스턴스를 감지한다.
        self._detect_external()

    def _detect_external(self) -> None:
        """앱이 남긴 실행 상태 파일로 외부 인스턴스의 실행 여부를 반영한다."""
        if self._error:
            return  # 실행 실패 메시지는 다음 사용자 조작 전까지 유지한다.
        state = proc_state.read_live(self._runtime_file)
        pid = state.get("pid") if isinstance(state, dict) else None
        self._external_pid = pid if isinstance(pid, int) else None
        running = self._external_pid is not None
        if running != self._running:
            self._set_running(running)

    def _set_running(self, running: bool) -> None:
        self._running = running
        self._dot.set_running(running)
        self._btn.setText("열기" if running else "실행")
        self._btn.setEnabled(True)
        if running:
            self._lbl_status.setText("실행 중")
            self._lbl_status.setStyleSheet(f"color: {P['green']};")
        else:
            self._lbl_status.setText("대기 중")
            self._lbl_status.setStyleSheet(f"color: {P['text_muted']};")

    def _set_error(self, msg: str) -> None:
        self._loading = False
        self._error = True
        self._running = False
        self._anim_timer.stop()
        self._dot.set_running(False)
        self._btn.setText("실행")
        self._btn.setEnabled(True)
        self._lbl_status.setText(f"오류: {msg}")
        self._lbl_status.setStyleSheet(f"color: {P['red']};")


_RESTORE_MSGS: dict[str, int] = {}

_PROGRESS_FRAMES = make_wave_frames()
_ANIM_INTERVAL_MS = 110


def _has_visible_window(pid: int) -> bool:
    """프로세스(및 자손) PID 트리 안에 가시적인 일반 창이 하나라도 있으면 True."""
    if sys.platform != "win32":
        return True
    try:
        import ctypes
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
        pid_set = _get_process_tree(pid)
        found = [False]

        def _cb(hwnd: int, _: int) -> bool:
            if found[0]:
                return False
            pid_buf = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
            if pid_buf.value not in pid_set:
                return True
            if user32.GetParent(hwnd):
                return True
            if not user32.IsWindowVisible(hwnd):
                return True
            ex_style = user32.GetWindowLongW(hwnd, -20)
            buf = ctypes.create_unicode_buffer(64)
            user32.GetWindowTextW(hwnd, buf, 64)
            title = buf.value
            if title and not (ex_style & 0x80) and not title.startswith("_q_") and title != "QTrayIconMessageWindow":
                found[0] = True
                return False
            return True

        user32.EnumWindows(WNDENUMPROC(_cb), 0)
        return found[0]
    except Exception:
        return False


def _get_restore_msg(app_key: str) -> int:
    """앱별 RegisterWindowMessage ID를 캐시해 반환한다."""
    if app_key not in _RESTORE_MSGS:
        import ctypes
        _RESTORE_MSGS[app_key] = ctypes.windll.user32.RegisterWindowMessageW(app_key)
    return _RESTORE_MSGS[app_key]


def _get_process_tree(root_pid: int) -> set[int]:
    """ToolHelp32 스냅샷으로 root_pid 와 그 모든 자손 PID 집합을 반환한다."""
    import ctypes

    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize",              ctypes.c_ulong),
            ("cntUsage",            ctypes.c_ulong),
            ("th32ProcessID",       ctypes.c_ulong),
            ("th32DefaultHeapID",   ctypes.c_void_p),
            ("th32ModuleID",        ctypes.c_ulong),
            ("cntThreads",          ctypes.c_ulong),
            ("th32ParentProcessID", ctypes.c_ulong),
            ("pcPriClassBase",      ctypes.c_long),
            ("dwFlags",             ctypes.c_ulong),
            ("szExeFile",           ctypes.c_wchar * 260),
        ]

    k32 = ctypes.windll.kernel32
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == ctypes.c_void_p(-1).value:
        return {root_pid}

    parent_of: dict[int, int] = {}
    entry = PROCESSENTRY32W()
    entry.dwSize = ctypes.sizeof(PROCESSENTRY32W)
    try:
        if k32.Process32FirstW(snap, ctypes.byref(entry)):
            while True:
                parent_of[entry.th32ProcessID] = entry.th32ParentProcessID
                if not k32.Process32NextW(snap, ctypes.byref(entry)):
                    break
    finally:
        k32.CloseHandle(snap)

    # BFS로 root_pid 의 모든 자손 수집
    result: set[int] = {root_pid}
    queue = [root_pid]
    while queue:
        cur = queue.pop()
        for pid, ppid in parent_of.items():
            if ppid == cur and pid not in result:
                result.add(pid)
                queue.append(pid)
    return result


def _focus_pid_window(pid: int, restore_msg: int = 0) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)

        pid_set = _get_process_tree(pid)
        candidates: list[tuple[int, str]] = []   # (hwnd, title)
        tray_hwnds: list[int] = []

        PROCESS_QUERY_LIMITED = 0x1000
        k32 = ctypes.windll.kernel32

        def _is_python_pid(p: int) -> bool:
            hproc = k32.OpenProcess(PROCESS_QUERY_LIMITED, False, p)
            if not hproc:
                return False
            try:
                name_buf = ctypes.create_unicode_buffer(260)
                size = ctypes.c_ulong(260)
                ok = k32.QueryFullProcessImageNameW(hproc, 0, name_buf, ctypes.byref(size))
                return ok and "python" in name_buf.value.lower()
            finally:
                k32.CloseHandle(hproc)

        def _cb_all(hwnd: int, _: int) -> bool:
            pid_buf = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
            win_pid = pid_buf.value
            if win_pid not in pid_set:
                return True
            if user32.GetParent(hwnd):
                return True
            if not _is_python_pid(win_pid):
                return True
            ex_style = user32.GetWindowLongW(hwnd, -20)
            buf = ctypes.create_unicode_buffer(64)
            user32.GetWindowTextW(hwnd, buf, 64)
            title = buf.value
            if title == "QTrayIconMessageWindow":
                tray_hwnds.append(hwnd)
            elif title and not (ex_style & 0x80) and not title.startswith("_q_"):
                candidates.append((hwnd, title))
            return True

        user32.EnumWindows(WNDENUMPROC(_cb_all), 0)

        if not candidates and not tray_hwnds:
            return

        if len(candidates) > 1:
            class _RECT(ctypes.Structure):
                _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                             ("r", ctypes.c_long), ("b", ctypes.c_long)]
            def _area(h: int) -> int:
                rc = _RECT()
                user32.GetWindowRect(h, ctypes.byref(rc))
                return max(0, (rc.r - rc.l) * (rc.b - rc.t))
            candidates.sort(key=lambda x: _area(x[0]), reverse=True)

        hwnd, title = candidates[0] if candidates else (0, "")
        is_visible = bool(user32.IsWindowVisible(hwnd)) if hwnd else False
        is_iconic  = bool(user32.IsIconic(hwnd))        if hwnd else False

        SWP_NOMOVE    = 0x0002
        SWP_NOSIZE    = 0x0001
        WM_SYSCOMMAND = 0x0112
        SC_RESTORE    = 0xF120

        if not is_visible:
            # 트레이 숨김: WA_WState_Hidden은 Qt만 해제 가능
            # PostMessageW(비동기) → nativeEvent → showNormal()
            if restore_msg and hwnd:
                user32.PostMessageW(hwnd, restore_msg, 0, 0)
            if tray_hwnds:
                WM_APP_NOTIFY    = 0x8000 + 101
                WM_LBUTTONDBLCLK = 0x0203
                user32.PostMessageW(tray_hwnds[0], WM_APP_NOTIFY, 0, WM_LBUTTONDBLCLK)
        else:
            # 최소화 또는 가려짐: 허브가 포그라운드 권한으로 직접 처리
            if is_iconic:
                user32.SendMessageW(hwnd, WM_SYSCOMMAND, SC_RESTORE, 0)

            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p, ctypes.c_ssize_t,
                ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int,
                ctypes.c_uint,
            ]
            HWND_TOPMOST   = ctypes.c_ssize_t(-1).value
            HWND_NOTOPMOST = ctypes.c_ssize_t(-2).value
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)
            user32.SetForegroundWindow(hwnd)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE)

    except Exception:
        pass


class HubWindow(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("점검 납품")
        self.setMinimumWidth(480)

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(12)

        title = QLabel("점검 납품")
        title.setStyleSheet(f"font-size: 18px; font-weight: 700; color: {P['text']};")
        root.addWidget(title)

        subtitle = QLabel("실행할 앱을 선택하세요")
        subtitle.setStyleSheet(f"font-size: 12px; color: {P['text_muted']}; margin-bottom: 4px;")
        root.addWidget(subtitle)

        backup_tool_cmd = _resolve_app_cmd("backup-tool", "main.py")
        scrape_cmd = _resolve_app_cmd("scrape_dist_app", "new_gui_app.py")
        error_list_cmd = _resolve_app_cmd("error_list_dist", "error_list_gui.py")
        dummy_cmd = [sys.executable, "-c", "pass"]

        cards_container = QWidget()
        cards_layout = QVBoxLayout(cards_container)
        cards_layout.setContentsMargins(0, 0, 0, 0)
        cards_layout.setSpacing(12)

        cards_layout.addWidget(AppCard(
            name="실시간 폴더 백업",
            desc="폴더를 감시해 변경 파일을 자동 백업 · Google Drive 동기화",
            cwd=HERE / "backup-tool",
            cmd=backup_tool_cmd,
            restore_msg_key="DeliveryBackup.Restore",
        ))
        cards_layout.addWidget(AppCard(
            name="스크래핑+자동분배",
            desc="구글 시트 스크래핑 → 엑셀 자동 분류 · 서식 적용",
            cwd=HERE / "scrape_dist_app",
            cmd=scrape_cmd,
            restore_msg_key="ScrapeDistApp.Restore",
        ))
        cards_layout.addWidget(AppCard(
            name="오류항목 자동 분배",
            desc="엑셀 오류리스트 자동 분류 · 서식 적용",
            cwd=HERE / "error_list_dist",
            cmd=error_list_cmd,
        ))
        cards_layout.addStretch(1)

        self._cards_scroll = QScrollArea()
        self._cards_scroll.setObjectName("cardScroll")
        self._cards_scroll.setWidget(cards_container)
        self._cards_scroll.setWidgetResizable(True)
        self._cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._cards_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._cards_layout = cards_layout
        root.addWidget(self._cards_scroll)

        # 카드 3개 분량으로 스크롤 영역 최대 높이 제한
        QTimer.singleShot(0, self._adjust_scroll_height)

        # ── 구분선 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background-color: {P['border']}; max-height: 1px; border: none;")
        root.addWidget(sep)

        # ── 구글 계정 행 ──
        auth_row = QHBoxLayout()
        auth_row.setSpacing(8)
        self._dot_auth = DotIndicator()
        self._lbl_auth = QLabel("구글 계정: 로그인 안 됨")
        self._lbl_auth.setObjectName("status")
        self._btn_auth = QPushButton("로그인")
        self._btn_auth.setObjectName("launch")
        self._btn_auth.setFixedHeight(36)
        self._btn_auth.clicked.connect(self._on_auth_clicked)
        auth_row.addWidget(self._dot_auth, alignment=Qt.AlignmentFlag.AlignVCenter)
        auth_row.addWidget(self._lbl_auth, alignment=Qt.AlignmentFlag.AlignVCenter)
        auth_row.addStretch()
        auth_row.addWidget(self._btn_auth, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(auth_row)

        # ── 출퇴근 행 ──
        commute_row = QHBoxLayout()
        commute_row.setSpacing(8)
        lbl_commute = QLabel("출퇴근")
        lbl_commute.setObjectName("status")
        self._lbl_commute_record = QLabel("")
        self._lbl_commute_record.setObjectName("status")
        self._btn_commute = QPushButton("출근하기")
        self._btn_commute.setObjectName("launch")
        self._btn_commute.setFixedHeight(36)
        self._btn_commute.clicked.connect(self._on_commute_clicked)
        commute_row.addWidget(lbl_commute, alignment=Qt.AlignmentFlag.AlignVCenter)
        commute_row.addWidget(self._lbl_commute_record, alignment=Qt.AlignmentFlag.AlignVCenter)
        commute_row.addStretch()
        commute_row.addWidget(self._btn_commute, alignment=Qt.AlignmentFlag.AlignVCenter)
        root.addLayout(commute_row)

        # 출퇴근 debounce·애니메이션 상태
        self._commute_next_text = "출근하기"
        self._commute_next_record_text = ""
        self._commute_anim_frame = 0
        self._commute_anim_timer = QTimer(self)
        self._commute_anim_timer.setInterval(_ANIM_INTERVAL_MS)
        self._commute_anim_timer.timeout.connect(self._tick_commute_anim)
        self._commute_debounce_timer = QTimer(self)
        self._commute_debounce_timer.setSingleShot(True)
        self._commute_debounce_timer.timeout.connect(self._finish_commute_debounce)

        # 크로스 스레드 신호
        self._auth_signals = _AuthSignals()
        self._auth_signals.login_done.connect(self._on_login_done)
        self._auth_signals.logout_done.connect(self._on_logout_done)
        self._auth_signals.email_ready.connect(lambda email: self._refresh_auth_ui(True, email))
        self._auth_signals.auth_invalid.connect(self._on_auth_invalid)

        # 시작 시 로그인 상태 반영
        self._auth_busy = False
        self._login_cancelled = False
        self._current_email = ""
        self._auth_logged_in = False  # 마지막으로 UI에 반영된 로그인 상태
        self._refresh_auth_ui(hub_auth.is_logged_in())
        if hub_auth.is_logged_in():
            threading.Thread(target=self._fetch_email_worker, daemon=True).start()

        # 다른 프로세스(backup-tool 등)에서의 로그인/로그아웃을 감지해 허브 UI를 동기화한다.
        # 토큰은 Windows 자격 증명 관리자에 공유되므로 is_logged_in() 으로 폴링한다(네트워크 없음).
        self._auth_poll_timer = QTimer(self)
        self._auth_poll_timer.setInterval(3000)
        self._auth_poll_timer.timeout.connect(self._poll_auth_state)
        self._auth_poll_timer.start()

        # 출퇴근 버튼 초기 상태: 오늘 마지막이 "출근"이면 "퇴근하기", 그 외엔 "출근하기"
        last_ts, last_action = self._read_last_record()
        last_date = last_ts.split(" ", 1)[0] if last_ts else ""
        today = datetime.now().strftime("%Y-%m-%d")
        if last_date == today and last_action == "출근":
            self._btn_commute.setText("퇴근하기")
        else:
            self._btn_commute.setText("출근하기")
        if last_ts:
            self._lbl_commute_record.setText(f"{last_ts} {last_action}")

    def _adjust_scroll_height(self) -> None:
        """카드 3개 분량을 상한으로, 실제 카드 수에 맞춰 스크롤 영역 높이를 고정한다."""
        layout = self._cards_layout
        first = layout.itemAt(0).widget() if layout.count() else None
        if not first:
            return
        cap = first.sizeHint().height() * 3 + layout.spacing() * 2
        content = self._cards_scroll.widget().sizeHint().height()
        self._cards_scroll.setFixedHeight(min(content, cap))

    # ── 구글 계정 ────────────────────────────────────────────────────────────

    def _refresh_auth_ui(self, logged_in: bool, email: str = "") -> None:
        self._auth_logged_in = logged_in
        self._dot_auth.set_running(logged_in)
        if logged_in and email:
            self._lbl_auth.setText(f"구글 계정: {email}")
            self._current_email = email
        elif logged_in:
            self._lbl_auth.setText("구글 계정: 확인 중...")
        else:
            self._lbl_auth.setText("구글 계정: 로그인 안 됨")
            self._current_email = ""
        if self._auth_busy:
            self._btn_auth.setText("취소")
        elif logged_in:
            self._btn_auth.setText("로그아웃")
        else:
            self._btn_auth.setText("로그인")
        self._btn_auth.setEnabled(True)

    def _poll_auth_state(self) -> None:
        """자격 증명 관리자의 토큰 존재 여부를 주기적으로 확인해 외부 변경을 동기화한다.

        backup-tool 에서 로그인하면 허브도 로그인 상태로, 로그아웃하면 로그아웃 상태로 반영한다.
        허브 자체 로그인/로그아웃 진행 중(_auth_busy)에는 간섭하지 않는다.
        """
        if self._auth_busy:
            return
        current = hub_auth.is_logged_in()
        if current == self._auth_logged_in:
            return
        if current:
            # 외부에서 로그인됨 → "확인 중..." 표시 후 이메일 조회
            self._refresh_auth_ui(True)
            threading.Thread(target=self._fetch_email_worker, daemon=True).start()
        else:
            # 외부에서 로그아웃됨
            self._refresh_auth_ui(False)

    def _on_auth_clicked(self) -> None:
        if self._auth_busy:
            # 로그인 진행 중 → 취소 (서버 루프가 최대 0.5 초 내에 종료됨)
            self._login_cancelled = True
            self._auth_busy = False
            hub_auth.cancel_login()
            self._refresh_auth_ui(False)
            return
        if hub_auth.is_logged_in():
            # 백업툴이 구글 드라이브 연동 중이면 로그아웃 전 확인을 받는다.
            if self._is_gdrive_backup_active():
                reply = QMessageBox.question(
                    self, "로그아웃 확인",
                    "현재 구글 드라이브 백업 연동중입니다. 로그아웃하시겠습니까?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            self._auth_busy = True
            self._btn_auth.setEnabled(False)
            threading.Thread(target=self._logout_worker, daemon=True).start()
        else:
            self._auth_busy = True
            self._login_cancelled = False
            self._lbl_auth.setText("구글 계정: 로그인 중... (브라우저를 확인해 주세요)")
            self._btn_auth.setText("취소")  # _auth_busy=True이므로 직접 설정
            threading.Thread(target=self._login_worker, daemon=True).start()

    def _is_gdrive_backup_active(self) -> bool:
        """백업툴이 실행 중이고 구글 드라이브 연동(gdrive_enabled)이 켜져 있는지 확인한다.

        허브가 직접 띄운 인스턴스든, 먼저 켜져 있던 외부 인스턴스든 동일하게
        백업툴의 실행 상태 파일을 통해 판별한다. (pid + 생성시각으로 생존 검증)
        """
        state = proc_state.read_live(HERE / "backup-tool" / "runtime_state.json")
        return bool(state and state.get("gdrive_enabled", False))

    def _login_worker(self) -> None:
        try:
            email = hub_auth.login()
            self._auth_signals.login_done.emit(True, email)
        except Exception as e:
            self._auth_signals.login_done.emit(False, str(e))

    def _logout_worker(self) -> None:
        try:
            hub_auth.logout()
            self._auth_signals.logout_done.emit(True, "")
        except Exception as e:
            self._auth_signals.logout_done.emit(False, str(e))

    def _fetch_email_worker(self) -> None:
        try:
            email = hub_auth.get_email()
            self._auth_signals.email_ready.emit(email)
        except Exception:
            # 캐시 토큰이 만료/폐기됨 → 자동 로그아웃해 UI 갇힘 방지
            try:
                hub_auth.logout()
            except Exception:
                pass
            self._auth_signals.auth_invalid.emit()

    def _on_login_done(self, success: bool, email_or_err: str) -> None:
        if self._login_cancelled:
            self._login_cancelled = False
            return  # UI는 취소 시점에 이미 복구됨
        self._auth_busy = False
        if success:
            self._refresh_auth_ui(True, email_or_err)
        else:
            self._refresh_auth_ui(False)
            self._lbl_auth.setText(f"구글 계정: 로그인 실패 — {email_or_err}")

    def _on_logout_done(self, success: bool, msg: str) -> None:
        self._auth_busy = False
        self._refresh_auth_ui(False)

    def _on_auth_invalid(self) -> None:
        """캐시 토큰이 무효해 자동 로그아웃됨 — UI를 로그아웃 상태로 복원하고 안내."""
        self._auth_busy = False
        self._refresh_auth_ui(False)
        self._lbl_auth.setText("구글 계정: 세션 만료 — 다시 로그인해 주세요")

    # ── 출퇴근 ──────────────────────────────────────────────────────────────

    def _read_last_record(self) -> tuple[str, str]:
        """timesheet.txt 마지막 줄에서 (timestamp "YYYY-MM-DD HH:MM:SS", action) 반환. 실패 시 ("", "")."""
        if not TIMESHEET_FILE.exists():
            return ("", "")
        try:
            with TIMESHEET_FILE.open("r", encoding="utf-8") as f:
                lines = [ln.rstrip("\n") for ln in f if ln.strip()]
            if not lines:
                return ("", "")
            parts = lines[-1].split("\t")
            if len(parts) < 3:
                return ("", "")
            ts, _email, action = parts[0], parts[1], parts[2]
            if action not in ("출근", "퇴근"):
                return ("", "")
            return (ts, action)
        except Exception:
            return ("", "")

    def _append_timesheet(self, ts: str, action: str) -> None:
        """ts, 이메일, action 을 timesheet.txt 에 한 줄 추가한다."""
        line = f"{ts}\t{self._current_email}\t{action}\n"
        try:
            with TIMESHEET_FILE.open("a", encoding="utf-8") as f:
                f.write(line)
        except OSError:
            pass  # 디스크·권한 오류는 무시 — UI 갇힘 방지

    def _on_commute_clicked(self) -> None:
        # 디바운스 진행 중엔 클릭 무시 (버튼이 disabled 상태지만 안전망)
        if self._commute_debounce_timer.isActive():
            return
        action = "출근" if self._btn_commute.text() == "출근하기" else "퇴근"
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self._append_timesheet(ts, action)
        # 1초 동안 버튼 비활성 + 파도 애니메이션, 종료 후 토글·기록 시각 표시
        self._commute_next_text = "퇴근하기" if action == "출근" else "출근하기"
        self._commute_next_record_text = f"{ts} {action}"
        self._btn_commute.setEnabled(False)
        self._commute_anim_frame = 0
        self._btn_commute.setText(_PROGRESS_FRAMES[0])
        self._commute_anim_timer.start()
        self._commute_debounce_timer.start(1000)

    def _tick_commute_anim(self) -> None:
        self._commute_anim_frame = (self._commute_anim_frame + 1) % len(_PROGRESS_FRAMES)
        self._btn_commute.setText(_PROGRESS_FRAMES[self._commute_anim_frame])

    def _finish_commute_debounce(self) -> None:
        self._commute_anim_timer.stop()
        self._btn_commute.setText(self._commute_next_text)
        self._btn_commute.setEnabled(True)
        if self._commute_next_record_text:
            self._lbl_commute_record.setText(self._commute_next_record_text)

    def showEvent(self, event):
        super().showEvent(event)
        set_titlebar_dark(int(self.winId()), "dark")


def _resolve_app_cmd(subdir: str, script: str) -> list[str]:
    """앱 서브폴더에 맞는 Python 인터프리터를 찾아 실행 명령을 반환한다.

    .venv 가 존재하면 그 Python 을 직접 사용하고,
    없으면 uv run python 을 시도, 둘 다 없으면 현재 인터프리터로 폴백.
    """
    venv_python = HERE / subdir / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        return [str(venv_python), script]

    import shutil
    if shutil.which("uv"):
        return ["uv", "run", "python", script]

    return [sys.executable, script]


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("앱 허브")
    apply_theme(app, "dark", extra_qss=_HUB_QSS)
    window = HubWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
