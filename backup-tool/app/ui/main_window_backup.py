"""PySide6 메인 윈도우: 경로/제외 목록 입력, 감시 시작·중지, 로그 출력, 트레이 아이콘."""

from __future__ import annotations

import threading
import time
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
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

from .. import config as config_module
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


class MainWindow(QWidget):
    """백업 프로그램의 메인 화면."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("실시간 폴더 백업")
        self.setStyleSheet(
            """
            background-color: #E1E1E1;

            QGroupBox {
                border: 1px solid #A0A0A0;
                border-radius: 4px;
                margin-top: 12px;
                padding: 10px 8px 8px 8px;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                subcontrol-position: top left;
                left: 8px;
                padding: 0 4px;
            }
            """
        )
        self.resize(400, 500)

        self._watcher = WatcherService()
        self._logger = SessionLogger()
        self._signals = WorkerSignals()
        self._signals.log.connect(self._append_log)
        self._signals.error.connect(self._append_error)
        self._signals.backup.connect(self._on_backup_event)
        self._signals.sync_finished.connect(self._on_sync_finished)
        self._signals.gdrive_login_finished.connect(self._on_gdrive_login_finished)
        self._signals.gdrive_logout_finished.connect(self._on_gdrive_logout_finished)
        self._signals.path_backed_up.connect(self._on_path_backed_up)
        self._sync_thread: threading.Thread | None = None

        # 트레이 관련 상태
        self._tray: QSystemTrayIcon | None = None
        self._tray_toggle = None
        self._force_quit = False
        self._last_backup_notify = 0.0
        self._suppressed_backups = 0

        # 구글 드라이브 자동 업로드/인증 상태
        self._gdrive_timer: QTimer | None = None
        self._gdrive_uploading = False
        self._gdrive_busy = False  # 로그인/로그아웃 진행 중 가드
        self._gdrive_login_dialog: QProgressDialog | None = None
        self._gdrive_login_cancelled = False  # 사용자가 로그인을 취소했는지
        # 다음 업로드 사이클에서 Drive 로 올릴 백업 파일들의 절대경로
        self._gdrive_pending: set[str] = set()

        self._build_ui()
        self._build_tray()
        self._load_initial_config()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ---- 0) 섹션 표시 토글 (상단) ----
        section_row = QHBoxLayout()
        self._toggle_settings_btn = QPushButton("설정")
        self._toggle_settings_btn.setCheckable(True)
        self._toggle_settings_btn.setChecked(True)
        self._toggle_settings_btn.toggled.connect(self._on_settings_visibility_toggled)
        self._toggle_excludes_btn = QPushButton("제외")
        self._toggle_excludes_btn.setCheckable(True)
        self._toggle_excludes_btn.setChecked(True)
        self._toggle_excludes_btn.toggled.connect(
            lambda checked: self._exc_group.setVisible(checked)
        )
        section_row.addWidget(self._toggle_settings_btn)
        section_row.addWidget(self._toggle_excludes_btn)
        section_row.addStretch()
        layout.addLayout(section_row)

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
        self._dst_browse_btn.setFixedWidth(30)
        self._dst_browse_btn.clicked.connect(self._browse_backup)
        dst_row.addWidget(self._backup_edit)
        dst_row.addWidget(self._dst_browse_btn)
        dir_layout.addLayout(dst_row)
        dir_layout.addStretch()

        # 오른쪽 그룹: 구글 드라이브 연동 (아이콘 버튼 + 상태)
        self._gdrive_group = QGroupBox("구글 드라이브")
        gdrive_layout = QVBoxLayout(self._gdrive_group)
        self._gdrive_check = QPushButton()
        self._gdrive_check.setCheckable(True)
        self._gdrive_check.setIconSize(QSize(48, 48))
        self._gdrive_check.setFixedSize(64, 64)
        self._gdrive_check.setToolTip("구글 드라이브 연동 (1시간 주기 자동 업로드)")
        self._gdrive_check.setStyleSheet(
            """
            QPushButton {
                border: 1px solid #C0C0C0;
                border-radius: 6px;
                background: #FFFFFF;
            }
            QPushButton:checked {
                border: 1px solid #4285F4;
                background: #E8F0FE;
            }
            QPushButton:disabled {
                background: #F0F0F0;
            }
            """
        )
        self._gdrive_check.toggled.connect(self._on_gdrive_toggled)
        self._gdrive_check.toggled.connect(self._update_gdrive_icon)
        self._update_gdrive_icon(False)  # 초기 비활성 아이콘

        self._gdrive_status = QLabel("")
        self._gdrive_status.setStyleSheet("color: #404040;")
        self._gdrive_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._gdrive_status.setWordWrap(True)
        # 텍스트 길이와 무관하게 오른쪽 컬럼 폭을 일정하게 유지한다.
        self._gdrive_status.setFixedWidth(140)

        gdrive_layout.addWidget(self._gdrive_check, alignment=Qt.AlignmentFlag.AlignCenter)
        gdrive_layout.addWidget(self._gdrive_status)
        gdrive_layout.addStretch()

        settings_row.addWidget(self._dir_group, stretch=1)
        settings_row.addWidget(self._gdrive_group)
        layout.addLayout(settings_row)

        # ---- 2) 제외 목록 영역 ----
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

        # ---- 3) 감시 제어 영역 ----
        ctrl_label_layout = QHBoxLayout()
        self._status_label = QLabel("상태: 중지됨")
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
        self._log_view.setReadOnly(True)
        log_layout.addWidget(self._log_view)
        layout.addWidget(log_group, stretch=1)

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

        # 이전에 구글 드라이브에 로그인된 상태였다면 토글을 켜고, 이메일은 백그라운드에서 확인한다.
        from .. import gdrive
        if gdrive.is_logged_in():
            self._gdrive_check.blockSignals(True)
            self._gdrive_check.setChecked(True)
            self._gdrive_check.blockSignals(False)
            self._update_gdrive_icon(True)
            self._gdrive_status.setText("로그인 확인 중...")
            threading.Thread(target=self._gdrive_fetch_email_worker, daemon=True).start()

    def _collect_config(self) -> BackupConfig:
        """현재 위젯 상태로 BackupConfig 를 만든다."""
        excludes = [
            self._exclude_list.item(i).text()
            for i in range(self._exclude_list.count())
        ]
        return BackupConfig(
            source_dir=self._source_edit.text().strip(),
            backup_dir=self._backup_edit.text().strip(),
            excludes=excludes,
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
    def _set_busy_state(self) -> None:
        """초기 동기화 중 — 토글 버튼/메뉴를 잠그고 입력을 막는다."""
        self._toggle_btn.setEnabled(False)
        if self._tray_toggle is not None:
            self._tray_toggle.setEnabled(False)
        self._status_label.setText("상태: 초기 동기화 중...")
        self._set_inputs_enabled(False)

    def _set_watching_state(self, running: bool) -> None:
        """감시 중/중지 상태에 맞춰 버튼·메뉴·상태표시·입력잠금을 일괄 갱신한다."""
        text = "감시 중지" if running else "감시 시작"
        self._toggle_btn.setText(text)
        self._toggle_btn.setEnabled(True)
        if self._tray_toggle is not None:
            self._tray_toggle.setText(text)
            self._tray_toggle.setEnabled(True)
        self._status_label.setText("상태: 감시 중" if running else "상태: 중지됨")
        self._set_inputs_enabled(not running)
        # 감시가 끝나면 이 세션의 로그 파일도 닫는다.
        if not running:
            self._logger.stop()

    def _set_inputs_enabled(self, enabled: bool) -> None:
        """감시 중에는 경로/제외 목록을 수정하지 못하게 잠근다."""
        self._source_edit.setEnabled(enabled)
        self._backup_edit.setEnabled(enabled)
        self._src_browse_btn.setEnabled(enabled)
        self._dst_browse_btn.setEnabled(enabled)
        self._exclude_list.setEnabled(enabled)
        self._exc_add_btn.setEnabled(enabled)
        self._exc_del_btn.setEnabled(enabled)
        self._gdrive_check.setEnabled(enabled)

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

    def _append_log(self, message: str) -> None:
        self._log_view.appendHtml(
            f'<span style="color:#202020">[{self._timestamp()}] {message}</span>'
        )
        self._logger.write(f"[{self._file_timestamp()}] {message}")

    def _append_error(self, message: str) -> None:
        self._log_view.appendHtml(
            f'<span style="color:#c0392b">[{self._timestamp()}] [오류] {message}</span>'
        )
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

    def _on_gdrive_toggled(self, checked: bool) -> None:
        """체크박스 토글 — 켜면 로그인, 끄면 로그아웃을 백그라운드에서 수행한다."""
        if self._gdrive_busy:
            return
        self._gdrive_busy = True
        self._gdrive_check.setEnabled(False)
        if checked:
            self._gdrive_login_cancelled = False
            self._gdrive_status.setText("로그인 중... \n(브라우저를 확인해 주세요)")
            self._show_gdrive_login_dialog()
            threading.Thread(target=self._gdrive_login_worker, daemon=True).start()
        else:
            self._gdrive_status.setText("로그아웃 중...")
            threading.Thread(target=self._gdrive_logout_worker, daemon=True).start()

    def _show_gdrive_login_dialog(self) -> None:
        """로그인 진행 중 다른 UI 조작을 막는 모달 진행 다이얼로그를 띄운다."""
        dialog = QProgressDialog(self)
        dialog.setWindowTitle("구글 드라이브 로그인")
        dialog.setLabelText(
            "구글 드라이브에 로그인 중입니다.\n"
            "브라우저 창에서 로그인을 완료해 주세요."
        )
        dialog.setRange(0, 0)  # 인디터미넌트(busy) 진행바
        dialog.setMinimumDuration(0)
        dialog.setCancelButtonText("취소")
        dialog.canceled.connect(self._on_gdrive_login_cancel)
        dialog.setWindowModality(Qt.WindowModality.ApplicationModal)
        # 제목줄만 두고 닫기/도움말/최소화 버튼은 제거 (사용자는 '취소' 버튼으로만 빠져나간다)
        dialog.setWindowFlags(
            Qt.WindowType.Dialog
            | Qt.WindowType.CustomizeWindowHint
            | Qt.WindowType.WindowTitleHint
        )
        dialog.show()
        self._gdrive_login_dialog = dialog

    def _on_gdrive_login_cancel(self) -> None:
        """다이얼로그의 '취소' 또는 Esc 로 사용자가 로그인을 포기했을 때.

        백그라운드의 OAuth 흐름은 즉시 멈출 수 없으므로, 결과를 무시하도록 플래그만 세우고
        UI 를 즉시 원상복구한다. 브라우저 탭은 사용자가 직접 닫는 것을 권장한다.
        """
        self._gdrive_login_cancelled = True
        self._gdrive_login_dialog = None  # canceled 시그널 직후 dialog 는 자동 close 된다
        self._gdrive_busy = False
        if self._source_edit.isEnabled():
            self._gdrive_check.setEnabled(True)
        # 토글을 다시 끄고 아이콘을 비활성으로
        self._gdrive_check.blockSignals(True)
        self._gdrive_check.setChecked(False)
        self._gdrive_check.blockSignals(False)
        self._update_gdrive_icon(False)
        self._gdrive_status.setText("")
        self._append_log("구글 드라이브 로그인을 취소했습니다.")

    def _close_gdrive_login_dialog(self) -> None:
        """진행 다이얼로그가 떠 있으면 닫는다."""
        if self._gdrive_login_dialog is not None:
            self._gdrive_login_dialog.close()
            self._gdrive_login_dialog = None

    def _gdrive_login_worker(self) -> None:
        try:
            from .. import gdrive
            email = gdrive.login()
            self._signals.gdrive_login_finished.emit(True, email)
        except Exception as err:
            self._signals.gdrive_login_finished.emit(False, str(err))

    def _gdrive_logout_worker(self) -> None:
        try:
            from .. import gdrive
            gdrive.logout()
            self._signals.gdrive_logout_finished.emit(True, "")
        except Exception as err:
            self._signals.gdrive_logout_finished.emit(False, str(err))

    def _gdrive_fetch_email_worker(self) -> None:
        """앱 시작 시 캐시된 토큰으로 이메일을 가져와 상태 라벨에 채운다."""
        try:
            from .. import gdrive
            email = gdrive.get_current_email()
            self._signals.gdrive_login_finished.emit(True, email)
        except Exception as err:
            self._signals.gdrive_login_finished.emit(False, str(err))

    def _on_gdrive_login_finished(self, success: bool, message: str) -> None:
        # 이미 사용자가 취소했다면 워커가 늦게 끝나도 결과를 무시한다.
        if self._gdrive_login_cancelled:
            self._gdrive_login_cancelled = False
            return
        self._gdrive_busy = False
        self._close_gdrive_login_dialog()
        # 감시/초기 동기화 중에는 다른 입력과 함께 잠겨 있어야 하므로 그 상태를 따라간다.
        if self._source_edit.isEnabled():
            self._gdrive_check.setEnabled(True)
        if success:
            self._gdrive_status.setText(f"로그인됨: {message}")
            self._append_log(f"구글 드라이브 로그인 성공: {message}")
        else:
            self._gdrive_status.setText("")
            self._append_error(f"구글 드라이브 로그인 실패: {message}")
            # 실패 시 토글을 다시 끈다 (시그널은 막아서 재진입 방지)
            self._gdrive_check.blockSignals(True)
            self._gdrive_check.setChecked(False)
            self._gdrive_check.blockSignals(False)
            self._update_gdrive_icon(False)

    def _on_gdrive_logout_finished(self, success: bool, message: str) -> None:
        self._gdrive_busy = False
        if not self._watcher.is_running:
            self._gdrive_check.setEnabled(True)
        self._gdrive_status.setText("")
        if success:
            self._append_log("구글 드라이브에서 로그아웃했습니다.")
        else:
            self._append_error(f"구글 드라이브 로그아웃 중 오류: {message}")

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
            args=(backup_root, rel_paths),
            daemon=True,
        ).start()

    def _gdrive_upload_worker(self, backup_root: Path, rel_paths: list[str]) -> None:
        """백그라운드에서 Drive 업로드를 수행한다. UI 갱신은 signals 로 전달한다."""
        try:
            self._signals.log.emit(
                f"구글 드라이브 업로드 시작: 변경 파일 {len(rel_paths)}건"
            )
            from .. import gdrive
            failed = gdrive.upload_files(
                backup_root,
                rel_paths,
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
            "트레이로 보내면 백그라운드에서 백업 감시를 계속합니다."
        )
        tray_btn = box.addButton("트레이로 보내기", QMessageBox.ButtonRole.AcceptRole)
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
                "트레이에서 백업 감시를 계속합니다.",
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
