"""앱 전용 예외 클래스.

모든 예외는 사용자에게 그대로 보여줄 수 있는 한글 메시지를 담는다.
원인이 되는 하위 예외는 `raise ... from err` 로 연결해 `__cause__` 에 보존한다.
"""

from __future__ import annotations


class BackupError(Exception):
    """백업 프로그램에서 발생하는 모든 예외의 베이스 클래스.

    `message` 는 사용자에게 보여줄 한글 메시지다.
    """

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message

    def detail(self) -> str:
        """로그용 상세 메시지. 원인 예외가 있으면 함께 표시한다."""
        if self.__cause__ is not None:
            cause = self.__cause__
            return f"{self.message} (원인: {type(cause).__name__}: {cause})"
        return self.message


class ConfigError(BackupError):
    """설정 파일을 읽거나 쓰는 중 발생한 오류."""


class ValidationError(BackupError):
    """사용자가 입력한 설정값이 올바르지 않을 때 발생하는 오류."""


class SyncError(BackupError):
    """파일 복사(백업) 중 발생한 오류."""

    def __init__(self, message: str, path: str | None = None):
        super().__init__(message)
        self.path = path
