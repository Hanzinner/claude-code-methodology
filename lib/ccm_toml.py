#!/usr/bin/env python3
"""TOML reading on any Python 3.9+: tomllib where it exists (3.11+), else tomli if installed, else a small parser.

    import ccm_toml
    with open(path, "rb") as f:
        c = ccm_toml.load(f)           # a dict; ccm_toml.TOMLDecodeError (a ValueError) on text it cannot read
    c = ccm_toml.loads(text)

Why: a stock macOS has /usr/bin/python3 3.9 (no tomllib), and the scripts that read release.toml died at the import
with ModuleNotFoundError - the drift watchman, the stale-repo reminder and the releaser all went quiet.

The fallback reads what release.toml uses: `key = value` lines, [table] and [a.b] headers, # comments, and values that
are basic "strings" (with \\" \\\\ \\n \\t \\r \\uXXXX escapes), 'literal strings', integers, floats, true/false and
arrays of them (one line or several). Anything else (inline tables, dates, multi-line strings, dotted keys, a key
given twice) is a TOMLDecodeError, never a silent guess: a gate command read wrong is worse than one not read.
"""
import re

try:
    import tomllib as _lib
except ImportError:  # python < 3.11
    try:
        import tomli as _lib
    except ImportError:
        _lib = None


class TOMLDecodeError(ValueError):
    pass


if _lib is not None:
    TOMLDecodeError = _lib.TOMLDecodeError  # noqa: F811  (a ValueError subclass there too)

    def load(fp):
        return _lib.load(fp)

    def loads(s):
        return _lib.loads(s)
else:
    def load(fp):
        data = fp.read()
        if isinstance(data, bytes):
            try:
                data = data.decode("utf-8")
            except UnicodeDecodeError as e:
                raise TOMLDecodeError(f"not UTF-8: {e}")
        return loads(data)

    def loads(s):
        return _Parser(s).parse()


_KEY = re.compile(r"[A-Za-z0-9_-]+")
_NUM = re.compile(r"[+-]?(0|[1-9](_?[0-9])*)(\.[0-9](_?[0-9])*)?([eE][+-]?[0-9]+)?")
_ESC = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", '"': '"', "\\": "\\"}


class _Parser:
    def __init__(self, s):
        self.s, self.i, self.line = s.replace("\r\n", "\n"), 0, 1

    def err(self, msg):
        raise TOMLDecodeError(f"{msg} (line {self.line})")

    def peek(self):
        return self.s[self.i] if self.i < len(self.s) else ""

    def skip_ws(self, newlines=False):
        while self.i < len(self.s):
            c = self.s[self.i]
            if c in " \t":
                self.i += 1
            elif c == "#":
                while self.i < len(self.s) and self.s[self.i] != "\n":
                    self.i += 1
            elif newlines and c == "\n":
                self.i += 1
                self.line += 1
            else:
                break

    def end_of_line(self):
        self.skip_ws()
        c = self.peek()
        if c == "\n":
            self.i += 1
            self.line += 1
        elif c:
            self.err(f"unexpected {c!r} after a value")

    def key(self):
        if self.peek() in "\"'":
            return self.string()
        m = _KEY.match(self.s, self.i)
        if not m:
            self.err("a key expected")
        self.i = m.end()
        return m.group()

    def parse(self):
        root = {}
        cur = root
        while True:
            self.skip_ws(newlines=True)
            if not self.peek():
                return root
            if self.peek() == "[":
                self.i += 1
                if self.peek() == "[":
                    self.err("arrays of tables are not supported")
                path = []
                while True:
                    self.skip_ws()
                    path.append(self.key())
                    self.skip_ws()
                    if self.peek() == ".":
                        self.i += 1
                        continue
                    if self.peek() != "]":
                        self.err("] expected")
                    self.i += 1
                    break
                cur = root
                for p in path:
                    cur = cur.setdefault(p, {})
                    if not isinstance(cur, dict):
                        self.err(f"{p} is not a table")
                self.end_of_line()
                continue
            k = self.key()
            self.skip_ws()
            if self.peek() == ".":
                self.err("dotted keys are not supported")
            if self.peek() != "=":
                self.err("= expected after a key")
            self.i += 1
            self.skip_ws()
            if k in cur:
                self.err(f"key {k!r} given twice")
            cur[k] = self.value()
            self.end_of_line()

    def value(self):
        c = self.peek()
        if c in "\"'":
            return self.string()
        if c == "[":
            self.i += 1
            out = []
            while True:
                self.skip_ws(newlines=True)
                if self.peek() == "]":
                    self.i += 1
                    return out
                out.append(self.value())
                self.skip_ws(newlines=True)
                if self.peek() == ",":
                    self.i += 1
                elif self.peek() == "]":
                    self.i += 1
                    return out
                else:
                    self.err(", or ] expected in an array")
        for word, v in (("true", True), ("false", False)):
            if self.s.startswith(word, self.i):
                self.i += len(word)
                return v
        m = _NUM.match(self.s, self.i)
        if m and m.group():
            self.i = m.end()
            t = m.group().replace("_", "")
            return float(t) if any(x in t for x in ".eE") else int(t)
        self.err("a value expected (string, number, true/false or array)")

    def string(self):
        q = self.peek()
        if self.s.startswith(q * 3, self.i):
            self.err("multi-line strings are not supported")
        self.i += 1
        out = []
        while True:
            if self.i >= len(self.s) or self.s[self.i] == "\n":
                self.err("unterminated string")
            c = self.s[self.i]
            self.i += 1
            if c == q:
                return "".join(out)
            if c == "\\" and q == '"':
                e = self.peek()
                self.i += 1
                if e in _ESC:
                    out.append(_ESC[e])
                elif e in "uU":
                    n = 4 if e == "u" else 8
                    h = self.s[self.i:self.i + n]
                    if not re.fullmatch(r"[0-9A-Fa-f]{%d}" % n, h):
                        self.err("bad \\u escape")
                    out.append(chr(int(h, 16)))
                    self.i += n
                else:
                    self.err(f"bad escape \\{e}")
            else:
                out.append(c)
