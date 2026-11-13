#!/usr/bin/env python3
"""work-guard — Stop gate "don't stop with open tasks".

Why: the human got tired of re-waking agents every time they stopped with work still queued. An agent that is on the
guard list may end a turn only if ALL of these hold:
  (a) the "## New" section of its inbox has no unprocessed `- [ ]` items, AND
  (b) if its agent TODO has open runnable `- [ ]` items (not marked ⏳/⏸ = waiting), the last message has a line
      "STATE: ..." (waiting for X / blocked: ...), AND
  (c) ALWAYS (unless the alarm is off, see modes) a live background alarm: `scripts/inbox_wait.sh <agent>` — a new
      letter or a time wakes the tab; without it a new letter never reaches a sleeping tab.
Otherwise it prints {"decision":"block","reason":...} with what to do.

Only agents listed in the guard file act under it (config key CCM_WORK_GUARD_AGENTS = path to a file, one agent
folder name per line, `#` comments; empty = the guard is OFF for everyone). A mechanism coarser than its rule
hurts everyone else, so it touches only the agents named there. The agent's identity comes from
~/.claude/agent-identity/<session_id> (written by briefing-watchman).

Also here:
  * Context >= RECAP_AT tokens -> once per "filling" demand a recap; the human gets a line "type /compact" in the
    human TODO (an agent can't compact itself; after the compact the line closes itself).
  * Ghost: a turn of a branch that does NOT descend from the last compaction boundary (an old conversation that a
    background notification woke up during /compact) is not blocked — let it stop (transcript_tail.live_branch).
  * Memory pressure: the harness itself stops background tasks of an idle session when memory is low and tells the
    agent "Do not start it again on your own". Then the alarm is not demanded (otherwise the guard pushes against the
    harness's ban); the stop is allowed, and the infra agent (CCM_INFRA_AGENT, empty = nobody) gets a letter once.
  * Alarm modes per agent: <CCM_ALARM_MODE_DIR>/<agent> = off | once | auto | always (no file = auto).
      off: alarm not demanded (only the human wakes the tab). once: demanded until inbox_wait woke on a letter, then
      it switches itself to off. auto: demanded while there was work (a letter in the inbox or a human message) within
      the last CCM_ALARM_AUTO_IDLE seconds (default 3600); after an hour of silence — not. always: always.
      Switching: by the human's words in the tab (newer than the mode file; the last phrase wins) or by editing the file.
  * "turn off the alarm" from the human today, or a file <agent folder>/.no-alarm touched today -> no alarm demanded
    until the end of the day.
Loop guard: at most MAX_BLOCKS blocks in a row per session (then a pass with a log line). Any error -> fail-open.
Log: ~/.claude/work-guard.log; counters: ~/.claude/work-guard/.
Config: CCM_WORK_GUARD_AGENTS, CCM_ALARM_MODE_DIR, CCM_ALARM_AUTO_IDLE, CCM_INFRA_AGENT, CCM_HUMAN_NAME, CCM_CLAUDE_DIR,
CCM_LANG_EXTRA (contains "uk" -> Ukrainian "СТАН:" marker and alarm phrases are understood too)."""
import glob, json, os, re, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
from ccm_conf import conf  # noqa: E402

HOME = os.path.expanduser("~")
UK = "uk" in conf("CCM_LANG_EXTRA", "")
STATE = f"{HOME}/.claude/work-guard"
LOG = f"{HOME}/.claude/work-guard.log"
MAX_BLOCKS = 12
RECAP_AT = 700_000   # for 1M-token models: "less than 30% free"
MODES = ("off", "once", "auto", "always")
HUMAN = conf("CCM_HUMAN_NAME", "the user")


def scripts_dir():
    """where inbox_wait.sh / inbox_post.sh live: next to this hook's sibling scripts/ (the installed layout)"""
    d = os.path.join(HERE, "..", "scripts")
    return os.path.realpath(d) if os.path.isdir(d) else os.path.join(conf("CCM_CLAUDE_DIR", ""), "scripts")


def mode_dir():
    return conf("CCM_ALARM_MODE_DIR", "") or f"{HOME}/.claude/alarm-mode"


def auto_idle():
    try:
        return int(conf("CCM_ALARM_AUTO_IDLE", "3600"))
    except ValueError:
        return 3600


STATE_RE = re.compile(r"(?m)^\W{0,4}(?:STATE" + ("|СТАН" if UK else "") + r")\s*:")


