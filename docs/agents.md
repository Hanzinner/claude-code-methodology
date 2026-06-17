# Agents and cross-agent dial

Two patterns this repo supports for multi-agent work:

1. **Sub-agents** — short-lived, spawned by the main agent for parallel or scoped work
2. **Named agents** — long-lived sessions registered in a shared registry, callable by name from any other session

These are different tools for different shapes of work.

## Sub-agents

Built into Claude Code via the `Agent` tool. The main agent spawns a sub-agent with a prompt, the sub-agent runs in its own context (no shared memory with the main), and returns a single message back.

Use sub-agents for:
- **Parallel research** — fan out N searches/lookups concurrently
- **Context isolation** — keep noisy results (large file reads, search dumps) out of the main context
- **Specialized roles** — code review, planning, exploration via the typed agents (`Explore`, `Plan`, `code-reviewer`, etc.)

Don't use sub-agents for:
- Tasks the main agent could just do (one search, one file read)
- Anything stateful — sub-agents don't remember each other or themselves across calls
- Throughput multiplication on what's already a quick task — the spawn overhead isn't free

There's no setup for sub-agents — they're a built-in tool. The framework here doesn't add to them.

## Named agents (cross-agent dial)

A persistent pattern. You have several long-lived Claude Code sessions (one per project, one per persona, one per topic), and you want them to be able to ask each other questions.

The mechanism is the **agent registry** — a JSON file at `$CLAUDE_METHODOLOGY_DIR/agent-registry.json` mapping a short name to a session ID.

### The flow

```
session A                         registry                       session B
   │                                 │                              │
   │  /register-as research          │                              │
   ├────────────────────────────────►│                              │
   │  {research: {sid: ..., ...}}    │                              │
   │                                 │                              │
   │                                 │      /register-as security   │
   │                                 │◄─────────────────────────────┤
   │                                 │  {security: {sid: ..., ...}} │
   │                                 │                              │
   │  /call-agent security "?"       │                              │
   ├────────────────────────────────►│                              │
   │                                 │      claude --resume <sid>   │
   │                                 ├─────────────────────────────►│
   │                                 │                              │ wakes,
   │                                 │                              │ answers,
   │                                 │                              │ dormant
   │                                 │◄─────────────────────────────┤
   │  answer                         │                              │
   │◄────────────────────────────────┤                              │
```

### Setup

In session A, register:
```
/register-as research
```

In session B:
```
/register-as security
```

Now from either session, dial the other:
```
/call-agent security "what alerts did we tune this week?"
```

### When to use

- **Domain knowledge a peer holds** — your "research" agent has accumulated context on a topic the "security" agent needs once. Cheaper to dial than to repeat the research.
- **Cross-checking** — get a second opinion from an agent with different context.
- **Distributed memory** — if your topics are large enough that one agent's memory would be unwieldy, split them and dial across.

### When NOT to use

- **Memory first.** If the answer is in shared memory, read it — dialing is expensive (cache miss on the target's full history).
- **Multi-round dialogue needed.** Cross-agent dial is one-shot. If you need back-and-forth, the user should switch sessions.
- **The agent could just figure it out.** Don't delegate from laziness.

### Cost

Each dial wakes the target session and runs a one-shot completion in its full context. That means:

- Cache miss on the target's history (it's been dormant)
- One full inference pass at the target's model
- The question and answer become permanent additions to the target's transcript

A dial against a session with 200k tokens of history is not free. Treat dials like phone calls: have your question ready, ask one thing, hang up.

### Identity prefix

The `call-agent` script prefixes every dialed message with `[from agent: <caller-name>]` (resolved from the registry by the caller's session ID). The target sees it's a cross-agent dial — not the human directly — and answers peer-to-peer rather than re-asking what the user wants.

### Caveats

- One dial per target at a time. Parallel dials abort.
- A bad response can't be corrected in real time — you got it, move on.
- If the target session has been compacted heavily, the cache miss is bigger.

## Choosing between sub-agents and named agents

| Question | Sub-agent | Named agent |
|----------|-----------|-------------|
| One-shot question, no state needed? | Sub-agent | — |
| Need 5 parallel searches? | Sub-agent | — |
| Want to ask a session that's been accumulating context for weeks? | — | Named agent |
| Want isolation (sub-agent shouldn't see your context)? | Sub-agent | — |
| Want continuity (peer who remembers prior conversations)? | — | Named agent |
| Need it to remember the question after answering? | — | Named agent |

If you're not sure, default to a sub-agent. It's cheaper and the failure mode is "had to re-ask", not "stale state corrupted the answer".
