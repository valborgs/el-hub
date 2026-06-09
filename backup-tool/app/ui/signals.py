"""백그라운드 스레드와 Qt(메인) 스레드를 잇는 신호 브리지.

watchdog 의 Observer 와 초기 동기화 작업은 별도 스레드에서 실행된다. 그 스레드에서
위젯을 직접 건드리면 안 되므로, QObject 의 Signal 을 통해 메인 스레드로 전달한다.
서로 다른 스레드에서 emit 하면 Qt 가 자동으로 큐 연결(QueuedConnection)을 쓴다.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class WorkerSignals(QObject):
    """백그라운드 스레드 -> UI 로 메시지/결과를 전달하는 신호 모음."""

    log = Signal(str)
    error = Signal(str)
    # 파일 1건 백업 완료. 메시지 예: "수정: 문서/보고서.docx"
    backup = Signal(str)
    # 백업된 파일의 절대경로(백업 디렉토리 아래). Drive 업로드 대기열에 사용.
    path_backed_up = Signal(str)
    # 초기 동기화 종료: (성공 건수, 실패 건수, 치명적 오류 메시지 또는 빈 문자열)
    sync_finished = Signal(int, int, str)
