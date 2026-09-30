"""Read-only access to the KH2 process on Windows via ReadProcessMemory (no extra packages)."""
from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from .game_data import EXE_NAME, VERSION_CHECK_VALUE, VERSIONS, GameVersion


class GameNotFound(Exception):
    pass


class UnsupportedVersion(Exception):
    pass


if sys.platform == "win32":
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    TH32CS_SNAPPROCESS = 0x2
    TH32CS_SNAPMODULE = 0x8
    TH32CS_SNAPMODULE32 = 0x10
    PROCESS_VM_READ = 0x0010
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    INVALID_HANDLE = ctypes.c_void_p(-1).value

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_void_p),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", ctypes.c_long),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    class MODULEENTRY32W(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("th32ModuleID", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("GlblcntUsage", wintypes.DWORD),
                    ("ProccntUsage", wintypes.DWORD), ("modBaseAddr", ctypes.c_void_p),
                    ("modBaseSize", wintypes.DWORD), ("hModule", wintypes.HMODULE),
                    ("szModule", wintypes.WCHAR * 256), ("szExePath", wintypes.WCHAR * 260)]

    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32FirstW.argtypes = k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32W)]
    k32.Module32FirstW.argtypes = k32.Module32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MODULEENTRY32W)]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.ReadProcessMemory.argtypes = [wintypes.HANDLE, ctypes.c_void_p, ctypes.c_void_p,
                                      ctypes.c_size_t, ctypes.POINTER(ctypes.c_size_t)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]


def _find_pid() -> int | None:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snap == INVALID_HANDLE:
        return None
    try:
        e = PROCESSENTRY32W()
        e.dwSize = ctypes.sizeof(e)
        ok = k32.Process32FirstW(snap, ctypes.byref(e))
        while ok:
            if e.szExeFile.lower() == EXE_NAME.lower():
                return e.th32ProcessID
            ok = k32.Process32NextW(snap, ctypes.byref(e))
    finally:
        k32.CloseHandle(snap)
    return None


def _module_base(pid: int) -> int | None:
    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPMODULE | TH32CS_SNAPMODULE32, pid)
    if snap == INVALID_HANDLE:
        return None
    try:
        m = MODULEENTRY32W()
        m.dwSize = ctypes.sizeof(m)
        ok = k32.Module32FirstW(snap, ctypes.byref(m))
        while ok:
            if m.szModule.lower() == EXE_NAME.lower():
                return m.modBaseAddr
            ok = k32.Module32NextW(snap, ctypes.byref(m))
    finally:
        k32.CloseHandle(snap)
    return None


class GameProcess:
    """Attached game. read(offset, n) reads relative to the game module base."""

    def __init__(self):
        if sys.platform != "win32":
            raise GameNotFound("Auto-tracking only works on Windows.")
        pid = _find_pid()
        if pid is None:
            raise GameNotFound("KH2 isn't running.")
        self.handle = k32.OpenProcess(PROCESS_VM_READ | PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not self.handle:
            raise GameNotFound(f"Couldn't open the game process (error {ctypes.get_last_error()}).")
        self.base = _module_base(pid)
        if self.base is None:
            self.close()
            raise GameNotFound("Game is still starting up.")
        self.version: GameVersion | None = None
        for v in VERSIONS:
            try:
                if self.read(v.version_check, 1)[0] == VERSION_CHECK_VALUE:
                    self.version = v
                    break
            except OSError:
                continue
        if self.version is None:
            self.close()
            raise UnsupportedVersion("This game version isn't supported yet. Update VERSIONS in game_data.py.")

    def read(self, offset: int, size: int) -> bytes:
        return self.read_abs(self.base + offset, size)

    def read_abs(self, address: int, size: int) -> bytes:
        buf = (ctypes.c_ubyte * size)()
        got = ctypes.c_size_t()
        if not k32.ReadProcessMemory(self.handle, ctypes.c_void_p(address), buf, size, ctypes.byref(got)):
            raise OSError("read failed")
        return bytes(buf)

    def alive(self) -> bool:
        code = wintypes.DWORD()
        return bool(k32.GetExitCodeProcess(self.handle, ctypes.byref(code))) and code.value == 259  # STILL_ACTIVE

    def close(self):
        if getattr(self, "handle", None):
            k32.CloseHandle(self.handle)
            self.handle = None
