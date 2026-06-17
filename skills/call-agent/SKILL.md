---
name: call-agent
description: Ask another registered agent a question in their own context — their session resumes, answers, then returns to dormant. Invoked when the user says "/call-agent <name> <question>", "ask <name>", or when this agent needs knowledge another agent owns.
---

# call-agent

Cross-agent live dial. Takes a registered agent from `$CLAUDE_METHODOLOGY_DIR/agent-registry.json`, wakes their session via `claude --resume`, sends the question, returns the response.

## How to invoke

```bash
"$CLAUDE_METHODOLOGY_DIR/scripts/call_agent.sh" <name> "<full-sentence question>"
```

Examples:
- `call_agent.sh security "what alerts did we tune this week?"`
- `call_agent.sh research "what's the latest on topic X?"`

## Parameters

- `<name>` — exact name from the registry (lowercase). If unsure, inspect the registry:
  ```bash
  python3 -m json.tool < "$CLAUDE_METHODOLOGY_DIR/agent-registry.json"
  ```
- `<question>` — a single, specific message in quotes. One-shot — no multi-round dialogue.

## How it works under the hood

1. The script reads the target's sid from the registry.
2. It runs `claude -p "<question>" --resume <sid> --output-format text` in the target's cwd.
3. The target session wakes in full context (prior messages come back via prompt cache), answers, then becomes dormant.
4. The script prints the response text.
5. The question + answer are permanently appended to the target's transcript — that's normal.

## Protocol — MANDATORY before any dial

1. **Memory first.** Read relevant files in `memory/` (project files, episodic for the current month). If the answer is there, use it — don't dial. Free.

2. **If memory is stale / missing — dial with a PRECISE question.** Not "what's new with you" — concrete: "list new skills I've picked up since the last recap, one line each". One shot = one specific answer.

3. **Prefer the smaller agent.** Bigger agents (longer history, more cache misses) cost more. If a smaller agent can answer, dial them.

## When NOT to dial

- The answer is in shared memory — read it.
- A multi-round dialogue is needed — wrong tool. Tell the user to switch to that session.
- The current agent can reason this out themselves — don't delegate from laziness.

## Identity prefix

The script auto-prefixes the message with `[from agent: <your-name>]` (resolved from the registry by current session_id). The target sees it's a cross-agent dial, not the human directly, and responds peer-to-peer.

## Known caveats

- One dial per target at a time — parallel dials abort.
- A bad response in real-time can't be corrected — you get it and move on.
- Cache stays warm while the target is recently active; otherwise the first dial is slower.

## After

Hand the response to the user directly (or weave it into your own answer if it was for your task). Attribute the source ("security says: …").
