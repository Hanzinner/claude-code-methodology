# Agents — registry

> The source of truth is the folders with a `briefing.md` under `Agents/`, not this table and not memory.
> This table is for humans: what exists and what each one owns. To bring an agent up, write its name as the
> first message of a chat; the agent reads `Agents/<name>/briefing.md` and works as that agent.
> Ownership boundaries matter more than descriptions: two agents owning one file is how work gets lost.

| Agent | Owns (files, domains) | Doesn't touch | Briefing |
|---|---|---|---|
| example-agent | `Project-Example/`, its roadmap | shared mechanisms, other projects' files | `Agents/_example-agent/briefing.md` |
