#!/usr/bin/env python3
"""os.kill(pid, 0) - "is this process alive?" - without killing it on Windows.

    from ccm_proc import kill0
    kill0(pid)      # instead of os.kill(pid, 0): returns if alive, raises as os.kill does if not

On Linux and macOS this IS os.kill(pid, 0), with the same exceptions (ProcessLookupError, PermissionError, ...).
On Windows os.kill(pid, 0) is not a probe: any signal other than CTRL_C/CTRL_BREAK ends the process (TerminateProcess,
exit code 0) - a liveness check there killed what it checked. Here Windows asks OpenProcess/GetExitCodeProcess
instead and raises ProcessLookupError when the process is gone; nothing is ever sent to it.
A pid written by Git Bash ($$) is an MSYS pid, not a Windows one: on Windows the answer for such a pid is about the
Windows process with that number, so treat it as a hint, never as a reason to act on a process.
"""
import os


def kill0(pid):
    pid = int(pid)
    if os.name != "nt":
        os.kill(pid, 0)
        return
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    h = k.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
    if not h:
        if ctypes.get_last_error() == 5:               # ERROR_ACCESS_DENIED: it exists, it is someone else's
            raise PermissionError(1, "process exists, access denied", str(pid))
        raise ProcessLookupError(3, "no such process", str(pid))
    try:
        code = wintypes.DWORD()
        if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:   # 259 = STILL_ACTIVE
            raise ProcessLookupError(3, "no such process", str(pid))
    finally:
        k.CloseHandle(h)


def sh_argv():
    """What goes before a .sh path to start it from Python: [] on Linux and macOS (the #! line does it); on Windows
    [<Git Bash's bash.exe>] - Windows cannot start a .sh, and a bare "bash" would be found in System32 first, which is
    the WSL launcher. shutil.which follows PATH, where Git Bash puts its own /usr/bin first."""
    if os.name != "nt":
        return []
    import shutil
    return [shutil.which("bash") or "bash"]


def bash_exe():
    """"bash" for subprocess.run(["bash", "-c", ...]): the same word on Linux and macOS; on Windows the full path of
    Git Bash's bash.exe (a bare "bash" is System32's WSL launcher - the command would run inside WSL, if at all)."""
    return (sh_argv() or ["bash"])[0]
