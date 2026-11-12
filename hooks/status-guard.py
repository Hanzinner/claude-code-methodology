#!/usr/bin/env python3
"""status-guard - a coordinator reports a story's state or blockers only with a check in the SAME turn.
Why: a coordinator told the human a story's state three times from memory - "code ready", then "not started", then "nobody
started" - while the code had been committed for days; a blocker lived as a sentence ("until prod") and the story stood
still for 5 days. The state of work is computed from sources (story_status.py, blockers.py, git log), never recalled.
Only the agents listed in config CCM_STATUS_GUARD_AGENTS (comma-separated folder names, e.g. "Alpha-HQ,Beta-HQ") are
checked; an empty list = the guard is off. The agent is identified through ~/.claude/agent-identity/<session_id>.

A turn = everything after the last human message. Two branches:
  BLOCK (Stop, blocking) - the final text (without quotes and code) has a sentence with a story code (S68, E4.S68; or the code
    in the two sentences before: "- S68 ... / Code not started") that states a state ("done", "not started", "nobody started",
    "in progress", "closed") OR tells the human "waiting on you / it all rests on you / no work left", and in the turn there was
    NO run of a source: story_status.py / blockers.py / git log|show. The agent's own TODO/inbox and the roadmap are NOT a
    source of state (a plan is not a fact about code). One block per stop (stop_hook_active).
  FLAG - "waiting for <human> / before prod / we'll do it later" without a blocker number B<n> in the sentence -> a hint on the
    next prompt: "register a blocker with blocker_add.sh, or name the number".
Flags: ~/.claude/status-guard-flags/<session_id> (finished hint text). Log: ~/.claude/status-guard.log.
Config: CCM_STATUS_GUARD_AGENTS (NEW, default empty = off), CCM_HUMAN_NAME, CCM_LANG_EXTRA ("uk" adds the Ukrainian lists)."""
import importlib.util, json, os, re, sys, time

HERE = os.path.dirname(os.path.realpath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "lib"))
sys.path.insert(0, os.path.join(HERE, "..", "scripts"))
from ccm_conf import conf  # noqa: E402


def _load(name, fname):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fname))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


clean = _load("pause_guard_mod", "pause-guard.py").clean      # quotes, code, `>` lines are not the agent's own text
is_prompt = _load("proof_guard_mod", "proof-guard.py").is_prompt   # one definition of "a human message" for all Stop gates

HOME = os.path.expanduser("~")
UK = "uk" in conf("CCM_LANG_EXTRA", "")
WHO = re.escape(conf("CCM_HUMAN_NAME", "the user"))
AGENTS = {a.strip() for a in conf("CCM_STATUS_GUARD_AGENTS", "").split(",") if a.strip()}
LOG = f"{HOME}/.claude/status-guard.log"


def rx(en, uk=""):
    return re.compile("|".join(f"(?:{p})" for p in (en, uk if UK else "") if p), re.I)


STORY = re.compile(r"\b(?:E\d+\.)?S\d{1,3}\b")
# "Done when ..." is a condition, not a state
STATE = rx(r"(?<!\w)(done|finished|completed|implemented|shipped|merged|closed|not (?:yet )?(?:started|done|implemented)|"
           r"(?:has|have|hasn't|haven't) (?:not )?(?:been )?started|(?:nobody|no one) (?:has |is |was )?(?:started|working|picked)\w*|"
           r"in progress|in the works|code is ready)(?!\w)(?!,?\s+(?:when|once|if|after|before|unless))",
          r"(?<!\w)(готов[оаіий]|зроблен[оаі]|не почат[оаі]|не почина\w*|ніхто не почина\w*|ніхто не бра\w*|"
          r"в роботі|у роботі|закрит[оаі]|не зроблен\w*)(?!\w)(?!,?\s+коли)")
ON_HUMAN = rx(r"(?<!\w)(?:waiting (?:for|on) you|blocked on you|depends on you|stuck on you|rests? on you|"
              r"(?:it(?:'s| is)|everything(?: is)?|all(?: of it)?(?: is)?) (?:up to|on) you|only you can|"
              r"there(?:'s| is) no (?:work|more work)(?: left| available)?|no work (?:left|available))(?!\w)",
              r"(?<!\w)(чека[єю]\w* (?:на )?тебе|впира\w* в тебе|(?:усе|все) на тобі|нема(?:є)? роботи|"
              r"(?:усе|все) за тобою|лише ти можеш)(?!\w)")