def _join(*parts):
    return "|".join(f"(?:{p})" for p in parts if p)


# alarm phrases: English always, Ukrainian when CCM_LANG_EXTRA has "uk"
_OFF_EN = (r"(?:turn(?:ing)? off|switch(?:ing)? off|disabl\w+|stop(?:ping)?|kill(?:ing)?|remov\w+|drop|cancel\w*|without|no more)\s+(?:\S+\s+){0,2}?alarms?\b"
           r"|alarms?\s+(?:off|(?:is\s+|are\s+)?not\s+needed|(?:is\s+|are\s+)?no\s+longer\s+needed)|\bno alarms?\b")
_OFF_UK = (r"(?:вимкн\w*|(?:по)?стоп\w*|зупин\w*|не\s+(?:запускай|став|вмикай|треба)|прибер\w*|без)\s+(?:\S+\s+){0,2}?будильник\w*"
           r"|будильник\w*\s+(?:не\s+(?:треба|потрібен|запускай)|вимкн\w*|геть)")
_ON_EN = r"(?:turn(?:ing)? on|switch(?:ing)? on|enabl\w+|start(?:ing)?|restart\w*|set(?:ting)?(?:\s+up)?|bring\s+back|put\s+back)\s+(?:\S+\s+){0,2}?alarms?\b"
_ON_UK = r"(?:увімкн\w*|запуст\w*|постав\w*|верни|включ\w*)\s+(?:\S+\s+){0,2}?будильник\w*"
_ALWAYS_EN = (r"(?:permanent|always[- ]on|constant|persistent|continuous)\s+(?:\S+\s+){0,2}?alarms?\b"
              r"|alarms?\s+(?:\S+\s+){0,1}?(?:permanent|always|constantly)\b|(?:set|make|switch|turn)\s+(?:it\s+)?(?:to\s+)?(?:permanent|always[- ]on)\b")
_ALWAYS_UK = (r"(?:постійн\w*|завжди)\s+(?:\S+\s+){0,2}?будильник|будильник\w*\s+(?:\S+\s+){0,1}?(?:постійн\w*|завжди)"
              r"|(?:постав\w*|зроби|увімкн\w*)\s+постійн\w*")
_ONCE_EN = (r"(?:one[- ]shot|one[- ]time|single|once)\s+(?:\S+\s+){0,2}?alarms?\b|alarms?\s+(?:\S+\s+){0,1}?(?:once|one[- ]shot|one[- ]time)\b"
            r"|(?:set|make|switch|turn)\s+(?:it\s+)?(?:to\s+)?(?:one[- ]shot|one[- ]time)\b")
_ONCE_UK = (r"одноразов\w*\s+(?:\S+\s+){0,2}?будильник|будильник\w*\s+(?:\S+\s+){0,1}?одноразов\w*"
            r"|(?:постав\w*|зроби|увімкн\w*)\s+одноразов\w*")
ALARM_OFF = re.compile(_join(_OFF_EN, _OFF_UK if UK else ""), re.I)
ALARM_ON = re.compile(_join(_ON_EN, _ON_UK if UK else ""), re.I)
ALARM_ALWAYS = re.compile(_join(_ALWAYS_EN, _ALWAYS_UK if UK else ""), re.I)
ALARM_ONCE = re.compile(_join(_ONCE_EN, _ONCE_UK if UK else ""), re.I)

SECTION_NEW = "(?:New|Нові)(?: candidates| кандидати)?"


def _tail(tp, what):
    """Tail of the transcript from the last assistant row with TEXT (what="text") or with usage (what="usage")
    (transcript_tail): the whole .jsonl used to be read twice per Stop. The last assistant row is often only a tool_use."""
    sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
    from transcript_tail import lines
    if what == "text":
        pred = lambda o: o.get("type") == "assistant" and any(isinstance(c, dict) and c.get("type") == "text"
                                                           for c in ((o.get("message") if isinstance(o.get("message"), dict) else {}).get("content") or []))
        return lines(tp, pred, need='"text"', skip=None)
    return lines(tp, lambda o: o.get("type") == "assistant" and (o.get("message") if isinstance(o.get("message"), dict) else {}).get("usage"),
                 need='"usage"', skip=None)


def _real(o):
    """An assistant row from the model, not a synthetic one (a limit error etc.: model "<synthetic>", zero usage)."""
    return o.get("type") == "assistant" and (o.get("message") if isinstance(o.get("message"), dict) else {}).get("model") != "<synthetic>"


