"""PySide6 메인 윈도우: 경로/제외 목록 입력, 감시 시작·중지, 로그 출력, 트레이 아이콘."""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QPoint, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPalette, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressDialog,
    QPushButton,
    QStyle,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from .. import ICON_PATH
from .palette import LOG_COLORS, PALETTE
from .style import apply_theme, set_titlebar_color, set_window_rounded

# 허브 앱이 외부에서 창 복원을 요청할 때 사용하는 Windows 등록 메시지.
# RegisterWindowMessageW 는 같은 문자열에 대해 같은 ID 를 반환하므로
# 송신 측(허브)과 수신 측(이 앱) 양쪽에서 동일한 ID 를 얻는다.
_HUB_RESTORE_MSG: int = (
    ctypes.windll.user32.RegisterWindowMessageW("DeliveryBackup.Restore")
    if hasattr(ctypes, "windll")
    else 0
)

# ctypes.wintypes 에는 MSG 구조체가 없으므로 직접 정의한다.
# Windows x64: HWND(8) + UINT(4) + padding(4) + WPARAM(8) + LPARAM(8) + DWORD(4) + POINT(8)
if hasattr(ctypes, "windll"):
    class _WinMSG(ctypes.Structure):
        _fields_ = [
            ("hwnd",    ctypes.c_void_p),
            ("message", ctypes.c_uint),
            ("wParam",  ctypes.c_size_t),
            ("lParam",  ctypes.c_ssize_t),
            ("time",    ctypes.c_ulong),
            ("pt_x",    ctypes.c_long),
            ("pt_y",    ctypes.c_long),
        ]
else:
    _WinMSG = None  # type: ignore[assignment,misc]

from .. import config as config_module
from .. import runtime_state
from ..backup_engine import initial_sync
from ..config import BackupConfig
from ..errors import BackupError, ConfigError, SyncError, ValidationError
from ..logger import SessionLogger
from ..watcher import WatcherService
from .signals import WorkerSignals

# 트레이 풍선 알림을 너무 자주 띄우지 않기 위한 최소 간격(초).
_NOTIFY_INTERVAL_SECONDS = 5.0

# 구글 드라이브 자동 업로드 주기 (1시간).
_GDRIVE_INTERVAL_MS = 60 * 60 * 1000

# 구글 드라이브 토글 아이콘 (활성/비활성)
_ASSETS_DIR = Path(__file__).resolve().parent.parent.parent / "assets"
_GDRIVE_ICON_ON = _ASSETS_DIR / "google_drive_icon.svg"
_GDRIVE_ICON_OFF = _ASSETS_DIR / "google_drive_icon_disabled.svg"


class _TitleBar(QWidget):
    """커스텀 타이틀바: 드래그·더블클릭 최대화·윈도우 컨트롤 포함."""

    def __init__(self, win: "MainWindow") -> None:
        super().__init__(win)
        self._win = win
        self._drag_pos: QPoint | None = None
        self.setObjectName("title-bar")
        self.setFixedHeight(38)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 0, 0, 0)
        lay.setSpacing(0)

        # 커스텀 버튼 슬롯 (MainWindow._build_ui 에서 채운다)
        self._slot = QHBoxLayout()
        self._slot.setSpacing(2)
        self._slot.setContentsMargins(0, 3, 0, 3)
        lay.addLayout(self._slot)

        lay.addStretch()

        # 윈도우 컨트롤 (최소화 / 최대화 / 닫기)
        self._max_btn = self._wm("", "wm-btn", self._toggle_max)
        for btn in (
            self._wm("", "wm-btn", win.showMinimized),
            self._max_btn,
            self._wm("", "wm-close", win.close),
        ):
            lay.addWidget(btn)

    def _wm(self, text: str, obj: str, slot) -> QPushButton:
        btn = QPushButton(text)
        btn.setObjectName(obj)
        btn.setFixedSize(46, 38)
        btn.clicked.connect(slot)
        return btn

    def add_button(self, btn: QPushButton) -> None:
        self._slot.addWidget(btn)

    def _toggle_max(self) -> None:
        if self._win.isMaximized():
            self._win.showNormal()
        else:
            self._win.showMaximized()

    def update_max_icon(self) -> None:
        self._max_btn.setText("" if self._win.isMaximized() else "")

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = (
                event.globalPosition().toPoint() - self._win.frameGeometry().topLeft()
            )

    def mouseMoveEvent(self, event) -> None:
        if self._drag_pos and event.buttons() & Qt.MouseButton.LeftButton:
            self._win.move(event.globalPosition().toPoint() - self._drag_pos)

    def mouseReleaseEvent(self, event) -> None:
        self._drag_pos = None

    def mouseDoubleClickEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._toggle_max()