WAIT_WORDS = rx(rf"(?<!\w)((?:we(?:'re| are) |i(?:'m| am) )?waiting (?:for|on) {WHO}|before prod(?:uction)?|before (?:the )?release|"
                r"(?:we(?:'ll| will)|let's|i(?:'ll| will)) (?:do|enable|connect|add|ship) (?:it|this|that) later|"
                r"(?:this|that|it) can wait)(?!\w)",
                r"(?<!\w)(чекаємо (?:на )?Марка|чекаю (?:на )?Марка|перед Prod|перед продом|"
                r"(?:це|зробимо|ввімкнемо|увімкнемо|підключимо) потім)(?!\w)")
# A source = output that looks at the code and commits (story_status.py) or at the blocker register (blockers.py), or git log/show.
# NOT the agent's own TODO/inbox and NOT the roadmap: counting roadmap lines is how "code not started" was said about code
# that had been committed for days.
SOURCE = re.compile(r"story_status|blockers\.py|git\s+(?:-C\s+\S+\s+)?(?:log|show)\b", re.I)


def turn(tp):
    from transcript_tail import lines as tail_lines
    text, sourced = "", False
    for line in tail_lines(tp, is_prompt):
        try:
            o = json.loads(line)
        except ValueError:
            continue
        if is_prompt(o):
            text, sourced = "", False
            continue
        if o.get("type") != "assistant":
            continue
        for x in (o.get("message") or {}).get("content") or []:
            if not isinstance(x, dict):
                continue
            if x.get("type") == "text":
                text = x.get("text", "")
            elif x.get("type") == "tool_use" and SOURCE.search(json.dumps(x.get("input") or {}, ensure_ascii=False)):
                sourced = True
    return text, sourced


def sentences(t):
    return [s for s in re.split(r"(?<=[.!?;])\s+|\n+", t) if s.strip()]


def verdict(text, sourced):
    """-> (block_reason | None, flag_reason | None)"""
    t = clean(text)
    block = None
    if not sourced:
        ss = sentences(t)
        for k, s in enumerate(ss):
            st = STORY.search(s) or STORY.search(" ".join(ss[max(0, k - 2):k]))
            m = STATE.search(s) if st else None
            om = ON_HUMAN.search(s)
            if m or om:
                block = f"\"{(m or om).group(0)}\"" + (f" about {st.group(0)}" if st and m else "")
                break
    flag = None
    for s in sentences(t):
        w = WAIT_WORDS.search(s)
        if w and not re.search(r"\bB\d+\b", s):
            flag = w.group(0)
            break
    return block, flag


def agent_of(sid):
    try:
        return os.path.basename(open(f"{HOME}/.claude/agent-identity/{sid}").read().strip().rstrip("/"))
    except OSError:
        return ""


def hit(sid, agent, what):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%F %T')} [{sid[:8]}] {agent} {what}\n")


def main():
    raw = sys.stdin.read()
    if not raw.strip() or not AGENTS:
        return
    d = json.loads(raw)
    sid = d.get("session_id") or ""
    agent = agent_of(sid)
    if agent not in AGENTS:
        return
    text, sourced = turn(d.get("transcript_path", ""))
    block, flag = verdict(text, sourced)
    if block and not d.get("stop_hook_active"):
        hit(sid, agent, f"BLOCK {block}")
        print(json.dumps({"decision": "block", "reason":
              f"[status-guard] You are stating a state - {block} - but did not look at a source in this turn. Run "
              "`story_status.py <project> <S-code>` (for \"waiting on you\": `blockers.py list <project>`) and rewrite the "
              "sentence from its output; without the output, do not assert it. State of work is computed, not recalled."}))
        return
    if flag:
        os.makedirs(f"{HOME}/.claude/status-guard-flags", exist_ok=True)
        with open(f"{HOME}/.claude/status-guard-flags/{sid}", "w", encoding="utf-8") as f:
            f.write(f"[status-guard] Last turn you wrote \"{flag[:120]}\" without a blocker number. Whatever is waiting, "
                    "register it: scripts/blocker_add.sh <project> \"<what>\" \"<who clears it>\" \"<check command | manual>\" and put "
                    "B<n> in the story line; or name an existing number (blockers.py list <project>). "
                    "\"Waiting / later / before prod\" without B<n> is how a story stands still for days.")
        hit(sid, agent, f"FLAG \"{flag}\"")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass
