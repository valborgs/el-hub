"""백업 설정의 데이터 모델과 JSON 영속화, 검증 로직."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from .errors import ConfigError, ValidationError

# 설정 파일 경로: 프로젝트 폴더(backup-tool/) 내 config.json
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.json"


@dataclass
class BackupConfig:
    """백업 대상/저장 경로와 제외/지정 패턴을 담는 설정.

    excludes 는 대상 디렉토리 기준 상대경로에 대한 제외 glob 패턴 목록이다.
    includes 는 백업할 파일/디렉토리를 지정하는 glob 패턴 목록이다.
      - includes 가 비어 있으면 전체 파일을 대상으로 한다(기존 동작).
      - includes 가 있으면 패턴에 매칭되는 파일/디렉토리만 백업한다.
    예: "*.tmp", "node_modules", "temp/cache"
    """

    source_dir: str = ""
    backup_dir: str = ""
    excludes: list[str] = field(default_factory=list)
    includes: list[str] = field(default_factory=list)
    theme: str = "dark"
    gdrive_enabled: bool = False

    def to_dict(self) -> dict:
        return {
            "source_dir": self.source_dir,
            "backup_dir": self.backup_dir,
            "excludes": list(self.excludes),
            "includes": list(self.includes),
            "theme": self.theme,
            "gdrive_enabled": self.gdrive_enabled,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BackupConfig":
        """dict 에서 설정을 복원한다. 형식이 어긋나면 ConfigError 를 던진다."""
        if not isinstance(data, dict):
            raise ConfigError("설정 파일의 형식이 올바르지 않습니다. (최상위가 객체가 아님)")
        try:
            source_dir = data.get("source_dir", "")
            backup_dir = data.get("backup_dir", "")
            excludes = data.get("excludes", [])
            includes = data.get("includes", [])
            theme = data.get("theme", "dark")
            gdrive_enabled = bool(data.get("gdrive_enabled", False))
            if not isinstance(source_dir, str) or not isinstance(backup_dir, str):
                raise ConfigError("설정 파일의 경로 항목이 문자열이 아닙니다.")
            if not isinstance(excludes, list) or not all(isinstance(x, str) for x in excludes):
                raise ConfigError("설정 파일의 제외 목록(excludes) 형식이 올바르지 않습니다.")
            if not isinstance(includes, list) or not all(isinstance(x, str) for x in includes):
                raise ConfigError("설정 파일의 지정 목록(includes) 형식이 올바르지 않습니다.")
            if theme not in ("dark", "light"):
                theme = "dark"
        except ConfigError:
            raise
        except Exception as err:  # 예상 못 한 구조 오류 방어
            raise ConfigError("설정 파일의 내용을 해석할 수 없습니다.") from err
        return cls(
            source_dir=source_dir,
            backup_dir=backup_dir,
            excludes=excludes,
            includes=includes,
            theme=theme,
            gdrive_enabled=gdrive_enabled,
        )


def load(path: Path = CONFIG_PATH) -> BackupConfig:
    """설정 파일을 읽어 BackupConfig 로 반환한다.

    - 파일이 없으면 빈 기본 설정을 반환한다(오류 아님).
    - JSON 파싱 실패나 형식 오류는 ConfigError 로 변환한다.
    """
    if not path.exists():
        return BackupConfig()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as err:
        raise ConfigError(f"설정 파일을 읽을 수 없습니다: {path}") from err
    try:
        data = json.loads(text)
    except json.JSONDecodeError as err:
        raise ConfigError(
            f"설정 파일이 손상되어 읽을 수 없습니다: {path}\n"
            "기본 설정으로 시작합니다."
        ) from err
    return BackupConfig.from_dict(data)


def save(config: BackupConfig, path: Path = CONFIG_PATH) -> None:
    """설정을 JSON 파일로 저장한다. 실패 시 ConfigError 를 던진다."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = json.dumps(config.to_dict(), ensure_ascii=False, indent=2)
        path.write_text(text, encoding="utf-8")
    except OSError as err:
        raise ConfigError(f"설정 파일을 저장할 수 없습니다: {path}") from err


def _is_subpath(child: Path, parent: Path) -> bool:
    """child 가 parent 와 같거나 그 하위 경로인지 검사한다."""
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def validate(config: BackupConfig) -> None:
    """설정값을 검증한다. 문제가 있으면 ValidationError 를 던진다.

    검사 항목:
    - 대상/백업 경로가 비어 있지 않은지
    - 대상 경로가 실제로 존재하는 디렉토리인지
    - 백업 경로를 만들 수 있는지(이미 있으면 디렉토리인지)
    - 두 경로가 같거나 서로 포함 관계가 아닌지 (무한 복사 방지)
    """
    if not config.source_dir.strip():
        raise ValidationError("백업 대상 디렉토리를 지정해 주세요.")
    if not config.backup_dir.strip():
        raise ValidationError("백업을 저장할 디렉토리를 지정해 주세요.")

    try:
        source = Path(config.source_dir).resolve()
        backup = Path(config.backup_dir).resolve()
    except OSError as err:
        raise ValidationError("경로 형식이 올바르지 않습니다.") from err

    if not source.exists():
        raise ValidationError(f"백업 대상 디렉토리가 존재하지 않습니다:\n{source}")
    if not source.is_dir():
        raise ValidationError(f"백업 대상이 디렉토리가 아닙니다:\n{source}")

    if backup.exists() and not backup.is_dir():
        raise ValidationError(f"백업 경로에 같은 이름의 파일이 있습니다:\n{backup}")
    if not backup.exists():
        # 실제로 만들지는 않고, 만들 수 있는지(상위 경로 쓰기 권한)만 확인
        try:
            backup.mkdir(parents=True, exist_ok=True)
        except OSError as err:
            raise ValidationError(
                f"백업 디렉토리를 만들 수 없습니다:\n{backup}"
            ) from err

    if source == backup:
        raise ValidationError("대상 디렉토리와 백업 디렉토리가 동일합니다.")
    if _is_subpath(backup, source):
        raise ValidationError(
            "백업 디렉토리가 대상 디렉토리 안에 있습니다.\n"
            "백업이 끝없이 반복되므로 다른 위치를 지정해 주세요."
        )
    if _is_subpath(source, backup):
        raise ValidationError(
            "대상 디렉토리가 백업 디렉토리 안에 있습니다.\n다른 위치를 지정해 주세요."
        )
