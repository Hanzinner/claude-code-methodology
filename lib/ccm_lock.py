#!/usr/bin/env python3
"""fcntl.flock for a Python without fcntl (Windows): the same names, the same calls, on msvcrt.locking.

    try:
        import fcntl
    except ImportError:          # Windows: no fcntl
        import ccm_lock as fcntl

Then fcntl.flock(f, fcntl.LOCK_EX), fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB) (raises BlockingIOError when the lock
is taken, as fcntl does) and fcntl.flock(f, fcntl.LOCK_UN) work as before. On Linux and macOS the real fcntl is used and
this file is never imported.

The lock is on the first byte of the file (msvcrt locks a byte range, not the file), so every process that locks the
same file meets on the same byte. A shared lock (LOCK_SH) is taken as exclusive: msvcrt has no shared locks. Closing
the file releases the lock, as with flock.
"""
import os, time

LOCK_SH, LOCK_EX, LOCK_NB, LOCK_UN = 1, 2, 4, 8


def _fd(f):
    return f if isinstance(f, int) else f.fileno()


def flock(f, op):
    import msvcrt   # only reached on Windows: on other systems the real fcntl is imported instead of this module
    fd = _fd(f)
    pos = os.lseek(fd, 0, os.SEEK_CUR)   # msvcrt locks from the current position: lock byte 0, then go back
    os.lseek(fd, 0, os.SEEK_SET)
    try:
        if op & LOCK_UN:
            try:
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
            except OSError:
                pass   # not locked: flock(LOCK_UN) is silent too
            return
        while True:
            try:
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
                return
            except OSError:
                if op & LOCK_NB:
                    raise BlockingIOError("the lock is held by another process")
                time.sleep(0.05)   # LK_LOCK gives up after 10 s; flock without LOCK_NB waits as long as it takes
    finally:
        os.lseek(fd, pos, os.SEEK_SET)