def last_assistant(tp, rows=None):
    a = ""
    try:
        for line in (rows if rows is not None else _tail(tp, "text")):
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            if _real(o):
                for c in (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content") or []:
                    if isinstance(c, dict) and c.get("type") == "text":
                        a = c["text"]
    except OSError:
        pass
    return a


def context_tokens(tp, rows=None):
    """Context size by the last assistant usage (rows = the live branch only); synthetic rows don't count."""
    u = None
    try:
        for line in (rows if rows is not None else _tail(tp, "usage")):
            if '"usage"' not in line:
                continue
            try:
                o = json.loads(line)
            except json.JSONDecodeError:
                continue
            m = o.get("message") or {}
            if _real(o) and m.get("usage"):
                u = m["usage"]
    except OSError:
        return 0
    if not u:
        return 0
    return u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)


def section_open(path, header):
    """Number of `- [ ]` in section `## header` (for the inbox — "New"); header=None — in the whole file."""
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        return 0
    if header:
        m = re.search(rf"(?ms)^## {header}\s*$(.*?)(?=^## |\Z)", text)
        text = m.group(1) if m else ""
    return len(re.findall(r"(?m)^- \[ \]", text))


def _find(agent_dir, names, globs=()):
    for n in names:
        p = os.path.join(agent_dir, n)
        if os.path.exists(p):
            return p
    for g in globs:
        hits = sorted(glob.glob(os.path.join(agent_dir, g)))
        if hits:
            return hits[0]
    return None


def agent_todo_path(agent_dir, agent):
    base = agent[:-6] if agent.lower().endswith("-agent") else agent
    return _find(agent_dir, ["agent-TODO.md", f"{agent}-agent-TODO.md", f"{base}-agent-TODO.md"])


def human_todo_path(agent_dir, agent):
    """the file the human reads: template name first, the older <name>-<x>-TODO style where it already exists"""
    return (_find(agent_dir, ["human-TODO.md"], ["*-human-TODO.md"])
            or os.path.join(agent_dir, "human-TODO.md"))


def todo_open(agent_dir, agent):
    p = agent_todo_path(agent_dir, agent)
    if not p:
        return 0
    try:   # waiting notes (⏳/⏸) are not tasks
        lines = open(p, encoding="utf-8").read().splitlines()
    except OSError:
        return 0
    return sum(1 for l in lines if l.startswith("- [ ]") and "⏳" not in l and "⏸" not in l)


