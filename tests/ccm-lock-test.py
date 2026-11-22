#!/usr/bin/env python3
"""lib/ccm_lock.py (fcntl.flock for Windows) on Linux: a stand-in msvcrt whose locking() is a POSIX byte-range lock
on the same byte - the semantics msvcrt.locking has (LK_NBLCK fails at once when another holder has the byte,
LK_UNLCK frees it). Checks: exclusive lock, LOCK_NB raises BlockingIOError like fcntl, a blocking lock waits until
the holder lets go, LOCK_UN frees, the file position is kept. Last line: ccm-lock: N pass, M fail."""
import fcntl as real_fcntl, multiprocessing as mp, os, sys, tempfile, time, types

HERE = os.path.dirname(os.path.abspath(__file__))
for c in (os.environ.get("CCM_REPO_DIR"), os.path.join(HERE, "..")):
    if c and os.path.isfile(os.path.join(c, "lib", "ccm_lock.py")):
        sys.path.insert(0, os.path.join(c, "lib")); break
else:
    print("ccm-lock: SKIP (no lib/ccm_lock.py next to this test: set CCM_REPO_DIR=<clone> - nothing was tested)"); sys.exit(0)

import multiprocessing.synchronize, subprocess  # noqa: E401,F401 - before the fake: they look for msvcrt to detect Windows
fake = types.ModuleType("msvcrt")
fake.LK_UNLCK, fake.LK_LOCK, fake.LK_NBLCK = 0, 1, 2
def locking(fd, mode, n):
    off = os.lseek(fd, 0, os.SEEK_CUR)
    if mode == fake.LK_UNLCK:
        real_fcntl.lockf(fd, real_fcntl.LOCK_UN, n, off)
    else:
        real_fcntl.lockf(fd, real_fcntl.LOCK_EX | real_fcntl.LOCK_NB, n, off)   # OSError when taken, as msvcrt
fake.locking = locking
sys.modules["msvcrt"] = fake
import ccm_lock  # noqa: E402

passed = failed = 0
def ok(name, cond):
    global passed, failed
    if cond: passed += 1
    else: failed += 1; print("FAIL:", name)

def holder(path, hold, ready):   # another process: takes the lock, says so, holds it for `hold` seconds
    import sys as s; s.modules["msvcrt"] = fake
    f = open(path, "a"); ccm_lock.flock(f, ccm_lock.LOCK_EX); ready.set(); time.sleep(hold); f.close()

def try_once(path):   # another process: exit 0 = got the lock at once, 1 = refused
    import sys as s; s.modules["msvcrt"] = fake
    try:
        ccm_lock.flock(open(path, "a"), ccm_lock.LOCK_EX | ccm_lock.LOCK_NB); os._exit(0)
    except BlockingIOError:
        os._exit(1)

if __name__ == "__main__":
    os.environ.setdefault("CCM_TEST", "1")
    d = tempfile.mkdtemp(); p = os.path.join(d, "x.lock")
    try:
        ctx = mp.get_context("fork")
        ready = ctx.Event(); h = ctx.Process(target=holder, args=(p, 1.5, ready)); h.start(); ready.wait(5)
        f = open(p, "a")
        try:
            ccm_lock.flock(f, ccm_lock.LOCK_EX | ccm_lock.LOCK_NB); got = True
        except BlockingIOError:
            got = False
        ok("1 LOCK_NB while another process holds it -> BlockingIOError", got is False)
        t = time.time(); ccm_lock.flock(f, ccm_lock.LOCK_EX); waited = time.time() - t
        ok(f"2 a blocking LOCK_EX waits until the holder lets go ({waited:.1f}s)", 0.5 < waited < 5)
        h.join(5)
        # 3-4 from another process (a POSIX range lock, the stand-in, is per process; msvcrt's is per handle)
        def probe():
            q = ctx.Process(target=try_once, args=(p,)); q.start(); q.join(5); return q.exitcode
        ok("3 held here -> another process is refused", probe() == 1)
        ccm_lock.flock(f, ccm_lock.LOCK_UN)
        ok("4 after LOCK_UN another process gets it", probe() == 0)
        w = open(os.path.join(d, "data"), "w+"); w.write("hello"); pos = w.tell(); w.flush()
        ccm_lock.flock(w, ccm_lock.LOCK_EX); ok("5 the file position is kept", w.tell() == pos)
        ccm_lock.flock(w, ccm_lock.LOCK_UN); ccm_lock.flock(w, ccm_lock.LOCK_UN)
        ok("6 LOCK_UN of a lock not held is silent", True)
    finally:
        import shutil; shutil.rmtree(d, ignore_errors=True)
    print(f"ccm-lock: {passed} pass, {failed} fail"); sys.exit(1 if failed else 0)