class _GDriveFolderDialog(QDialog):
    """구글 드라이브 폴더를 탐색하며 업로드 대상 폴더를 고르는 모달 대화상자.

    Drive API 호출은 네트워크 블로킹이므로 백그라운드 스레드에서 수행하고,
    결과는 `_folders_loaded` 시그널로 메인 스레드에 전달해 위젯을 갱신한다.
    빠르게 폴더를 옮겨 다닐 때 이전 응답이 늦게 도착해 화면을 덮어쓰지
    않도록 로드마다 세대(generation) 번호로 가드한다.
    """

    # (generation, [(id, name)...], error_message)
    _folders_loaded = Signal(int, list, str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("구글 드라이브 업로드 폴더 선택")
        self.resize(360, 440)

        # 루트부터 현재 폴더까지의 경로 스택: [(id, name), ...]
        self._stack: list[tuple[str, str]] = [("root", "내 드라이브")]
        self._load_gen = 0

        lay = QVBoxLayout(self)

        self._path_label = QLabel()
        self._path_label.setWordWrap(True)
        lay.addWidget(self._path_label)

        nav_row = QHBoxLayout()
        self._up_btn = QPushButton("⬆ 상위 폴더")
        self._up_btn.clicked.connect(self._go_up)
        nav_row.addWidget(self._up_btn)
        nav_row.addStretch()
        lay.addLayout(nav_row)

        self._list = QListWidget()
        self._list.itemDoubleClicked.connect(self._enter_item)
        lay.addWidget(self._list, stretch=1)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        lay.addWidget(self._status)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self._select_btn = QPushButton("이 폴더로 선택")
        self._select_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("취소")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(self._select_btn)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

        self._folders_loaded.connect(self._on_folders_loaded)
        self._load_current()

    def selected_folder(self) -> tuple[str, str]:
        """선택된 (폴더 id, 표시 경로) 를 반환한다."""
        folder_id = self._stack[-1][0]
        path = "/".join(name for _, name in self._stack)
        return folder_id, path

    def _load_current(self) -> None:
        self._load_gen += 1
        gen = self._load_gen
        self._path_label.setText("📁 " + "/".join(name for _, name in self._stack))
        self._up_btn.setEnabled(len(self._stack) > 1)
        self._list.clear()
        self._list.setEnabled(False)
        self._status.setText("불러오는 중...")
        parent_id = self._stack[-1][0]
        threading.Thread(
            target=self._fetch_worker, args=(gen, parent_id), daemon=True
        ).start()

    def _fetch_worker(self, gen: int, parent_id: str) -> None:
        from .. import gdrive
        try:
            folders = gdrive.list_subfolders(parent_id)
            self._folders_loaded.emit(gen, folders, "")
        except Exception as err:
            self._folders_loaded.emit(gen, [], str(err))

    def _on_folders_loaded(self, gen: int, folders: list, error: str) -> None:
        if gen != self._load_gen:
            return  # 더 새로운 로드가 시작됨 — 늦게 온 응답은 버린다.
        self._list.setEnabled(True)
        if error:
            self._status.setText(f"폴더 목록을 불러오지 못했습니다: {error}")
            return
        for fid, name in folders:
            item = QListWidgetItem("📁 " + name)
            item.setData(Qt.ItemDataRole.UserRole, (fid, name))
            self._list.addItem(item)
        if folders:
            self._status.setText("폴더를 더블클릭하면 들어갑니다. '이 폴더로 선택'으로 현재 폴더를 지정하세요.")
        else:
            self._status.setText("하위 폴더가 없습니다. '이 폴더로 선택'으로 현재 폴더를 지정하세요.")

    def _enter_item(self, item: QListWidgetItem) -> None:
        data = item.data(Qt.ItemDataRole.UserRole)
        if data:
            self._stack.append((data[0], data[1]))
            self._load_current()

    def _go_up(self) -> None:
        if len(self._stack) > 1:
            self._stack.pop()
            self._load_current()


class MainWindow(QWidget):
    """백업 프로그램의 메인 화면."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Window)
        self._theme = "dark"
        self.setWindowTitle("실시간 폴더 백업")
        self.resize(420, 540)

        self._watcher = WatcherService()
        self._logger = SessionLogger()
        self._signals = WorkerSignals()
        self._signals.log.connect(self._append_log)
        self._signals.error.connect(self._append_error)
        self._signals.backup.connect(self._on_backup_event)
        self._signals.sync_finished.connect(self._on_sync_finished)
        self._signals.path_backed_up.connect(self._on_path_backed_up)
        self._signals.gdrive_login_finished.connect(self._on_gdrive_login_finished)
        self._sync_thread: threading.Thread | None = None

        # 트레이 관련 상태
        self._tray: QSystemTrayIcon | None = None
        self._tray_toggle = None
        self._force_quit = False
        self._last_backup_notify = 0.0
        self._suppressed_backups = 0

        # 구글 드라이브 자동 업로드 상태
        self._gdrive_timer: QTimer | None = None
        self._gdrive_uploading = False
        # 로그인/로그아웃 진행 중 가드 및 진행 다이얼로그 상태
        self._gdrive_busy = False
        self._gdrive_login_dialog: QProgressDialog | None = None
        self._gdrive_login_cancelled = False
        # 다음 업로드 사이클에서 Drive 로 올릴 백업 파일들의 절대경로
        self._gdrive_pending: set[str] = set()
        # 업로드 대상 Drive 폴더 (id 가 비면 '내 드라이브' 루트)
        self._gdrive_folder_id = ""
        self._gdrive_folder_path = ""

        self._build_ui()
        self._update_theme_btn()
        self._refresh_log_theme()
        self._set_status_label("중지됨", False)
        self._build_tray()
        self._load_initial_config()
        # 설정 복원 후 현재 상태를 런타임 파일에 기록한다(허브가 외부에서 읽음).
        self._update_runtime_state()

    def _update_runtime_state(self) -> None:
        """현재 감시/구글 드라이브 연동 상태를 런타임 상태 파일에 반영한다."""
        runtime_state.write(
            watching=self._watcher.is_running,
            gdrive_enabled=self._gdrive_check.isChecked(),
        )

    def changeEvent(self, event) -> None:
        super().changeEvent(event)
        if event.type() == event.Type.WindowStateChange:
            self._titlebar.update_max_icon()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        set_window_rounded(int(self.winId()))

    def nativeEvent(self, event_type: bytes, message: int):
        if _HUB_RESTORE_MSG and _WinMSG is not None:
            try:
                msg = ctypes.cast(int(message), ctypes.POINTER(_WinMSG)).contents
                if msg.message == _HUB_RESTORE_MSG:
                    self._restore_window()
                    return True, 0
            except Exception:
                pass
        return super().nativeEvent(event_type, message)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        # 외부 레이아웃: 타이틀바는 가장자리까지, 콘텐츠는 안쪽 여백 유지
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- 타이틀바 ----
        self._titlebar = _TitleBar(self)
        outer.addWidget(self._titlebar)

        # ---- 콘텐츠 영역 ----
        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        outer.addWidget(content, stretch=1)

        # ---- 타이틀바 아이콘 버튼 ----
        def _tb_btn(text: str, tip: str, checkable: bool = False) -> QPushButton:
            btn = QPushButton(text)
            btn.setObjectName("toolbar-btn")
            btn.setFixedSize(32, 32)
            btn.setToolTip(tip)
            btn.setCheckable(checkable)
            return btn

        self._toggle_settings_btn = _tb_btn("⚙", "설정 표시/숨김", checkable=True)
        self._toggle_settings_btn.setChecked(False)
        self._toggle_settings_btn.toggled.connect(self._on_settings_visibility_toggled)

        self._toggle_includes_btn = _tb_btn("➕", "지정 목록 표시/숨김", checkable=True)
        self._toggle_includes_btn.setChecked(False)
        self._toggle_includes_btn.toggled.connect(
            lambda checked: self._inc_group.setVisible(checked)
        )

        self._toggle_excludes_btn = _tb_btn("🚫", "제외 목록 표시/숨김", checkable=True)
        self._toggle_excludes_btn.setChecked(False)
        self._toggle_excludes_btn.toggled.connect(
            lambda checked: self._exc_group.setVisible(checked)
        )

        self._theme_btn = _tb_btn("", "테마 전환")
        self._theme_btn.clicked.connect(self._on_theme_toggled)

        for btn in (self._toggle_settings_btn, self._toggle_includes_btn, self._toggle_excludes_btn, self._theme_btn):
            self._titlebar.add_button(btn)

        # ---- 1) 설정 영역 (왼쪽: 디렉토리 그룹, 오른쪽: 구글 드라이브 그룹) ----
        settings_row = QHBoxLayout()

        # 왼쪽 그룹: 백업 디렉토리
        self._dir_group = QGroupBox("디렉토리")
        dir_layout = QVBoxLayout(self._dir_group)
        dir_layout.addWidget(QLabel("백업 대상 디렉토리"))
        src_row = QHBoxLayout()
        self._source_edit = QLineEdit()
        self._source_edit.setReadOnly(True)
        self._src_browse_btn = QPushButton("...")
        self._src_browse_btn.setObjectName("browse-btn")
        self._src_browse_btn.setFixedWidth(30)
        self._src_browse_btn.clicked.connect(self._browse_source)
        src_row.addWidget(self._source_edit)
        src_row.addWidget(self._src_browse_btn)
        dir_layout.addLayout(src_row)
        dir_layout.addWidget(QLabel("백업 저장 디렉토리"))
        dst_row = QHBoxLayout()
        self._backup_edit = QLineEdit()
        self._backup_edit.setReadOnly(True)
        self._dst_browse_btn = QPushButton("...")
        self._dst_browse_btn.setObjectName("browse-btn")
        self._dst_browse_btn.setFixedWidth(30)
        self._dst_browse_btn.clicked.connect(self._browse_backup)
        dst_row.addWidget(self._backup_edit)
        dst_row.addWidget(self._dst_browse_btn)
        dir_layout.addLayout(dst_row)
        dir_layout.addStretch()

        # 오른쪽 그룹: 구글 드라이브 연동 (아이콘 버튼 + 상태)
        self._gdrive_group = QGroupBox("구글 드라이브 연동")
        gdrive_layout = QVBoxLayout(self._gdrive_group)
        self._gdrive_check = QPushButton()
        self._gdrive_check.setCheckable(True)
        self._gdrive_check.setObjectName("gdrive-toggle")
        self._gdrive_check.setIconSize(QSize(48, 48))
        self._gdrive_check.setFixedSize(64, 64)
        self._gdrive_check.setToolTip("구글 드라이브 연동 (1시간 주기 자동 업로드)")
        self._gdrive_check.toggled.connect(self._on_gdrive_toggled)
        self._update_gdrive_icon(False)  # 초기 비활성 아이콘

        self._gdrive_status = QLabel("")
        self._gdrive_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._gdrive_status.setWordWrap(True)
        # 텍스트 길이와 무관하게 오른쪽 컬럼 폭을 일정하게 유지한다.
        self._gdrive_status.setFixedWidth(140)

        # 업로드 대상 Drive 폴더 선택 (로컬 '백업 저장 디렉토리'에 대응)
        self._gdrive_folder_btn = QPushButton("업로드 폴더 선택")
        self._gdrive_folder_btn.clicked.connect(self._browse_gdrive_folder)
        self._gdrive_folder_label = QLabel("")
        self._gdrive_folder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._gdrive_folder_label.setWordWrap(True)
        self._gdrive_folder_label.setFixedWidth(140)

        gdrive_layout.addWidget(self._gdrive_check, alignment=Qt.AlignmentFlag.AlignCenter)
        gdrive_layout.addWidget(self._gdrive_status)
        gdrive_layout.addWidget(self._gdrive_folder_btn)
        gdrive_layout.addWidget(self._gdrive_folder_label)
        gdrive_layout.addStretch()
        # 업로드 폴더 선택칸은 연동 토글이 켜졌을 때만 보인다.
        self._set_gdrive_folder_visible(False)

        settings_row.addWidget(self._dir_group, stretch=1)
        settings_row.addWidget(self._gdrive_group)
        layout.addLayout(settings_row)

        # ---- 2) 지정 목록 영역 ----
        self._inc_group = QGroupBox("백업할 파일 / 하위 디렉토리 직접 지정 (패턴, 예: *.docx, reports)")
        inc_layout = QVBoxLayout(self._inc_group)
        inc_row = QHBoxLayout()
        self._inc_add_btn = QPushButton("추가")
        self._inc_add_btn.clicked.connect(self._add_include)
        self._inc_del_btn = QPushButton("삭제")
        self._inc_del_btn.clicked.connect(self._remove_include)
        inc_row.addWidget(self._inc_add_btn)
        inc_row.addWidget(self._inc_del_btn)
        inc_row.addStretch()
        inc_layout.addLayout(inc_row)
        self._include_list = QListWidget()
        self._include_list.setFixedHeight(80)
        inc_layout.addWidget(self._include_list)
        layout.addWidget(self._inc_group)

        # ---- 3) 제외 목록 영역 ----
        self._exc_group = QGroupBox("제외할 파일 / 하위 디렉토리 (패턴, 예: *.tmp, temp)")
        exc_layout = QVBoxLayout(self._exc_group)
        exc_row = QHBoxLayout()
        self._exc_add_btn = QPushButton("추가")
        self._exc_add_btn.clicked.connect(self._add_exclude)
        self._exc_del_btn = QPushButton("삭제")
        self._exc_del_btn.clicked.connect(self._remove_exclude)
        exc_row.addWidget(self._exc_add_btn)
        exc_row.addWidget(self._exc_del_btn)
        exc_row.addStretch()
        exc_layout.addLayout(exc_row)
        self._exclude_list = QListWidget()
        self._exclude_list.setFixedHeight(80)
        exc_layout.addWidget(self._exclude_list)
        layout.addWidget(self._exc_group)

        # ---- 4) 감시 제어 영역 ----
        ctrl_label_layout = QHBoxLayout()
        self._status_label = QLabel()
        self._status_label.setTextFormat(Qt.TextFormat.RichText)
        ctrl_label_layout.addWidget(self._status_label)
        ctrl_label_layout.addStretch()
        ctrl_button_layout = QHBoxLayout()
        self._toggle_btn = QPushButton("감시 시작")
        self._toggle_btn.clicked.connect(self._toggle_watch)
        ctrl_button_layout.addWidget(self._toggle_btn)
        ctrl_button_layout.addStretch()
        layout.addLayout(ctrl_label_layout)
        layout.addLayout(ctrl_button_layout)

        # ---- 4) 로그 영역 ----
        log_group = QGroupBox("로그")
        log_layout = QVBoxLayout(log_group)
        self._log_view = QPlainTextEdit()
        self._log_view.setObjectName("log")
        self._log_view.setReadOnly(True)
        log_layout.addWidget(self._log_view)
        layout.addWidget(log_group, stretch=1)

        # 초기 기본값: 설정·제외·지정 영역 숨김
        self._dir_group.setVisible(False)
        self._gdrive_group.setVisible(False)
        self._exc_group.setVisible(False)
        self._inc_group.setVisible(False)

    def _on_settings_visibility_toggled(self, checked: bool) -> None:
        """상단 '설정' 토글 — 디렉토리/구글 드라이브 두 그룹을 함께 보이거나 숨긴다."""
        self._dir_group.setVisible(checked)
        self._gdrive_group.setVisible(checked)

    def _build_tray(self) -> None:
        """시스템 트레이 아이콘과 우클릭 메뉴를 구성한다.

        트레이를 쓸 수 없는 환경에서는 조용히 건너뛴다(창 닫기 = 일반 종료).
        """
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return

        # 전용 SVG 아이콘이 있으면 사용하고, 없으면 Qt 기본 하드디스크 아이콘으로 폴백한다.
        if ICON_PATH.exists():
            icon = QIcon(str(ICON_PATH))
        else:
            icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DriveHDIcon)
        self.setWindowIcon(icon)

        self._tray = QSystemTrayIcon(self)
        self._tray.setIcon(icon)
        self._tray.setToolTip("실시간 폴더 백업")

        menu = QMenu()
        open_action = menu.addAction("열기")
        open_action.triggered.connect(self._restore_window)
        menu.addSeparator()
        self._tray_toggle = menu.addAction("감시 시작")
        self._tray_toggle.triggered.connect(self._toggle_watch)
        menu.addSeparator()
        quit_action = menu.addAction("종료")
        quit_action.triggered.connect(self._quit_app)

        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_tray_activated)
        self._tray.show()

    # ------------------------------------------------------ 테마
    def _apply_theme(self, theme: str) -> None:
        self._theme = theme
        apply_theme(QApplication.instance(), theme)
        set_titlebar_color(int(self.winId()), theme)
        self._update_theme_btn()
        self._refresh_log_theme()
        watching = self._watcher.is_running
        status_text = "감시 중" if watching else (
            "초기 동기화 중..." if not self._toggle_btn.isEnabled() else "중지됨"
        )
        self._set_status_label(status_text, watching)

    def _refresh_log_theme(self) -> None:
        """로그 뷰 팔레트 및 기존 텍스트 색을 현재 테마에 맞게 갱신한다."""
        colors = LOG_COLORS.get(self._theme, LOG_COLORS["dark"])
        info_color = QColor(colors["info"])
        error_color = QColor(colors["error"])

        palette = self._log_view.palette()
        palette.setColor(QPalette.ColorRole.Text, info_color)
        self._log_view.setPalette(palette)

        doc = self._log_view.document()
        block = doc.begin()
        while block.isValid():
            color = error_color if "[오류]" in block.text() else info_color
            cur = QTextCursor(block)
            cur.select(QTextCursor.SelectionType.BlockUnderCursor)
            fmt = QTextCharFormat()
            fmt.setForeground(color)
            cur.mergeCharFormat(fmt)
            block = block.next()

    def _update_theme_btn(self) -> None:
        self._theme_btn.setText("☀️" if self._theme == "dark" else "🌙")

    def _on_theme_toggled(self) -> None:
        new_theme = "light" if self._theme == "dark" else "dark"
        self._apply_theme(new_theme)
        self._autosave_config()

    # ------------------------------------------------------ 설정 로드/수집
    def _load_initial_config(self) -> None:
        """저장된 설정을 불러와 위젯을 채운다. 실패해도 빈 설정으로 계속 진행한다."""
        try:
            cfg = config_module.load()
        except ConfigError as err:
            self._append_error(err.detail())
            QMessageBox.warning(self, "설정 불러오기 실패", err.message)
            cfg = BackupConfig()
        self._source_edit.setText(cfg.source_dir)
        self._backup_edit.setText(cfg.backup_dir)
        self._exclude_list.clear()
        self._exclude_list.addItems(cfg.excludes)
        self._include_list.clear()
        self._include_list.addItems(cfg.includes)

        self._gdrive_folder_id = cfg.gdrive_folder_id
        self._gdrive_folder_path = cfg.gdrive_folder_path
        self._update_gdrive_folder_label()

        if cfg.theme != self._theme:
            self._apply_theme(cfg.theme)

        # 이전에 Drive 연동을 켰고 허브에 로그인된 상태라면 토글을 복원한다.
        from .. import gdrive
        if cfg.gdrive_enabled and gdrive.is_logged_in():
            self._gdrive_check.blockSignals(True)
            self._gdrive_check.setChecked(True)
            self._gdrive_check.blockSignals(False)
            self._update_gdrive_icon(True)
            self._gdrive_status.setText("구글 드라이브 연동 활성화됨")
            self._set_gdrive_folder_visible(True)


    def _collect_config(self) -> BackupConfig:
        """현재 위젯 상태로 BackupConfig 를 만든다."""
        excludes = [
            self._exclude_list.item(i).text()
            for i in range(self._exclude_list.count())
        ]
        includes = [
            self._include_list.item(i).text()
            for i in range(self._include_list.count())
        ]
        return BackupConfig(
            source_dir=self._source_edit.text().strip(),
            backup_dir=self._backup_edit.text().strip(),
            excludes=excludes,
            includes=includes,
            theme=self._theme,
            gdrive_enabled=self._gdrive_check.isChecked(),
            gdrive_folder_id=self._gdrive_folder_id,
            gdrive_folder_path=self._gdrive_folder_path,
        )

    # ----------------------------------------------------------- 버튼 핸들러
    def _autosave_config(self) -> None:
        """현재 위젯 상태를 config.json 에 저장한다. 실패는 로그로만 남긴다."""
        try:
            config_module.save(self._collect_config())
        except ConfigError as err:
            self._append_error(err.detail())

    def _browse_source(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "백업 대상 디렉토리 선택")
        if path:
            self._source_edit.setText(path)
            self._autosave_config()

    def _browse_backup(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "백업 저장 디렉토리 선택")
        if path:
            self._backup_edit.setText(path)
            self._autosave_config()

    def _add_exclude(self) -> None:
        text, ok = QInputDialog.getText(
            self, "제외 패턴 추가", "제외할 파일/디렉토리 패턴:"
        )
        if ok and text.strip():
            self._exclude_list.addItem(text.strip())
            self._autosave_config()

    def _remove_exclude(self) -> None:
        removed = False
        for item in self._exclude_list.selectedItems():
            self._exclude_list.takeItem(self._exclude_list.row(item))
            removed = True
        if removed:
            self._autosave_config()

    def _add_include(self) -> None:
        text, ok = QInputDialog.getText(
            self, "지정 패턴 추가", "백업할 파일/디렉토리 패턴:"
        )
        if ok and text.strip():
            self._include_list.addItem(text.strip())
            self._autosave_config()

    def _remove_include(self) -> None:
        removed = False
        for item in self._include_list.selectedItems():
            self._include_list.takeItem(self._include_list.row(item))
            removed = True
        if removed:
            self._autosave_config()

    def _toggle_watch(self) -> None:
        if self._watcher.is_running:
            self._stop_watch()
        else:
            self._start_watch()

    # --------------------------------------------------------- 감시 시작/중지
    def _start_watch(self) -> None:
        """검증 -> 설정 저장 -> 초기 동기화(백그라운드) -> 감시 시작."""
        config = self._collect_config()

        # 1) 검증 — 실패 시 감시에 진입하지 않는다.
        try:
            config_module.validate(config)
        except ValidationError as err:
            QMessageBox.critical(self, "설정 오류", err.message)
            return

        # 2) 설정 저장 — 실패해도 백업 자체는 가능하므로 경고만 하고 계속 진행한다.
        try:
            config_module.save(config)
        except ConfigError as err:
            self._append_error(err.detail())
            QMessageBox.warning(self, "설정 저장 실패", err.message)

        # 3) 감시 세션 로그 파일을 연다 — 실패해도 백업은 가능하므로 경고만 한다.
        try:
            self._logger.start()
        except BackupError as err:
            QMessageBox.warning(self, "로그 파일 생성 실패", err.message)

        # 4) 초기 동기화는 폴더가 크면 오래 걸리므로 백그라운드 스레드에서 수행한다.
        # 새 세션이므로 이전 세션의 Drive 업로드 대기열을 비운다.
        self._gdrive_pending.clear()
        self._set_busy_state()
        self._append_log("감시를 준비합니다.")
        if self._logger.path is not None:
            self._append_log(f"로그 파일: {self._logger.path}")

        self._pending_config = config
        self._sync_thread = threading.Thread(
            target=self._run_initial_sync, args=(config,), daemon=True
        )
        self._sync_thread.start()

    def _run_initial_sync(self, config: BackupConfig) -> None:
        """백그라운드 스레드에서 초기 동기화를 수행한다."""
        try:
            success, failed = initial_sync(
                config,
                log_cb=self._signals.log.emit,
                error_cb=self._signals.error.emit,
                path_cb=lambda p: self._signals.path_backed_up.emit(str(p)),
            )
            self._signals.sync_finished.emit(success, failed, "")
        except SyncError as err:
            self._signals.sync_finished.emit(0, 0, err.detail())
        except Exception as err:  # 예상 못 한 오류도 UI 로 안전하게 전달
            self._signals.sync_finished.emit(0, 0, f"초기 동기화 중 오류: {err}")

    def _on_sync_finished(self, success: int, failed: int, fatal: str) -> None:
        """초기 동기화 완료(메인 스레드). 치명적 오류가 없으면 감시를 시작한다."""
        if fatal:
            self._append_error(fatal)
            QMessageBox.critical(self, "초기 동기화 실패", fatal)
            self._set_watching_state(False)
            return

        try:
            self._watcher.start(
                self._pending_config,
                log_cb=self._signals.log.emit,
                error_cb=self._signals.error.emit,
                backup_cb=self._signals.backup.emit,
                path_cb=lambda p: self._signals.path_backed_up.emit(str(p)),
            )
        except BackupError as err:
            self._append_error(err.detail())
            QMessageBox.critical(self, "감시 시작 실패", err.message)
            self._set_watching_state(False)
            return

        self._set_watching_state(True)
        self._start_gdrive_timer()

    def _stop_watch(self) -> None:
        self._stop_gdrive_timer()
        try:
            self._watcher.stop()
        except Exception as err:  # 중지 실패는 치명적이지 않다 — 로그만 남긴다.
            self._append_error(f"감시 중지 중 오류: {err}")
        self._append_log("실시간 감시를 중지했습니다.")
        self._set_watching_state(False)

    # ------------------------------------------------------------ 상태 전환
    def _set_status_label(self, status_text: str, highlight: bool) -> None:
        """'상태:' 는 볼드 고정, 상태 텍스트는 highlight=True 면 빨간색, 아니면 기본색."""
        text_color = PALETTE.get(self._theme, PALETTE["dark"])["text"]
        value_color = "red" if highlight else text_color
        self._status_label.setText(
            f'<b style="color:{text_color}">상태:</b> '
            f'<span style="color:{value_color}">{status_text}</span>'
        )

    def _set_busy_state(self) -> None:
        """초기 동기화 중 — 토글 버튼/메뉴를 잠그고 입력을 막는다."""
        self._toggle_btn.setEnabled(False)
        if self._tray_toggle is not None:
            self._tray_toggle.setEnabled(False)
        self._set_status_label("초기 동기화 중...", False)
        self._set_inputs_enabled(False)

    def _set_watching_state(self, running: bool) -> None:
        """감시 중/중지 상태에 맞춰 버튼·메뉴·상태표시·입력잠금을 일괄 갱신한다."""
        text = "감시 중지" if running else "감시 시작"
        self._toggle_btn.setText(text)
        self._toggle_btn.setEnabled(True)
        if self._tray_toggle is not None:
            self._tray_toggle.setText(text)
            self._tray_toggle.setEnabled(True)
        self._set_status_label("감시 중" if running else "중지됨", running)
        self._set_inputs_enabled(not running)
        self._update_runtime_state()
        # 감시가 끝나면 이 세션의 로그 파일도 닫는다.
        if not running:
            self._logger.stop()

    def _set_inputs_enabled(self, enabled: bool) -> None:
        """감시 중에는 경로/제외/지정 목록을 수정하지 못하게 잠근다."""
        self._source_edit.setEnabled(enabled)
        self._backup_edit.setEnabled(enabled)
        self._src_browse_btn.setEnabled(enabled)
        self._dst_browse_btn.setEnabled(enabled)
        self._exclude_list.setEnabled(enabled)
        self._exc_add_btn.setEnabled(enabled)
        self._exc_del_btn.setEnabled(enabled)
        self._include_list.setEnabled(enabled)
        self._inc_add_btn.setEnabled(enabled)
        self._inc_del_btn.setEnabled(enabled)
        self._gdrive_check.setEnabled(enabled)
        self._gdrive_folder_btn.setEnabled(enabled)

    # ------------------------------------------------------------- 트레이
    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        """트레이 아이콘 클릭 시 창을 복원한다."""
        if reason in (
            QSystemTrayIcon.ActivationReason.Trigger,
            QSystemTrayIcon.ActivationReason.DoubleClick,
        ):
            self._restore_window()

    def _restore_window(self) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def _quit_app(self) -> None:
        """트레이 메뉴의 '종료' — 확인 없이 곧바로 프로그램을 끝낸다."""
        self._force_quit = True
        self.close()
        QApplication.quit()

    def _notify(
        self,
        title: str,
        message: str,
        icon: QSystemTrayIcon.MessageIcon,
        msec: int = 4000,
    ) -> None:
        """트레이 풍선 알림을 띄운다. 트레이가 없으면 아무 일도 하지 않는다."""
        if self._tray is not None and self._tray.isVisible():
            self._tray.showMessage(title, message, icon, msec)

    # ----------------------------------------------------------- 로그 출력
    def _timestamp(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _file_timestamp(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _insert_colored_line(self, text: str, color_key: str) -> None:
        """지정한 색으로 한 줄을 로그 뷰에 추가한다."""
        color = LOG_COLORS.get(self._theme, LOG_COLORS["dark"])[color_key]
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        cursor = self._log_view.textCursor()
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not self._log_view.document().isEmpty():
            cursor.insertBlock(cursor.blockFormat(), fmt)
        cursor.insertText(text, fmt)
        self._log_view.setTextCursor(cursor)
        self._log_view.ensureCursorVisible()

    def _append_log(self, message: str) -> None:
        self._insert_colored_line(f"[{self._timestamp()}] {message}", "info")
        self._logger.write(f"[{self._file_timestamp()}] {message}")

    def _append_error(self, message: str) -> None:
        self._insert_colored_line(f"[{self._timestamp()}] [오류] {message}", "error")
        self._logger.write(f"[{self._file_timestamp()}] [오류] {message}")
        # 오류는 중요하므로 창이 보이든 안 보이든 항상 알린다.
        self._notify("백업 오류", message, QSystemTrayIcon.MessageIcon.Warning, 6000)

    def _on_backup_event(self, message: str) -> None:
        """파일 1건 백업 완료 — 로그에 남기고, 창이 숨겨져 있으면 알림을 띄운다."""
        self._append_log(message)

        # 창이 보이면 로그로 충분하므로 알림을 띄우지 않는다.
        if self._tray is None or self.isVisible():
            return

        # 파일마다 알림을 띄우면 시끄러우므로 일정 간격으로 묶어서 알린다.
        now = time.monotonic()
        self._suppressed_backups += 1
        if now - self._last_backup_notify < _NOTIFY_INTERVAL_SECONDS:
            return
        count = self._suppressed_backups
        self._suppressed_backups = 0
        self._last_backup_notify = now
        text = message if count <= 1 else f"{message} 외 {count - 1}건"
        self._notify("백업 완료", text, QSystemTrayIcon.MessageIcon.Information, 3000)

    # --------------------------------------------------- 구글 드라이브 인증
    def _update_gdrive_icon(self, checked: bool) -> None:
        """토글 상태에 맞춰 활성/비활성 아이콘을 교체한다."""
        icon_path = _GDRIVE_ICON_ON if checked else _GDRIVE_ICON_OFF
        if icon_path.exists():
            self._gdrive_check.setIcon(QIcon(str(icon_path)))

    def _set_gdrive_folder_visible(self, visible: bool) -> None:
        """업로드 폴더 선택칸(버튼+라벨)을 보이거나 숨긴다."""
        self._gdrive_folder_btn.setVisible(visible)
        self._gdrive_folder_label.setVisible(visible)

    def _on_gdrive_toggled(self, checked: bool) -> None:
        """토글 ON — 로그인 상태를 확인하고 필요하면 재로그인한 뒤 폴더칸을 연다.

        토큰이 만료/무효(PermissionError)면 허브 로그인 흐름으로 재로그인을 시도한다.
        실제 검증·로그인은 네트워크를 타므로 백그라운드 스레드에서 수행하고,
        결과는 `_on_gdrive_login_finished`(메인 스레드)에서 처리한다.
        """
        if self._gdrive_busy:
            return
        if checked:
            self._gdrive_busy = True
            self._gdrive_login_cancelled = False
            self._gdrive_check.setEnabled(False)
            self._gdrive_status.setText("구글 드라이브 연결 확인 중...")
            self._show_gdrive_login_dialog()
            threading.Thread(target=self._gdrive_login_worker, daemon=True).start()
        else:
            self._update_gdrive_icon(False)
            self._gdrive_status.setText("")
            self._set_gdrive_folder_visible(False)
            self._stop_gdrive_timer()
            self._autosave_config()
            self._update_runtime_state()

    # ----------------------------------------------- 구글 드라이브 로그인 흐름
    def _show_gdrive_login_dialog(self) -> None:
        """로그인 진행 중 다른 조작을 막는 모달 진행 다이얼로그를 띄운다."""
        dialog = QProgressDialog(self)
        dialog.setWindowTitle("구글 드라이브 로그인")
        dialog.setLabelText(
            "구글 드라이브에 연결하는 중입니다.\n"
            "로그인이 필요하면 브라우저 창이 열립니다."
        )
        dialog.setRange(0, 0)  # 인디터미넌트(busy) 진행바
        dialog.setMinimumDuration(0)
        dialog.setCancelButtonText("취소")
        dialog.canceled.connect(self._on_gdrive_login_cancel)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        dialog.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        dialog.show()
        self._gdrive_login_dialog = dialog

    def _on_gdrive_login_cancel(self) -> None:
        """다이얼로그의 '취소'/Esc — 진행 중인 OAuth 흐름을 중단하고 토글을 되돌린다."""
        from .. import gdrive
        self._gdrive_login_cancelled = True
        self._gdrive_login_dialog = None  # canceled 직후 다이얼로그는 자동 close 된다
        self._gdrive_busy = False
        try:
            gdrive.cancel_login()
        except Exception:
            pass
        if self._source_edit.isEnabled():
            self._gdrive_check.setEnabled(True)
        self._gdrive_check.blockSignals(True)
        self._gdrive_check.setChecked(False)
        self._gdrive_check.blockSignals(False)
        self._update_gdrive_icon(False)
        self._set_gdrive_folder_visible(False)
        self._gdrive_status.setText("")
        self._append_log("구글 드라이브 로그인을 취소했습니다.")

    def _close_gdrive_login_dialog(self) -> None:
        """진행 다이얼로그를 프로그램적으로 닫는다.

        QProgressDialog.close() 는 canceled 시그널을 발생시키므로, 먼저
        취소 핸들러를 끊어 '사용자 취소'로 오인되지 않게 한다. (이 오인이
        로그인 성공 후 토글을 몰래 해제해 OFF 클릭이 ON 으로 동작하던 원인.)
        """
        if self._gdrive_login_dialog is not None:
            dlg = self._gdrive_login_dialog
            self._gdrive_login_dialog = None
            try:
                dlg.canceled.disconnect(self._on_gdrive_login_cancel)
            except (RuntimeError, TypeError):
                pass
            dlg.close()
            dlg.deleteLater()

    def _gdrive_login_worker(self) -> None:
        """백그라운드: 기존 토큰을 검증하고, 만료/무효면 허브 로그인으로 재로그인한다."""
        from .. import gdrive
        try:
            try:
                email = gdrive.get_email()  # 기존 토큰 검증 (브라우저 없음)
            except PermissionError:
                email = gdrive.login()      # 토큰 만료/무효 → 허브 재로그인 (브라우저)
            self._signals.gdrive_login_finished.emit(True, email)
        except Exception as err:
            self._signals.gdrive_login_finished.emit(False, str(err))

    def _on_gdrive_login_finished(self, success: bool, message: str) -> None:
        """로그인 결과(메인 스레드). 성공하면 폴더칸을 열고, 실패하면 토글을 되돌린다."""
        # 사용자가 이미 취소했으면 늦게 끝난 결과는 무시한다.
        if self._gdrive_login_cancelled:
            self._gdrive_login_cancelled = False
            return
        self._gdrive_busy = False
        self._close_gdrive_login_dialog()
        if self._source_edit.isEnabled():
            self._gdrive_check.setEnabled(True)

        if success:
            # 토글 내부 상태를 결과와 명시적으로 일치시킨다(시각/내부 desync 방지).
            self._gdrive_check.blockSignals(True)
            self._gdrive_check.setChecked(True)
            self._gdrive_check.blockSignals(False)
            self._update_gdrive_icon(True)
            self._gdrive_status.setText(
                f"로그인됨: {message}" if message else "구글 드라이브 연동 활성화됨"
            )
            self._set_gdrive_folder_visible(True)
            self._append_log(
                f"구글 드라이브 연동 활성화: {message}" if message
                else "구글 드라이브 연동을 활성화했습니다."
            )
            self._autosave_config()
            self._update_runtime_state()
            # 감시 중에 켠 경우라면 업로드 타이머도 시작한다.
            if not self._source_edit.isEnabled():
                self._start_gdrive_timer()
        else:
            self._gdrive_check.blockSignals(True)
            self._gdrive_check.setChecked(False)
            self._gdrive_check.blockSignals(False)
            self._update_gdrive_icon(False)
            self._set_gdrive_folder_visible(False)
            self._gdrive_status.setText("")
            self._append_error(f"구글 드라이브 로그인 실패: {message}")

    def _update_gdrive_folder_label(self) -> None:
        """선택된 업로드 폴더 경로를 라벨에 표시한다(미지정이면 루트)."""
        path = self._gdrive_folder_path or "내 드라이브"
        self._gdrive_folder_label.setText(f"업로드 위치:\n{path}")

    def _browse_gdrive_folder(self) -> None:
        """Drive 폴더 탐색 대화상자를 띄워 업로드 대상 폴더를 고른다."""
        from .. import gdrive
        if not gdrive.is_logged_in():
            QMessageBox.information(
                self, "구글 드라이브",
                "허브에서 먼저 구글 계정으로 로그인해 주세요.",
            )
            return
        dlg = _GDriveFolderDialog(self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self._gdrive_folder_id, self._gdrive_folder_path = dlg.selected_folder()
            self._update_gdrive_folder_label()
            self._append_log(f"구글 드라이브 업로드 폴더를 '{self._gdrive_folder_path}'(으)로 지정했습니다.")
            self._autosave_config()

    # --------------------------------------------------- 구글 드라이브 업로드
    def _start_gdrive_timer(self) -> None:
        """구글 드라이브 토글이 켜져 있으면 1시간 주기 타이머를 켜고 즉시 1회 업로드를 트리거한다."""
        if not self._gdrive_check.isChecked():
            return
        if self._gdrive_timer is None:
            self._gdrive_timer = QTimer(self)
            self._gdrive_timer.timeout.connect(self._run_gdrive_upload)
        self._gdrive_timer.start(_GDRIVE_INTERVAL_MS)
        self._append_log("구글 드라이브 자동 업로드를 시작합니다 (1시간 주기).")
        # 감시 시작 직후 1회 업로드
        self._run_gdrive_upload()

    def _stop_gdrive_timer(self) -> None:
        if self._gdrive_timer is not None:
            self._gdrive_timer.stop()

    def _on_path_backed_up(self, abs_path: str) -> None:
        """백업이 일어난 파일을 다음 Drive 업로드 사이클의 대상으로 추가한다."""
        if self._gdrive_check.isChecked():
            self._gdrive_pending.add(abs_path)

    def _run_gdrive_upload(self) -> None:
        """대기열에 쌓인 변경 파일만 Drive로 업로드한다.

        이전 업로드가 끝나지 않았으면 이번 주기는 건너뛰고, 큐에 쌓인 항목은 그대로 둔다.
        """
        if self._gdrive_uploading:
            self._append_log("이전 구글 드라이브 업로드가 진행 중이라 이번 주기는 건너뜁니다.")
            return
        if not self._gdrive_pending:
            self._append_log("구글 드라이브에 올릴 변경 파일이 없어 이번 주기는 건너뜁니다.")
            return
        backup_dir = self._pending_config.backup_dir
        if not backup_dir:
            return

        # 스냅샷 + 비우기. 업로드 도중 발생하는 새 이벤트는 새 큐에 쌓인다.
        snapshot = self._gdrive_pending
        self._gdrive_pending = set()

        # 백업 디렉토리 기준 상대경로로 변환 (Drive 폴더 구조와 매칭)
        backup_root = Path(backup_dir).resolve()
        rel_paths: list[str] = []
        for abs_str in snapshot:
            try:
                rel = Path(abs_str).resolve().relative_to(backup_root).as_posix()
            except ValueError:
                continue  # 백업 디렉토리 밖이면 무시
            rel_paths.append(rel)

        if not rel_paths:
            return

        self._gdrive_uploading = True
        threading.Thread(
            target=self._gdrive_upload_worker,
            args=(backup_root, rel_paths, self._gdrive_folder_id),
            daemon=True,
        ).start()

    def _gdrive_upload_worker(
        self, backup_root: Path, rel_paths: list[str], folder_id: str
    ) -> None:
        """백그라운드에서 Drive 업로드를 수행한다. UI 갱신은 signals 로 전달한다."""
        try:
            self._signals.log.emit(
                f"구글 드라이브 업로드 시작: 변경 파일 {len(rel_paths)}건"
            )
            from .. import gdrive
            failed = gdrive.upload_files(
                backup_root,
                rel_paths,
                parent_folder_id=folder_id or gdrive.ROOT_FOLDER_ID,
                log_cb=self._signals.log.emit,
                error_cb=self._signals.error.emit,
            )
            if failed:
                # 실패한 파일은 다음 사이클에서 재시도하도록 큐에 되돌린다.
                for rel in failed:
                    self._signals.path_backed_up.emit(str(backup_root / rel))
                self._signals.error.emit(
                    f"구글 드라이브 업로드 일부 실패: {len(failed)}건 (다음 주기에 재시도)"
                )
            self._signals.log.emit(
                f"구글 드라이브 업로드 완료: 성공 {len(rel_paths) - len(failed)}건"
            )
        except Exception as err:
            # 전체 실패 시 큐에 되돌려 다음 주기에 다시 시도
            for rel in rel_paths:
                self._signals.path_backed_up.emit(str(backup_root / rel))
            self._signals.error.emit(f"구글 드라이브 업로드 실패: {err}")
        finally:
            self._gdrive_uploading = False

    # ----------------------------------------------------------- 종료 처리
    def _cleanup(self) -> None:
        """감시 스레드와 트레이 아이콘을 정리한다."""
        self._stop_gdrive_timer()
        try:
            self._watcher.stop()
        except Exception:
            pass
        self._logger.stop()
        runtime_state.clear()
        if self._tray is not None:
            self._tray.hide()

    def closeEvent(self, event) -> None:
        """창 닫기 시 트레이로 보낼지 종료할지 묻는다.

        트레이를 쓸 수 없거나 트레이 메뉴의 '종료'로 들어온 경우에는 곧바로 종료한다.
        """
        if self._force_quit or self._tray is None:
            self._cleanup()
            event.accept()
            return

        box = QMessageBox(self)
        box.setWindowTitle("종료 확인")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText("프로그램을 어떻게 할까요?")
        box.setInformativeText(
            "트레이로 보내면 백그라운드에서 계속 실행됩니다."
        )
        tray_btn = box.addButton("트레이로", QMessageBox.ButtonRole.AcceptRole)
        quit_btn = box.addButton("종료", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(tray_btn)
        box.exec()
        clicked = box.clickedButton()

        if clicked is tray_btn:
            event.ignore()
            self.hide()
            self._notify(
                "트레이로 보내기",
                "트레이에서 계속 실행합니다.",
                QSystemTrayIcon.MessageIcon.Information,
                3000,
            )
        elif clicked is quit_btn:
            self._force_quit = True
            self._cleanup()
            event.accept()
            QApplication.quit()
        else:  # 취소
            event.ignore()

    # WM_NCHITTEST 를 가로채 OS 가 테두리 리사이즈를 처리하도록 한다.
    _RESIZE_MARGIN = 6

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG":
            msg = ctypes.wintypes.MSG.from_address(int(message))
            if msg.message == 0x0084:  # WM_NCHITTEST
                mx = ctypes.c_short(msg.lParam & 0xFFFF).value
                my = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                g = self.frameGeometry()
                m = self._RESIZE_MARGIN
                left   = mx - g.left()   < m
                right  = g.right()  - mx < m
                top    = my - g.top()    < m
                bottom = g.bottom() - my < m
                if top    and left:  return True, 13  # HTTOPLEFT
                if top    and right: return True, 14  # HTTOPRIGHT
                if bottom and left:  return True, 16  # HTBOTTOMLEFT
                if bottom and right: return True, 17  # HTBOTTOMRIGHT
                if top:              return True, 12  # HTTOP
                if bottom:           return True, 15  # HTBOTTOM
                if left:             return True, 10  # HTLEFT
                if right:            return True, 11  # HTRIGHT
        return super().nativeEvent(event_type, message)
