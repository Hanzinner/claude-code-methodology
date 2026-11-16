#!/usr/bin/env python3
"""Document reader for the workspace: serves reader.html (a one-file Markdown/FB2 reader) and read-only JSON routes -
folder listing, file text, search by name and text, a download route, plus two small state files (last opened file,
reader settings) so the same reading setup follows the human from device to device.

  python3 reader-server.py                     # settings from methodology.conf
  python3 reader-server.py --root DIR --port 8001 --bind 127.0.0.1

Settings (methodology.conf; an environment variable with the same name wins; a command-line flag wins over both):
  CCM_WORKSPACE        root that is served; nothing outside it is ever read
  CCM_READER_PORT      default 8001
  CCM_READER_BIND      default 127.0.0.1 (this machine only). Anything else exposes every document under the root to
                       whoever reaches the address: the reader has NO password. Put an authenticating proxy in front.
  CCM_READER_SHARED    folder the agents put documents in for the human to read (relative = under the root); shown as
                       a section at the top, newest first. Empty = the section is hidden.
  CCM_READER_HIDE      folder names hidden everywhere (tree, search, links), comma-separated. Dot-folders are always hidden.
  CCM_READER_SKIP      file-name patterns left out of search, comma-separated (e.g. briefing.md,inbox.md,*-TODO.md)
  CCM_READER_STATE     where the two state files live; default ~/.claude/reader

Safety: only .md .markdown .txt .fb2 are served; every path is resolved (symlinks too) and must stay under the root;
dot-files and dot-folders are never listed or served.
"""
import argparse, fnmatch, json, os, sys, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.realpath(__file__))
for lib in (os.path.join(HERE, "..", "..", "lib"),):      # <claude dir>/addons/reader -> <claude dir>/lib (the repo has the same layout)
    if os.path.isfile(os.path.join(lib, "ccm_conf.py")):
        sys.path.insert(0, os.path.realpath(lib))
try:
    from ccm_conf import conf as _conf
except ImportError:                                         # run on its own: environment only
    def _conf(key):
        return os.environ.get(key, "")

EXT = (".md", ".markdown", ".txt", ".fb2")
ALWAYS_HIDE = {"node_modules", "__pycache__"}
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def _list(v):
    return [x.strip() for x in (v or "").split(",") if x.strip()]


class Cfg:
    def __init__(self, root, shared="", hide="", skip="", state=""):
        self.root = os.path.realpath(os.path.expanduser(root))
        self.hide = ALWAYS_HIDE | set(_list(hide))
        self.skip = _list(skip)
        self.state = os.path.expanduser(state or "~/.claude/reader")
        self.reader = os.path.join(HERE, "reader.html")
        self.shared = None
        if shared:
            p = os.path.realpath(os.path.join(self.root, os.path.expanduser(shared)))
            if self.inside(p):
                self.shared = p
            else:
                print(f"reader: CCM_READER_SHARED={shared} is outside the root {self.root} - section hidden", file=sys.stderr)

    def inside(self, t):
        return t == self.root or t.startswith(self.root + os.sep)

    def hidden(self, t):
        """a dot-part or a hidden folder name anywhere between the root and t"""
        rel = os.path.relpath(t, self.root)
        return rel != "." and any(p.startswith(".") or p in self.hide for p in rel.split(os.sep))

    def safe_dir(self, rel):
        t = os.path.realpath(os.path.join(self.root, rel or ""))
        return t if self.inside(t) and not self.hidden(t) and os.path.isdir(t) else None

    def safe_file(self, rel):
        if not rel:
            return None
        t = os.path.realpath(os.path.join(self.root, rel))
        if not self.inside(t) or self.hidden(t) or not t.lower().endswith(EXT) or not os.path.isfile(t):
            return None
        return t

    def rel(self, t):
        return os.path.relpath(t, self.root)

    def list_dir(self, target):
        dirs, files = [], []
        try:
            entries = sorted(os.scandir(target), key=lambda e: e.name.lower())
        except OSError:
            return {"dirs": [], "files": []}
        for e in entries:
            if e.name.startswith("."):
                continue
            if e.is_dir():
                if e.name not in self.hide:
                    dirs.append({"name": e.name, "path": self.rel(e.path)})
            elif e.name.lower().endswith(EXT):
                files.append({"name": e.name, "path": self.rel(e.path)})
        return {"dirs": dirs, "files": files}

    def skipped(self, name):
        return any(fnmatch.fnmatch(name, p) for p in self.skip)

    def search(self, q, limit=80):
        ql, res = q.lower(), []
        for dp, dirs, files in os.walk(self.root):
            dirs[:] = [d for d in dirs if d not in self.hide and not d.startswith(".")]
            for f in files:
                if f.startswith(".") or not f.lower().endswith(EXT) or self.skipped(f):
                    continue
                full = os.path.join(dp, f)
                rel = self.rel(full)
                hit_name = ql in rel.lower()
                snip, hit_body = "", False
                try:
                    if os.path.getsize(full) < 2_000_000:
                        with open(full, encoding="utf-8", errors="ignore") as fh:
                            txt = fh.read()
                        i = txt.lower().find(ql)
                        if i >= 0:
                            hit_body = True
                            snip = txt[max(0, i - 40):i + len(q) + 60].replace("\n", " ").strip()
                except OSError:
                    pass
                if hit_name or hit_body:
                    res.append({"path": rel, "name": f, "snip": snip, "score": 0 if hit_name else 1})
                    if len(res) >= limit * 3:
                        break
            if len(res) >= limit * 3:
                break
        res.sort(key=lambda x: (x["score"], x["path"].lower()))
        return res[:limit]

    def shared_list(self, limit=40):
        if not self.shared:
            return None
        out = []
        try:
            for e in os.scandir(self.shared):
                if e.is_file() and e.name.lower().endswith(EXT) and not e.name.startswith("."):
                    out.append({"name": e.name, "path": self.rel(e.path), "mtime": e.stat().st_mtime})
        except OSError:
            return []
        out.sort(key=lambda x: -x["mtime"])
        return out[:limit]

    def state_file(self, name):
        return os.path.join(self.state, name)

    def write_state(self, name, text):
        os.makedirs(self.state, exist_ok=True)
        tmp = self.state_file(name) + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, self.state_file(name))


