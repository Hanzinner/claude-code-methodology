#!/usr/bin/env python3
"""File operations that behave the same on Linux, macOS and Windows (native Python under Git Bash).

    import ccm_fs
    ccm_fs.replace(tmp, path)          # os.replace that waits out a file held open by another process on Windows
    ccm_fs.chown(path, uid, gid)       # os.chown where it exists; False where it does not (Windows) or is refused

replace: on Windows a rename onto (or from) a file that another process holds open fails with PermissionError
(WinError 5 / 32): an antivirus scanning a file that was just written, the search indexer, a reader in another
process. It lasts a moment, so the rename is tried again with a growing pause, about 5 s in all (npm's graceful-fs
does the same for the same reason). On Linux and macOS a PermissionError from a rename is a real refusal (no write
right on the folder) and is raised at once, as before.

chown: os.chown does not exist in Windows Python (AttributeError, which `except OSError` does not catch). There a
file belongs to whoever wrote it, so there is nothing to hand over: chown returns False and does nothing.
"""
import os
import time

_PAUSES = (0.05, 0.1, 0.1, 0.2, 0.2, 0.3, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5, 0.5)   # ~5 s in all


def replace(src, dst):
    for pause in _PAUSES + (None,):
        try:
            return os.replace(src, dst)
        except PermissionError:
            if os.name != "nt" or pause is None:
                raise
            time.sleep(pause)


def chown(path, uid, gid):
    f = getattr(os, "chown", None)
    if f is None:
        return False
    try:
        f(path, uid, gid)
        return True
    except OSError:
        return False