def _human(o):
    """A human's message: user without origin (task notifications have an origin), not a service row, not a tool result."""
    if o.get("type") != "user" or o.get("origin") or o.get("isMeta") or o.get("isCompactSummary"):
        return False
    c = (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content")
    return isinstance(c, str) or (isinstance(c, list) and c and all(isinstance(x, dict) and x.get("type") == "text" for x in c))


def pressure_reaped(tp, rows=None):
    """uuid of the notification "background task stopped for low memory" if it came AFTER the human's last message,
    else None. Shape (claude, stopCause memory_pressure): a type=user row with origin.kind "task-notification" whose
    text has "...low on memory...". The human wrote after it -> the alarm rule applies again."""
    if rows is None:
        sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
        from transcript_tail import lines
        rows = lines(tp, _human)
    hit = None
    for line in rows:
        if '"user"' not in line or '"tool_result"' in line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if _human(o):
            hit = None
        elif o.get("type") == "user" and (o.get("origin") or {}).get("kind") == "task-notification":
            c = (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content")
            if "low on memory" in (c if isinstance(c, str) else json.dumps(c)):
                hit = o.get("uuid") or "?"
    return hit


def tell_infra(agent, sid, mark):
    """Once per notification: a letter to the infra agent that the tab is left without an alarm because of low memory.
    CCM_INFRA_AGENT empty = nobody to tell."""
    who = conf("CCM_INFRA_AGENT", "")
    if not who:
        return
    mp = f"{STATE}/reap-{sid}"
    try:
        if open(mp).read() == mark:
            return
    except OSError:
        pass
    os.makedirs(STATE, exist_ok=True)
    open(mp, "w").write(mark)
    import subprocess
    post = os.environ.get("WORK_GUARD_POST") or os.path.join(scripts_dir(), "inbox_post.sh")
    try:
        subprocess.run([post, who,
                        f"work-guard: in tab {agent} [{sid[:8]}] Claude Code stopped a background task because of LOW MEMORY "
                        f"({time.strftime('%F %H:%M')}; cause memory_pressure). The agent does not restart the alarm (the harness forbids it), "
                        "so new letters will not wake this tab until the human writes in it. Look at the machine's memory (who is eating it)."],
                       capture_output=True, timeout=4)
    except Exception:
        pass


def _human_msgs(rows):
    """(epoch, text) of the human's messages in the live branch (not the same as _human — that one is a predicate for lines())"""
    import datetime as _d
    for line in rows or []:
        if '"user"' not in line or '"tool_result"' in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") != "user" or o.get("origin") or o.get("isMeta"):
            continue
        c = (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content")
        t = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text") if isinstance(c, list) else ""
        if not t or t.lstrip().startswith("<"):
            continue
        try:
            ts = _d.datetime.fromisoformat((o.get("timestamp") or "").replace("Z", "+00:00")).timestamp()
        except ValueError:
            ts = 0
        yield ts, t


def alarm_off(agent_dir, tp, live):
    """The human said "turn off the alarm" -> the guard doesn't demand it until the end of the day (a tab under a
    block on every stop had to either break the order or live under the block).
    Two ways: the human's message TODAY in the live branch ("turn off the alarm", "no alarm"), with no later
    "turn on / start the alarm"; or a file <agent folder>/.no-alarm modified today. -> reason or None."""
    today = time.strftime("%F")
    flag = os.path.join(agent_dir, ".no-alarm")
    try:
        if time.strftime("%F", time.localtime(os.path.getmtime(flag))) == today:
            return "flag .no-alarm (today)"
    except OSError:
        pass
    rows = live
    if rows is None:
        try:
            sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
            from transcript_tail import lines
            rows = lines(tp, lambda o: False)
        except Exception:
            return None
    state = None
    for line in rows or []:
        if '"user"' not in line or '"tool_result"' in line:
            continue
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if o.get("type") != "user" or o.get("origin") or o.get("isMeta"):
            continue
        c = (o.get("message") if isinstance(o.get("message"), dict) else {}).get("content")
        t = c if isinstance(c, str) else " ".join(x.get("text", "") for x in c if isinstance(x, dict) and x.get("type") == "text") if isinstance(c, list) else ""
        if not t or t.lstrip().startswith("<"):
            continue
        if ALARM_ON.search(t):
            state = None
        elif ALARM_OFF.search(t):
            state = o.get("timestamp") or ""
    if not state:
        return None
    try:   # "until the end of the day" by local time (the transcript has UTC)
        import datetime as _d
        day = _d.datetime.fromisoformat(state.replace("Z", "+00:00")).astimezone().strftime("%F")
    except ValueError:
        return None
    return f"{HUMAN} said to turn the alarm off" if day == today else None


def get_mode(agent):
    try:
        m = open(os.path.join(mode_dir(), agent), encoding="utf-8").read().split()[0]
        return m if m in MODES else "auto"
    except (OSError, IndexError):
        return "auto"


def set_mode(agent, m):
    os.makedirs(mode_dir(), exist_ok=True)
    tmp = os.path.join(mode_dir(), f".{agent}.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(m + "\n")
    os.replace(tmp, os.path.join(mode_dir(), agent))


def mode_from_words(agent, rows):
    """The human's words newer than the mode file switch the mode (the last phrase wins). -> the mode after that."""
    try:
        since = os.path.getmtime(os.path.join(mode_dir(), agent))
    except OSError:
        since = 0
    new = None
    for ts, t in _human_msgs(rows):
        if ts <= since or ts < time.time() - 86400:
            continue   # fresh only: an old "stop the alarm" from days ago must not become a permanent off
        if ALARM_ALWAYS.search(t):
            new = "always"
        elif ALARM_ONCE.search(t):
            new = "once"
        elif ALARM_OFF.search(t):
            new = "off"
        elif ALARM_ON.search(t):
            new = "auto"
    if new:
        set_mode(agent, new)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %T')} {agent} alarm mode -> {new} (the human's words)\n")
        return new
    return get_mode(agent)


def quiet_for(agent_dir, rows):
    """seconds since the last work: a change of inbox.md (a letter came / was closed) or a human message"""
    last = 0
    try:
        last = os.path.getmtime(os.path.join(agent_dir, "inbox.md"))
    except OSError:
        pass
    for ts, _ in _human_msgs(rows):
        last = max(last, ts)
    return time.time() - last


def waiter_alive(agent):
    """A live alarm: the pid from the marker OR any process `inbox_wait.sh <agent>`. There is one marker per agent and
    in the race "the old alarm exits - the new one starts" it could vanish (a block 8 s after the start)."""
    try:
        os.kill(int(open(f"{HOME}/.claude/inbox-wait/{agent}").read().strip()), 0)
        return True
    except (OSError, ValueError):
        pass
    if os.path.isdir("/proc"):
        for pid in os.listdir("/proc"):
            if not pid.isdigit():
                continue
            try:
                argv = open(f"/proc/{pid}/cmdline", "rb").read().split(b"\0")
            except OSError:
                continue
            for i, a in enumerate(argv[:-1]):
                if a.endswith(b"inbox_wait.sh") and argv[i + 1].decode("utf-8", "replace") == agent:
                    return True
        return False
    try:   # no /proc (macOS): look at the process list
        import subprocess
        out = subprocess.run(["ps", "-axo", "args="], capture_output=True, text=True, timeout=5).stdout
        return any(re.search(r"inbox_wait\.sh\s+" + re.escape(agent) + r"(\s|$)", l) for l in out.splitlines())
    except Exception:
        return False


def guard_names():
    """names in the guard file (config key CCM_WORK_GUARD_AGENTS = path to the file); None = guard off"""
    path = conf("CCM_WORK_GUARD_AGENTS", "")
    if not path:
        return None
    try:
        return {l.strip() for l in open(os.path.expanduser(path), encoding="utf-8") if l.strip() and not l.startswith("#")}
    except OSError:
        return None


def main():
    d = json.load(sys.stdin)
    sid = d.get("session_id") or ""
    try:
        agent_dir = open(f"{HOME}/.claude/agent-identity/{sid}").read().strip()
    except OSError:
        return
    agent = os.path.basename(agent_dir.rstrip("/"))
    allowed = guard_names()
    if not allowed:
        return
    try:   # the folder was renamed — the list may hold the old name from .aliases
        names = {agent} | {l.split("#")[0].strip() for l in open(os.path.join(agent_dir, ".aliases"), encoding="utf-8")}
    except OSError:
        names = {agent}
    if not names & allowed:
        return

    tp = d.get("transcript_path", "")
    try:
        sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
        from transcript_tail import live_branch
        lb = live_branch(tp)
    except Exception:
        lb = None
    if lb and lb["last_is_ghost"]:
        # a ghost of the old branch after /compact: don't block — let it stop, otherwise the guard keeps it alive
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %T')} {agent} [{sid[:8]}] GHOST (branch before the compaction) — not blocking\n")
        return
    live = lb["live"] if lb else None

    # Context: >= RECAP_AT tokens -> once per "filling" demand /recap; the harness compacts by itself, the agent keeps working.
    ctx = context_tokens(tp, live)
    rp = f"{STATE}/recap-{sid}"
    try:
        done_at = int(open(rp).read())
    except (OSError, ValueError):
        done_at = 0
    if done_at and 0 < ctx < done_at - 200_000:   # a compaction happened -> the next filling demands a recap again (0 = not measured)
        os.remove(rp)
        done_at = 0
        close_compact_asks(agent_dir, agent, sid)
    # Recap and compact are always a pair. An agent can't compact itself (/compact is the human's command), so on the
    # first stop AFTER the recap demand we put "type /compact" into the human TODO.
    np_ = f"{STATE}/compact-asked-{sid}"
    if done_at and not os.path.exists(np_):
        mt = human_todo_path(agent_dir, agent)
        try:
            with open(mt, "a", encoding="utf-8") as f:
                f.write(f"- [ ] type `/compact` in tab {agent} — recap done at {time.strftime('%H:%M')} (context {ctx // 1000}k) [{sid[:8]}]\n")
            open(np_, "w").write(str(ctx))
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%F %T')} {agent} [{sid[:8]}] recap -> '/compact' asked in {os.path.basename(mt)}\n")
        except OSError:
            pass
    if not done_at and os.path.exists(np_):
        os.remove(np_)
    if ctx >= RECAP_AT and not done_at:
        os.makedirs(STATE, exist_ok=True)
        open(rp, "w").write(str(ctx))
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %T')} {agent} [{sid[:8]}] context {ctx // 1000}k -> demanding a recap\n")
        print(json.dumps({"decision": "block", "reason":
            f"🧠 work-guard: context {ctx // 1000}k of ~1000k (<30% free). Do a recap now (Skill `recap`): save what you know, "
            f"put open loops into your TODO. Do NOT stop and do NOT ask {HUMAN} — the harness compacts the context by itself when "
            "needed, and you keep working through the queue."}, ensure_ascii=False))
        return

    inbox_new = section_open(os.path.join(agent_dir, "inbox.md"), SECTION_NEW)
    alive = waiter_alive(agent)
    reaped = None if alive else pressure_reaped(tp, live)
    todo_n = todo_open(agent_dir, agent)
    try:
        rows = live
        if rows is None:
            sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
            from transcript_tail import lines
            rows = lines(tp, lambda o: False)
        mode = mode_from_words(agent, rows)
    except Exception:
        rows, mode = None, "auto"
    off = None if alive else alarm_off(agent_dir, tp, live)
    if not alive and not off:
        if mode == "off":
            off = f"alarm mode off — only {HUMAN} wakes the tab"
        elif mode == "auto" and quiet_for(agent_dir, rows) >= auto_idle():
            off = f"mode auto: {auto_idle() // 60} min without letters or human messages — the alarm went out by itself"
    msg = last_assistant(tp, live)
    has_state = bool(STATE_RE.search(msg))
    wait_cmd = f"{os.path.join(scripts_dir(), 'inbox_wait.sh')} {agent} [--until HH:MM]"

    why = None
    if inbox_new:
        why = (f"your inbox has {inbox_new} unprocessed item(s) in \"New\". Read them, do them or move them to your TODO "
               "(scripts/inbox_done.sh) and keep working.")
    elif todo_n and not has_state:
        why = (f"your TODO has {todo_n} open item(s). Take the next runnable one and do it. "
               "You may stop only if everything left is blocked: then write as the LAST line "
               "\"STATE: waiting for <what/whom/until when>\" (or \"STATE: queue empty\"), mark the waiting items ⏳ in the TODO, "
               f"and start the alarm in the BACKGROUND: Bash run_in_background `{wait_cmd}` — it wakes you on a new letter or at the time.")
        if reaped:
            why = why[:why.index("and start the alarm")] + ("do NOT start the alarm — the harness stopped the background task "
                                                             "because of low memory and forbade restarting it.")
        elif off:
            why = why[:why.index("and start the alarm")] + f"do NOT start the alarm ({off})."
    elif reaped:
        tell_infra(agent, sid, reaped)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %T')} {agent} [{sid[:8]}] LOW MEMORY: the harness stopped the alarm — not demanding it\n")
    elif off:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %T')} {agent} [{sid[:8]}] ALARM OFF ({off}) — not demanding it\n")
    elif not alive:
        # with an empty queue too: without the alarm nobody delivers a new letter from the coordinator
        why = ("no alarm is running — without it a new letter will not wake you. Start it in the BACKGROUND "
               f"(Bash run_in_background): `{wait_cmd}`, "
               "last line \"STATE: waiting for ...\" / \"STATE: queue empty\", then finish.")
    if not why:
        _reset(sid)
        return

    os.makedirs(STATE, exist_ok=True)
    cnt_p = f"{STATE}/{sid}"
    try:
        cnt = int(open(cnt_p).read())
    except (OSError, ValueError):
        cnt = 0
    stamp = time.strftime("%F %T")
    if cnt >= MAX_BLOCKS:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{stamp} {agent} [{sid[:8]}] PASS after {cnt} blocks in a row: {why[:120]}\n")
        _reset(sid)
        return
    open(cnt_p, "w").write(str(cnt + 1))
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{stamp} {agent} [{sid[:8]}] block {cnt + 1}: {why[:120]}\n")
    print(json.dumps({"decision": "block", "reason": f"🔁 work-guard ({HUMAN}: agents don't stop with open tasks): " + why},
                     ensure_ascii=False))


def close_compact_asks(agent_dir, agent, sid):
    """After the compaction close this session's "type /compact" lines in the human TODO (they went stale there)."""
    mt = human_todo_path(agent_dir, agent)
    try:
        text = open(mt, encoding="utf-8").read()
    except OSError:
        return
    new = re.sub(rf"(?m)^- \[ \] (type `/compact`.*\[{re.escape(sid[:8])}\])$", r"- [x] \1 — compacted", text)
    if new != text:
        with open(mt, "w", encoding="utf-8") as f:
            f.write(new)


def _reset(sid):
    try:
        os.remove(f"{STATE}/{sid}")
    except OSError:
        pass


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        try:
            os.makedirs(os.path.dirname(LOG), exist_ok=True)
            with open(LOG, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%F %T')} ERR {e!r}\n")
        except OSError:
            pass
