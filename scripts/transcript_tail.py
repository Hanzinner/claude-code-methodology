#!/usr/bin/env python3
"""transcript_tail - the transcript lines covering the LAST turn, without reading the whole file.

Why: ten Stop-hook branches each read the entire .jsonl - 13 s of a 20 s budget on a 63 MB transcript; a few more
branches and the Stop dispatcher is killed by its timeout, and the branches after the kill point silently never run.
Branches that only need the last turn (a link guard, a proof guard, a work guard) are fine with just the tail.

lines(tp, is_prompt, need='"user"', skip='"tool_result"') -> list of JSON lines (str) from the LAST line for which
is_prompt(o) is true to the end of the file; if there is none, the whole file. need/skip are a cheap substring
filter before json.loads (for "the last assistant message": need='"assistant"', skip=None).

CLI:  transcript_tail.py <transcript.jsonl>   prints the lines of the last human turn."""
import json, os, re

BLOCK = 2 * 1024 * 1024


def lines(tp, is_prompt, need='"user"', skip='"tool_result"'):
    """Reads from the end in 2 MB blocks, every byte once (v1 doubled the window and re-read the tail: 59 MB in
    4.9 s instead of 1.3). A candidate "human message" goes through json.loads only after the cheap filter:
    lines with tool_result (the heaviest) are never a human message."""
    try:
        size = os.path.getsize(tp)
        f = open(tp, "rb")
    except OSError:
        return []
    with f:
        pos, tail, done = size, b"", []       # done - complete lines (str), newest last
        while True:
            start = max(0, pos - BLOCK)
            f.seek(start)
            buf = f.read(pos - start) + tail
            pos = start
            parts = buf.split(b"\n")
            if pos > 0:
                tail, parts = parts[0], parts[1:]   # the first one may be cut off, it is glued to the next block
            else:
                tail = b""
            new = [p.decode("utf-8", "replace") for p in parts]
            for i in range(len(new) - 1, -1, -1):
                l = new[i]
                if (need and need not in l) or (skip and skip in l):
                    continue
                try:
                    o = json.loads(l)
                except ValueError:
                    continue
                if is_prompt(o):
                    return new[i:] + done
            done = new + done
            if pos == 0:
                return done


_UUID = re.compile(r'"uuid":\s*"([^"]+)"')          # the harness writes compactly, but json.dumps defaults to a space
_PARENT = re.compile(r'"parentUuid":\s*"([^"]+)"')
_ASSIST = re.compile(r'"type":\s*"assistant"')


def live_branch(tp):
    """The live branch after the LAST compaction -> dict(live=[lines of the live branch], last_is_ghost=bool), or None (no compactions).

    Why: a background-task notification arrived DURING a manual /compact, and the old conversation (~700k) kept
    living in parallel with the new one in the same file: its own alarms kept poking it, and a work guard blocked
    its stop. The branches are told apart by the parentUuid chain: the live one descends from the compaction
    boundary, the ghost from the old root. Cheap: uuid/parentUuid by regex, json.loads only at the boundary."""
    is_boundary = lambda o: o.get("type") == "system" and o.get("subtype") == "compact_boundary"
    ls = lines(tp, is_boundary, need='"compact_boundary"', skip=None)
    if not ls:
        return None
    try:
        first = json.loads(ls[0])
    except ValueError:
        return None
    if not is_boundary(first):
        return None                       # no compactions in the file - a single branch
    live_ids, live, last_ghost = {first.get("uuid")}, [], False
    for l in ls[1:]:
        m = _UUID.search(l)
        if not m:
            continue
        p = _PARENT.search(l)
        mine = bool(p and p.group(1) in live_ids)
        if mine:
            live_ids.add(m.group(1)); live.append(l)
        if _ASSIST.search(l):
            last_ghost = not mine
    return {"live": live, "last_is_ghost": last_ghost}


def _is_human(o):
    if o.get("type") != "user":
        return False
    c = (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content")
    if isinstance(c, str):
        return True
    return isinstance(c, list) and any(isinstance(b, dict) and b.get("type") == "text" for b in c)


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print(__doc__, file=sys.stderr); sys.exit(2)
    for _l in lines(sys.argv[1], _is_human):
        print(_l)
