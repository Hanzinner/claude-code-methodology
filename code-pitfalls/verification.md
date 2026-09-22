# verification

### "Live / works" proven by configuration, not execution
- **Symptom:** a mechanism was believed live for weeks and never ran once; "sent" — and there's no message; "the agents are working" — they've been idle for hours.
- **Why:** the evidence was intent or a cheap signal: `crontab -l`, a file on disk, a `✓` from the script, "the code looks right", a status file last written hours ago, a manual run from your own shell instead of cron's environment.
- **Right way:** proof = a trace only the mechanism's own work could leave (a log line written by it, a marker, an injection seen in a real session, a tag, a fresh process in `ps`), placed next to the claim. No trace → it's a hypothesis, and say so.
- **Seen:** 15+ times across 6+ agents.

### The instrument measures what it can see, not what is
- **Symptom:** a gate reports 0 violations, or green, while the defect is right there.
- **Why:** the checker's own coverage has holes — a list missing an entry, a macro hiding a call site, a fixed timeout shorter than the event.
- **Right way:** own the instrument: ask "what can this not see, by construction?" before trusting its number. Test it with an input that *must* fail.
- **Seen:** 4 different ways in one day, on one gate.