def make_handler(cfg):
    class H(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def _json(self, obj):
            self._send(200, json.dumps(obj, ensure_ascii=False), "application/json; charset=utf-8")

        def _no(self, code=403):
            self._send(code, "forbidden" if code == 403 else "not found", "text/plain; charset=utf-8")

        def do_GET(self):
            u = urllib.parse.urlparse(self.path)
            q = urllib.parse.parse_qs(u.query)
            arg = lambda k: (q.get(k) or [None])[0]
            if u.path in ("/", "/index.html", "/reader", "/reader.html"):
                try:
                    with open(cfg.reader, "rb") as fh:
                        return self._send(200, fh.read(), "text/html; charset=utf-8")
                except OSError:
                    return self._no(404)
            if u.path == "/api/dir":
                t = cfg.safe_dir(arg("p") or "")
                if t is None:
                    return self._no()
                res = cfg.list_dir(t)
                res["path"] = "" if t == cfg.root else cfg.rel(t)
                return self._json(res)
            if u.path in ("/api/file", "/api/download"):
                t = cfg.safe_file(arg("p") or "")
                if not t:
                    return self._no()
                try:
                    with open(t, "rb") as fh:
                        data = fh.read()
                except OSError:
                    return self._no(404)
                if u.path == "/api/file":
                    return self._send(200, data.decode("utf-8", errors="replace"), "text/plain; charset=utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Content-Disposition", "attachment; filename*=UTF-8''" + urllib.parse.quote(os.path.basename(t)))
                self.end_headers()
                self.wfile.write(data)
                return
            if u.path == "/api/search":
                term = (arg("q") or "").strip()
                return self._json(cfg.search(term) if len(term) >= 2 else [])
            if u.path == "/api/shared":
                return self._json(cfg.shared_list())
            if u.path == "/api/settings":
                setp = arg("set")
                if setp is not None:
                    try:
                        obj = json.loads(setp) if len(setp) < 20000 else None
                        if isinstance(obj, dict):
                            cfg.write_state("settings.json", json.dumps(obj, ensure_ascii=False))
                    except (ValueError, OSError):
                        pass
                    return self._json({"ok": True})
                try:
                    with open(cfg.state_file("settings.json"), encoding="utf-8") as fh:
                        data = json.load(fh)
                except (ValueError, OSError):
                    data = {}
                return self._json(data if isinstance(data, dict) else {})
            if u.path == "/api/last":
                setp = arg("set")
                if setp is not None:
                    if cfg.safe_file(setp):
                        try:
                            cfg.write_state("last-opened", setp)
                        except OSError:
                            pass
                    return self._json({"ok": True})
                path = ""
                try:
                    with open(cfg.state_file("last-opened"), encoding="utf-8") as fh:
                        cand = fh.read().strip()
                    path = cand if cfg.safe_file(cand) else ""
                except OSError:
                    pass
                return self._json({"path": path})
            return self._no(404)

        def log_message(self, *a):
            pass
    return H


def main():
    ap = argparse.ArgumentParser(description="Document reader for the workspace (read-only, no password).")
    ap.add_argument("--root", default=_conf("CCM_WORKSPACE") or os.path.expanduser("~/claude-projects"))
    ap.add_argument("--port", type=int, default=int(_conf("CCM_READER_PORT") or 8001))
    ap.add_argument("--bind", default=_conf("CCM_READER_BIND") or "127.0.0.1")
    a = ap.parse_args()
    cfg = Cfg(a.root, _conf("CCM_READER_SHARED"), _conf("CCM_READER_HIDE"), _conf("CCM_READER_SKIP"), _conf("CCM_READER_STATE"))
    if not os.path.isdir(cfg.root):
        print(f"reader: root {cfg.root} is not a folder (CCM_WORKSPACE / --root)", file=sys.stderr)
        sys.exit(2)
    if a.bind not in LOOPBACK:
        print(f"reader: WARNING - listening on {a.bind}: the reader has no password, anyone who reaches "
              f"http://<this machine>:{a.port}/ can read every document under {cfg.root}. Use an authenticating proxy.",
              file=sys.stderr)
    srv = ThreadingHTTPServer((a.bind, a.port), make_handler(cfg))
    print(f"reader: http://{a.bind}:{srv.server_address[1]}/  root {cfg.root}", file=sys.stderr, flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
