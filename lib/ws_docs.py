#!/usr/bin/env python3
"""The shared documents every agent in the workspace follows, copied from docs/ into the workspace root: four rules
and WEB-PLAYBOOK.md, the journal agents building sites read first and append their experience to.

  ws_docs.py install <repo dir> <workspace> <stamp dir> [--dry-run]   # install.sh calls this
  ws_docs.py render <repo dir> <docs file>                            # the workspace version, to stdout
  ws_docs.py links <workspace>                                        # broken links in them; rc 1 if any

docs/coding-standard.md -> CODING-STANDARD.md, project-work.md -> PROJECT-WORK.md, dev-methodology.md ->
DEV-METHODOLOGY.md, po-interface.md -> PO-INTERFACE.md (the names hooks/proof-guard.py and the briefing template expect),
web-playbook.md -> WEB-PLAYBOOK.md (code-pitfalls/web.md points there), hall-of-shame-docs.md -> DOC-SLOP.md (CLAUDE.md
points there: the test "what does the person do with this line?").
Links are rewritten on the way: between these documents -> the new names; to any other file of the repo -> its absolute path
in this clone, so nothing in the workspace points to a file that is not there.

Updates never overwrite the human's edits (the same scheme as CLAUDE.md):
  * missing                          -> written;
  * unchanged since we wrote it      -> replaced by the new version (also an untouched copy an older installer made);
  * edited by the human              -> kept; the new version goes next to it as <NAME>.new and what changed in OUR
                                        text since the version they last merged as <NAME>.changes. check-install stays
                                        red until they merge and run: mv <NAME>.new <stamp dir>/ws-<NAME>.base
Stamps: <stamp dir>/ws-<NAME>.sha256 (what we wrote) and ws-<NAME>.base (our text they have merged).
"""
import difflib, hashlib, os, re, sys

import ccm_fs  # os.replace that waits out a file held open on Windows (lib/ is this file's own folder)

DOCS = {"coding-standard.md": "CODING-STANDARD.md", "project-work.md": "PROJECT-WORK.md",
        "dev-methodology.md": "DEV-METHODOLOGY.md", "po-interface.md": "PO-INTERFACE.md",
        "web-playbook.md": "WEB-PLAYBOOK.md", "hall-of-shame-docs.md": "DOC-SLOP.md"}
LINK = re.compile(r"\]\(([^)\s]+)\)")
TEXT = re.compile(r"(?<![\w/.-])docs/(" + "|".join(re.escape(k[:-3]) for k in DOCS) + r")\.md")


def render(repo, src):
    docs_dir = os.path.join(os.path.realpath(repo), "docs")
    text = open(src, encoding="utf-8").read()

    def link(m):
        t = m.group(1)
        if re.match(r"[a-z]+:|#|/|<", t):
            return m.group(0)
        path, _, anchor = t.partition("#")
        full = os.path.normpath(os.path.join(docs_dir, path))
        if os.path.dirname(full) == docs_dir and os.path.basename(full) in DOCS:
            new = DOCS[os.path.basename(full)]
        else:
            new = f"<{full}>" if re.search(r"[\s()<>]", full) else full
            if anchor:
                new = new[:-1] + "#" + anchor + ">" if new.startswith("<") else new + "#" + anchor
                anchor = ""
        return f"]({new}{'#' + anchor if anchor else ''})"

    text = LINK.sub(link, text)
    return TEXT.sub(lambda m: DOCS[m.group(1) + ".md"], text)


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def read(p):
    try:
        return open(p, encoding="utf-8").read()
    except OSError:
        return None


def write(p, s):
    tmp = p + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(s)
    ccm_fs.replace(tmp, p)


def install(repo, ws, stamp, dry):
    out, added, updated, pending = [], 0, 0, []
    os.makedirs(ws, exist_ok=True)
    if not dry:
        os.makedirs(stamp, exist_ok=True)
    for src_name, name in DOCS.items():
        src = os.path.join(repo, "docs", src_name)
        if not os.path.isfile(src):
            out.append(f"  {name}: no docs/{src_name} in the repo - skipped")
            continue
        new, raw = render(repo, src), open(src, encoding="utf-8").read()
        dst = os.path.join(ws, name)
        cur, stored = read(dst), read(os.path.join(stamp, f"ws-{name}.sha256"))
        base_p = os.path.join(stamp, f"ws-{name}.base")
        base = read(base_p)

        def given():
            if not dry:
                write(dst, new)
                write(os.path.join(stamp, f"ws-{name}.sha256"), sha(new))
                write(base_p, new)

        if cur is None:
            given(); added += 1
        elif (stored and sha(cur) == stored.strip()) or (not stored and cur == raw):
            if cur != new:
                given(); updated += 1
        elif cur == new:
            if not dry and base != new:
                write(base_p, new); write(os.path.join(stamp, f"ws-{name}.sha256"), sha(new))
        elif base == new:
            pass   # the human already merged this version of our text into their own file
        else:
            if not dry:
                write(dst + ".new", new)
                if base is not None:
                    diff = "".join(difflib.unified_diff(base.splitlines(True), new.splitlines(True),
                                                        "our text, last merged", "our text, now"))
                else:
                    diff = f"# First merge: all of our text is new to this {name}\n" + new
                write(dst + ".changes", diff)
            pending.append(name)
    out.insert(0, f"workspace documents: {added} added, {updated} updated" +
               (f", {len(pending)} kept as yours with a .new next to them: {', '.join(pending)}" if pending else ""))
    for name in pending:
        out.append(f"  {name} is yours - not touched. Ours: {name}.new, what changed in ours: {name}.changes. Merge, then: "
                   f"mv {os.path.join(ws, name)}.new {os.path.join(stamp, 'ws-' + name + '.base')}")
    return out


def broken_links(ws):
    bad = []
    for name in DOCS.values():
        p = os.path.join(ws, name)
        txt = read(p)
        if txt is None:
            bad.append(f"{name}: missing")
            continue
        for m in LINK.finditer(txt):
            t = m.group(1)
            if re.match(r"[a-z]+:|#", t):
                continue
            path = t.strip("<>").partition("#")[0]
            full = path if path.startswith("/") else os.path.join(ws, path)
            if not os.path.exists(full):
                bad.append(f"{name}: ({t}) -> {full} does not exist")
    return bad


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[:1] == ["install"] and len(a) >= 4:
        print("\n".join(install(a[1], a[2], a[3], "--dry-run" in a)))
    elif a[:1] == ["render"] and len(a) == 3:
        sys.stdout.write(render(a[1], a[2]))
    elif a[:1] == ["links"] and len(a) == 2:
        b = broken_links(a[1])
        print("\n".join(b) if b else "no broken links")
        sys.exit(1 if b else 0)
    else:
        print(__doc__.strip().split("\n\n")[1]); sys.exit(2)
