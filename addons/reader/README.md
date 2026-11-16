# reader - read the agents' documents in a browser

Agents write long Markdown: reports, plans, research notes. A terminal is a poor place to read them, and the human often
reads on a phone or a tablet, away from the machine. This add-on is a small document reader for the workspace: one
Python file (standard library only) serving one HTML page (`reader.html`, a bundled Markdown renderer, no build step).

What the page does: paged or scrolling layout, three themes, a table of contents from the headings, adjustable font,
size, line width and spacing, footnotes, `.fb2` books. On the left: search by file name and by text inside the files,
the folder tree, recent and favourite files. Settings and the last opened file are kept on the server, so a phone and a
laptop show the same thing. The interface is in Ukrainian.

```
python3 addons/reader/reader-server.py                          # http://127.0.0.1:8001/  (root = CCM_WORKSPACE)
python3 addons/reader/reader-server.py --root ~/notes --port 9000
python3 addons/reader/reader-check.py                           # rc 0 = it answers
```

## How an agent hands a document to the human

* **A link to one file:** `http://<reader address>/?open=<path under the workspace, URL-encoded>` opens exactly that file.
* **A folder for the human:** set `CCM_READER_SHARED` (e.g. `shared`) and agents put a `.md` there; the reader lists it
  in a section at the top, newest first. The human can hide an entry from the list; the file stays.

Questions that need an answer do not go there: typing an answer on a phone into a reader is the wrong channel. The
reader is for what the human only reads.

## Safety

* It only shows files: it changes nothing in the workspace. It writes two small state files (last opened file,
  settings) under `CCM_READER_STATE` (default `~/.claude/reader`), never in the workspace.
* Only `.md .markdown .txt .fb2` are served. Every path is resolved, symlinks included, and must stay under the root.
  Dot-files and dot-folders (`.env`, `.git`), `node_modules`, `__pycache__` and the folders in `CCM_READER_HIDE` are
  never listed, searched or served.
* **There is no password.** By default it listens on `127.0.0.1` - this machine only. `CCM_READER_BIND=0.0.0.0` makes
  every document readable by anyone who reaches the address, and the server prints a warning when it starts like that.
  To read from another device, put a reverse proxy that asks for a login in front of it, or use an SSH tunnel
  (`ssh -L 8001:127.0.0.1:8001 <machine>`).

## Settings (methodology.conf; an environment variable with the same name wins)

| key | default | what |
|---|---|---|
| `CCM_WORKSPACE` | `~/claude-projects` | the root it serves |
| `CCM_READER_PORT` | `8001` | port |
| `CCM_READER_BIND` | `127.0.0.1` | address it listens on (see Safety) |
| `CCM_READER_SHARED` | empty | folder under the root for documents agents leave for the human; empty = no such section |
| `CCM_READER_HIDE` | empty | folder names hidden everywhere, comma-separated |
| `CCM_READER_SKIP` | empty | file-name patterns left out of search, e.g. `briefing.md,inbox.md,*-TODO.md` (agents' own working files) |
| `CCM_READER_STATE` | `~/.claude/reader` | where the last opened file and the settings are kept |

## Install

`install.sh --with-reader` copies this folder to `<claude dir>/addons/reader/`, starts the reader in the background
(log: `~/.claude/logs/reader.log`), adds an `@reboot` line to its crontab block so it starts again after a reboot, and
merges one supervisor check ("Reader answers"). No root. With `--no-cron` nothing is started or scheduled; the
installer prints the command. `check-install.py` says whether it answers.

To remove: delete the `@reboot ... reader-server.py` line (it is inside the methodology block; re-running install.sh
without `--with-reader` rewrites the block without it), stop the process, delete the folder.

## Test

`tests/reader-test.py`: a temp root and state dir, the server on a free localhost port. It checks what is served, what
never is (outside the root, `../`, a symlink out, `.env`, dot-files, `.git`, hidden folders, other extensions), search,
the agents' section on and off, the state files, and the real command line (default address, the no-password warning,
a missing root).

The Markdown renderer bundled in `reader.html` is marked (MIT, copyright header kept in the file).
