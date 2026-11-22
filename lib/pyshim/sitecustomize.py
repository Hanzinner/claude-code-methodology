"""Line endings as on Linux for our Python on Windows. Installed only there: install.sh copies it to
<install dir>/lib/pyshim/, and that folder goes on PYTHONPATH for the hooks (lib/pyshim/env.sh, sourced by
hooks/hook-safe.sh) and for every `python3` the scripts call (lib/pyshim/python3). Python finds a module named
sitecustomize on its path and imports it at start - that is the whole mechanism.

Why: Python on Windows ends every printed and written line with \r\n. Git Bash keeps the \r: a path read with
$(python3 lib/ccm_conf.py CCM_WORKSPACE) ends in \r and names a folder that does not exist, and a line written into an
inbox reads "## New\r" to `grep -x "## New"`. Here stdout and stderr end lines with \n, and so does a file opened for
writing ("w", "a", "x") when the caller did not choose a newline. Reading is untouched (Python reads both endings).
On Linux and macOS this file is never on the path; if it were, it would do nothing (os.name is not "nt").
"""
import os

if os.name == "nt":
    import builtins, io, sys

    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(newline="\n")
        except (AttributeError, ValueError):   # no stream (pythonw) or not a text stream
            pass

    _io_open = io.open

    def _open_lf(file, mode="r", buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
        if newline is None and "b" not in mode and "r" not in mode:
            newline = "\n"
        return _io_open(file, mode, buffering, encoding, errors, newline, closefd, opener)

    builtins.open = io.open = _open_lf
