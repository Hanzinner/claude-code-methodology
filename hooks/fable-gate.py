#!/usr/bin/env python3
"""fable-gate - PreToolUse on Agent and Workflow: a subagent with no EXPLICIT model, or on a forbidden model -> deny
with a hint.

Why: an expensive model costs ~2x a cheaper one, and a subagent without a `model` parameter inherits the main
session's model - in a tab on the expensive model every verifier and writer of a workflow ran on it too. Rule: always
pass the model explicitly (default: CCM_SUBAGENT_DEFAULT_MODEL; critical review may use a stronger one).
Agent: deny if `model` is missing or matches a forbidden name (substring, case-insensitive).
Workflow: deny if the script has agent(...) calls and no `model:` at all, or a `model:` naming a forbidden model;
a named workflow without a script (its models are not visible) passes.
Config: CCM_FORBIDDEN_SUBAGENT_MODELS (comma-separated; EMPTY = the gate is off), CCM_SUBAGENT_DEFAULT_MODEL.
Fail-open under hook-safe.sh. Log: ~/.claude/fable-gate.log"""
import json, os, re, sys, time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

LOG = os.path.expanduser("~/.claude/fable-gate.log")
FORBIDDEN = [m.strip().lower() for m in conf("CCM_FORBIDDEN_SUBAGENT_MODELS", "").split(",") if m.strip()]
DEFAULT = conf("CCM_SUBAGENT_DEFAULT_MODEL", "sonnet")


def hint():
    return (f"Always pass the model explicitly: model: \"{DEFAULT}\" (a stronger one only for critical review), never "
            f"one of: {', '.join(FORBIDDEN)}. Tell {conf('CCM_HUMAN_NAME')} in one line which model you launch on.")


def bad_name(text):
    t = text.lower()
    return next((f for f in FORBIDDEN if f in t), None)


def verdict(tool, inp):
    if tool == "Agent":
        m = str(inp.get("model") or "")
        if not m:
            return "Agent without a model parameter - the subagent inherits the tab's model (may be a forbidden one)"
        if bad_name(m):
            return f"Agent on model \"{m}\""
        return None
    if tool == "Workflow":
        src = str(inp.get("script") or "")
        if not src:
            return None
        for mm in re.finditer(r"model\s*:\s*['\"`]([^'\"`]*)", src, re.I):
            if bad_name(mm.group(1)):
                return f"the workflow script has model: {mm.group(1)}"
        if re.search(r"\bagent\s*\(", src) and not re.search(r"\bmodel\s*:", src):
            return "the workflow script calls agent(...) with no model: at all - they inherit the tab's model"
    return None


def main():
    if not FORBIDDEN:
        return                                  # gate off
    raw = sys.stdin.read()
    if not raw.strip():
        return
    d = json.loads(raw)
    tool = d.get("tool_name") or ""
    why = verdict(tool, d.get("tool_input") or {})
    if not why:
        return
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%F %T')} [{(d.get('session_id') or '')[:8]}] DENY {tool}: {why}\n")
    except OSError:
        pass
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                             "permissionDecisionReason": f"⛔ fable-gate: {why}. {hint()}"}},
                     ensure_ascii=False))


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback; traceback.print_exc(); sys.exit(1)
