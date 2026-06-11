# -*- coding: utf-8 -*-
"""허브에서 실행하는 앱들의 '실행 상태'(pid, 프로세스 생성시각)를 파일로 공유하는 공용 모듈.

허브와 각 앱이 함께 사용한다:
- 앱  : 시작 시 ``write(path)``, 종료 시 ``clear(path)`` 를 호출한다.
- 허브: ``read_live(path)`` 로 (허브가 직접 띄우지 않은) 외부에서 켜진 인스턴스까지
        실행 여부를 판별한다.

pid 는 재사용될 수 있으므로, pid 단독이 아니라 (pid + 프로세스 생성시각) 쌍으로
'동일 프로세스'인지 확인한다. 이렇게 하면 앱이 비정상 종료한 뒤 같은 pid 를 받은
다른 프로세스를 살아있는 앱으로 오인하지 않는다.

hub_auth 와 마찬가지로 각 앱은 허브 루트(auto/) 아래에서 실행되므로, 앱들은 이
모듈을 ``importlib`` 로 절대경로 로드해 공유한다.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def own_create_time() -> int | None:
    """현재 프로세스의 생성시각(Windows FILETIME, 64비트 정수)을 반환한다.

    프로세스 수명 동안 값이 변하지 않는다. Windows 가 아니거나 조회 실패 시 None.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        # 64비트에서 핸들이 잘리지 않도록 반환/인자 타입을 명시한다.
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        kernel32.GetProcessTimes.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
        ]
        kernel32.GetProcessTimes.restype = wintypes.BOOL

        creation = wintypes.FILETIME()
        exit_t = wintypes.FILETIME()
        kernel_t = wintypes.FILETIME()
        user_t = wintypes.FILETIME()
        ok = kernel32.GetProcessTimes(
            kernel32.GetCurrentProcess(),  # 의사 핸들 — 닫을 필요 없음
            ctypes.byref(creation), ctypes.byref(exit_t),
            ctypes.byref(kernel_t), ctypes.byref(user_t),
        )
        if not ok:
            return None
        return (creation.dwHighDateTime << 32) | creation.dwLowDateTime
    except Exception:
        return None


# 프로세스 생성시각은 수명 동안 불변이므로 한 번만 계산한다.
_OWN_CREATE_TIME = own_create_time()


def pid_alive(pid: int, create_time: int | None = None) -> bool:
    """pid 의 프로세스가 살아 있으면 True (허브가 띄우지 않은 프로세스도 판별).

    create_time(프로세스 생성시각)이 주어지면 해당 pid 의 실제 생성시각과
    일치하는지까지 확인한다. pid 재사용으로 인한 오판을 막기 위한 검사다.
    """
    if not isinstance(pid, int) or pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.windll.kernel32
            # 64비트에서 핸들이 잘리지 않도록 반환/인자 타입을 명시한다.
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
            kernel32.GetProcessTimes.argtypes = [
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME), ctypes.POINTER(wintypes.FILETIME),
            ]
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return False
                if code.value != STILL_ACTIVE:
                    return False
                if create_time is None:
                    return True
                # pid 재사용 방어: 이 pid 의 생성시각이 기록값과 같아야 동일 프로세스.
                creation = wintypes.FILETIME()
                exit_t = wintypes.FILETIME()
                kernel_t = wintypes.FILETIME()
                user_t = wintypes.FILETIME()
                if not kernel32.GetProcessTimes(
                    handle,
                    ctypes.byref(creation), ctypes.byref(exit_t),
                    ctypes.byref(kernel_t), ctypes.byref(user_t),
                ):
                    return True  # 생성시각 조회 실패 시 생존 여부만으로 판단
                actual = (creation.dwHighDateTime << 32) | creation.dwLowDateTime
                return actual == create_time
            finally:
                kernel32.CloseHandle(handle)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def write(path, **extra) -> None:
    """현재 프로세스의 실행 상태를 ``path`` 에 기록한다. 실패는 조용히 무시한다.

    pid·create_time 외에 앱별 부가 상태(예: gdrive_enabled)를 키워드로 넘기면 함께 저장한다.
    """
    try:
        data = {"pid": os.getpid(), "create_time": _OWN_CREATE_TIME}
        data.update(extra)
        Path(path).write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except OSError:
        pass


def read_live(path) -> dict | None:
    """``path`` 의 상태 파일을 읽어, 기록된 프로세스가 살아 있을 때만 dict 를 반환한다.

    파일이 없거나, 형식이 어긋나거나, 기록된 pid 의 프로세스가 죽어 있으면(또는 pid
    재사용으로 생성시각이 달라지면) None.
    """
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    pid = data.get("pid")
    create_time = data.get("create_time")
    if not isinstance(create_time, int):
        create_time = None
    if not pid_alive(pid, create_time):
        return None
    return data


def clear(path) -> None:
    """종료 시 상태 파일을 제거한다. 실패는 조용히 무시한다."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass
