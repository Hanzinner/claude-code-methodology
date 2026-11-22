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

# One home for bash and Python (the same rule as home_follows_HOME in lib/ccm_conf.py, kept here for the scripts that
# do not import it): Windows Python takes "~" from USERPROFILE and ignores HOME, so a test that isolated itself with
# HOME=<temp dir> had its Python write into the person's real ~/.claude. USERPROFILE follows an absolute HOME.
_h, _up = os.environ.get("HOME"), os.environ.get("USERPROFILE")
if _h and _up is not None and os.path.isabs(_h) and (os.name != "nt" or os.path.splitdrive(_h)[0]) \
        and os.path.normcase(os.path.normpath(_h)) != os.path.normcase(os.path.normpath(_up)):
    os.environ["USERPROFILE"] = _h

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
