# Handing files and visuals to a human

An agent finishes a document, a chart, a rendered page. The human is on another machine, often on a phone.
How does it get there? In a swarm this has to be **written down in one place that agents actually open**, or each agent
re-invents a channel — and the inventing is where the damage happens.

## Why this file exists

Knowledge about sharing was spread over three memory files, and the memory-index triggers were named after
technologies ("file sync", "reader"), not after the task ("hand a file over"). An agent that needed to give a human a
document had no entrance that matched its goal. Result in one day: **three working channels, none used**, four blocked
attempts to bring up a fourth, and a non-technical person panicking over a work deadline.

The rule that came out of it: sharing knowledge must **sit where the agent looks for it** ("send / show / hand over a
file" → this page first), not in a file nobody opens. The trigger in the index is phrased in the agent's words.

## Do not build a channel

- **Do not start your own server** (`python -m http.server`, ssh/scp to the human's laptop, reading another service's
  unit file). The permission classifier blocks these, and a "yes, allowed" typed in chat does not lift the block; only a
  rule in settings does.
- **Read a classifier block as "my model of the channel is wrong — stop and think"**, not "try a variant". Trying
  variants after a block means you do not know what is open. What is open is below.
- **Do not publish to hosted-page tools that sit under someone else's account.** A preview published that way shows the
  human's private work in a collaborator's gallery, and the human cannot delete it.
- **Ports of the existing services are taken.** Your server would not start even without the classifier.

## Channels

Names here are generic; the concrete host, port and folder are per-installation. None of the services below ships in
this repo — you wire them to whatever your setup has (see "What ships").

| Need | Channel |
|---|---|
| A document to work with (.docx, .pdf, .xlsx) | **a shared folder** that a sync tool mirrors to the human's machine |
| A visual to look at (HTML, chart, screenshot, prototype) | **a local preview server** serving one directory; the agent copies the file in and gives a short URL |
| Markdown or an ebook to read | **a document reader**; drop the file into the shared folder, or give a deep link to it |
| The human is in a hurry, in the editor, nothing else works | **the editor's "Download" action** on a file in the workspace root |
| Showing something to a third party | not a swarm channel; ask the human |

**Shared folder.** `cp` the file in and fix its ownership to the user the sync process runs as. A file owned by root
hangs the sync at 99%. This is the best channel for documents: the file simply appears in a folder on the human's
machine.

**Preview server.** Copy the file in, give a URL. Two traps: the HTML needs `<meta charset="utf-8">` or non-ASCII text
renders as garbage; and a long full URL gets doubled by the browser's autocomplete into a 404, so give the shortest
working form. Check the service by the address it actually listens on: a service bound to one interface returns
"connection refused" on loopback, and the agent that read that as "the channel is dead" lost an hour. (The binding later
changed the other way round, which is the point: see "Verify before you use it".)

**Document reader** (`./install.sh --with-reader`, see [`addons/reader/README.md`](../addons/reader/README.md)). A deep link of the form
`http://<host>/?open=<url-encoded path under the root>` is the best way to give someone something to read: one click.
It is for reading only.

**Download fallback.** Put the file in the workspace root and tell the human: right click in the file panel, Download.
The root is under an auto-commit cron, so the file gets committed; remove it afterwards (move to a trash folder).

## Questions never go through the reader

Anything that needs an **answer** (a question, an A/B choice, "keep or close", "send me the IP") goes into the chat as
plain numbered text. Typing an answer into a reading app on a phone is a bad channel, and the human said so. The
reader carries only what the human reads.

## Links to a human: names, not numbers

Never put a numeric URL in a link meant for a person. The same service has different numeric addresses from different
machines, so a link that works for the agent breaks on the human's second laptop. Give it a **name** that resolves
correctly everywhere (hosts file on each machine plus a reverse proxy). Numeric addresses stay as a debugging fallback
only. A new service gets its name from the infrastructure agent.

Give a **full direct URL to the file**, not the listing page plus a file name in backticks — the human asked "why not
the full link". And give a path inside the repo as a clickable `[name](path)`, not in backticks: `hooks/link-guard.py`
in this repo detects paths written the second way and shows the agent a ready-made link on the next turn.

## Verify before you use it

Status of services is state that changes, so this page must not claim "X is
running". Before **using** a channel — a sync folder, a port, a service — run one command that proves it is alive, and
before **declaring one dead**, check that you knocked on the right address. Real cases:

- A default sync folder that the sync tool creates on first start looked like a channel (right name), held nothing and
  synced nothing. An agent trusted the name and put a file there. The real channel had a different name. The folder was
  removed; the lesson is that a name is not evidence, the sync tool's own config is.
- A preview service was verified on loopback and "failed"; later, after a network change, the opposite held: loopback
  answered and the old interface address hung. Run checks **with a timeout** (`curl -m 5`), or the command itself hangs
  for two minutes.
- A shared folder stopped syncing from the laptop three times in one day while the server side reported "idle, nothing
  needed" — the laptop had not scanned and announced the new files. Workaround: pull the files over ssh. The cause was
  not found; the entry stays as a known gap.
- A "don't use ssh/scp to the laptop" rule was read by an agent as "never touch the laptop", and it sent the human to
  drag a file by hand. The rule is about **delivering** files; reading and fetching files from the laptop is allowed,
  changing anything there is not without the human's yes.

## Hygiene on handoff

- A document for a team or a client is **anonymized by default**: no names, account identifiers, tenant or IP.
- **Secrets never go to the workspace** (it is under an auto-commit cron; a token lasted minutes before it was
  committed). Keep them in a config directory outside the repo.
- **Do not hand over what you have not looked at.** For .docx and PDF, render to an image first
  ([`docx-playbook.md`](docx-playbook.md)). Slop handed over is work pushed onto the human.

## What ships

| Piece | In this repo? |
|---|---|
| Clickable-link detector | yes, `hooks/link-guard.py` |
| Document-generation rules | yes, [`docx-playbook.md`](docx-playbook.md) |
| Document reader | yes, `addons/reader/` (`--with-reader`) |
| Shared-folder sync, preview server, name resolution (hosts file, reverse proxy) | not in this repo |
| The "hand a file over" trigger in the memory index | not shipped as such; add a line in your `MEMORY.md` phrased as the task |

Agents append dated, **confirmed** notes at the bottom of their copy of this page (new channel, new trap, a channel
died). Do not rewrite older notes: the older fact may still hold in another context.
