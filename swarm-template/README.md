# swarm-template

Empty shared files for running several named agents. Copy this folder's contents to the root of the
workspace your agents share. Nothing here is filled in: the structure is ours, the content is yours.

| File | What it is | Who writes |
|---|---|---|
| `MISTAKES.md` | One journal for every agent's mistakes, so a repeat becomes visible and gets a mechanism | any agent, right after fixing |
| `AGENTS.md` | Registry: which agents exist, what each owns, where its briefing is | whoever creates an agent |
| `LIBRARY.md` | Catalog of every shared mechanism and system document, one machine-readable line each | whoever adds or removes a mechanism |
| `Agents/<name>/` | One folder per agent: briefing, inbox, its own todo, the human's todo for it | the agent (inbox: other agents, through `multi-agent/inbox-post.sh` only) |

How the pieces connect is in [`docs/multi-agent.md`](../docs/multi-agent.md); the rules agents follow are in
[`docs/coding-standard.md`](../docs/coding-standard.md) and [`docs/project-work.md`](../docs/project-work.md).
