"""실시간 폴더 백업 프로그램 — 엔트리포인트.

사용법:
    python main.py
"""

from __future__ import annotations

import sys
import traceback

# 토스트 알림 헤더 등에서 표시되는 앱 식별자/이름.
APP_ID = "DeliveryBackup.App"
APP_DISPLAY_NAME = "실시간 폴더 백업"


def _register_windows_app_id() -> None:
    """Windows 토스트 알림 헤더에 표시되는 앱 이름을 설정한다.

    기본 상태에서는 Windows 가 프로세스 이름(python.exe -> "Python")을 표시한다.
    1) HKCU\\Software\\Classes\\AppUserModelId\\<APP_ID> 에 DisplayName 을 등록하고
    2) 현재 프로세스의 AppUserModelID 를 그 ID 로 설정하면
    토스트 알림에 등록한 DisplayName 이 표시된다. (HKCU 키라 관리자 권한 불필요)

    Windows 가 아니거나 설정에 실패해도 프로그램은 정상 동작한다.
    """
    if sys.platform != "win32":
        return
    try:
        import winreg

        key_path = "Software\\Classes\\AppUserModelId\\" + APP_ID
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, APP_DISPLAY_NAME)
    except OSError:
        pass  # 레지스트리 쓰기 실패는 치명적이지 않다 — 헤더가 "Python" 으로 표시될 뿐
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except (AttributeError, OSError):
        pass


def _install_excepthook(app) -> None:
    """예상치 못한 예외를 잡아 메시지 상자로 보여준 뒤 콘솔에도 기록한다."""
    from PySide6.QtWidgets import QMessageBox

    def hook(exc_type, exc_value, exc_tb):
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        print(detail, file=sys.stderr)
        try:
            QMessageBox.critical(
                None,
                "예상치 못한 오류",
                f"예상치 못한 오류가 발생했습니다:\n\n{exc_value}\n\n"
                "프로그램이 불안정할 수 있으니 저장 후 재시작을 권장합니다.",
            )
        except Exception:
            # 메시지 상자조차 띄울 수 없는 상황 — 콘솔 출력으로 충분히 알렸다.
            pass

    sys.excepthook = hook


def main() -> int:
    # QApplication 생성 전에 호출해야 알림 시스템이 새 식별자를 인식한다.
    _register_windows_app_id()

    try:
        from PySide6.QtWidgets import QApplication
    except ImportError:
        print(
            "PySide6 가 설치되어 있지 않습니다.\n"
            "다음 명령으로 의존성을 설치하세요:\n"
            "    uv sync",
            file=sys.stderr,
        )
        return 1

    try:
        from app.ui.main_window import MainWindow
    except ImportError as err:
        print(f"프로그램 모듈을 불러올 수 없습니다: {err}", file=sys.stderr)
        return 1

    app = QApplication(sys.argv)
    app.setApplicationName(APP_DISPLAY_NAME)
    app.setApplicationDisplayName(APP_DISPLAY_NAME)

    from app.ui.style import apply_theme
    apply_theme(app, "dark")

    # 앱 전역 아이콘 — 메인 창, 다이얼로그, 작업표시줄에서 사용된다.
    try:
        from PySide6.QtGui import QIcon
        from app import ICON_PATH

        if ICON_PATH.exists():
            app.setWindowIcon(QIcon(str(ICON_PATH)))
    except Exception:
        # 아이콘 로드 실패는 치명적이지 않다 — 기본 아이콘으로 폴백된다.
        pass

    _install_excepthook(app)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
