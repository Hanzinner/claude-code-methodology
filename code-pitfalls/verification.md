# verification

### "Live / works" proven by configuration, not execution
- **Symptom:** a mechanism was believed live for weeks and never ran once; "sent" — and there's no message; "the agents are working" — they've been idle for hours.
- **Why:** the evidence was intent or a cheap signal: `crontab -l`, a file on disk, a `✓` from the script, "the code looks right", a status file last written hours ago, a manual run from your own shell instead of cron's environment.
- **Right way:** proof = a trace only the mechanism's own work could leave (a log line written by it, a marker, an injection seen in a real session, a tag, a fresh process in `ps`), placed next to the claim. No trace → it's a hypothesis, and say so.
- **Seen:** 15+ times across 6+ agents.

### Environment state or a test artifact taken for proof
- **Symptom:** the "first live run" turned out to be your own test; a "live subscription" was a leftover process from an old session.
- **Why:** positive environment signals (a file grew, a process exists, a flag is there) have other causes; the artifact has no provenance (who/when/from where).
- **Right way:** in a mechanism test check ITS OWN trace first (log/marker), effects second; proof = finding + provenance (timestamp, session id); clean up test artifacts in the same turn as the test.
- **Seen:** 2 times.

### A monitor/logger accepted on its start marker
- **Symptom:** the logger is "Running", the `=== START ===` line is there — and two days of data are zero; the freeze it was set up to catch passed unseen.
- **Why:** START is written before the loop; the loop failed every time and a `catch {}` swallowed the error.
- **Right way:** accept a monitor/logger/cron only after seeing ≥2 lines of DATA with the right step; a metric error is a visible marker in the field, not silence.
- **Seen:** 2 times (a repeat of the 2026-08 version).

### An instrument silently guesses instead of saying "I'm broken"
- **Symptom:** a test rejects working code (a "1024×768" screen instead of the real one); a watchdog says "all fine" though it can't see the object; a logger with no data.
- **Why:** a silent fallback on a verdict parameter (`if m else (1024,768)`, `if power is None: return`, `catch {}` over the whole block); the returned delta of the instrument's output was thrown away without printing.
- **Right way:** in measuring code no `or`/`else` defaults on verdict parameters — don't know → `assert`/crash. On failure the instrument prints the log tail, not a verdict. First question when an instrument is silent: "would my instrument have waited if everything were fine?"
- **Seen:** 3 times.

### The instrument measures what it can see, not what is
- **Symptom:** a gate reports 0 violations, or green, while the defect is right there.
- **Why:** the checker's own coverage has holes — a list missing an entry, a macro hiding a call site, a fixed timeout shorter than the event. Whitelists are incomplete; a grep for `crate::fs::` misses a bare `fs::` after a `use`; a macro (`println!`) expands into a call that isn't in the text.
- **Right way:** own the instrument: ask "what can this not see, by construction?" before trusting its number. Test it with an input that *must* fail (plant a violation → exit ≠ 0). Invert the default (list the finite "forbidden" set, the rest is covered by itself). Print the debt on every run instead of keeping it a quiet zero.
- **Also — load tests count attempts, not accepted actions:** a load of "200 bids/min per lot" counted ATTEMPTS; the product's business limit (a cap for a new account) turned everything after 66 accepted into cheap 409s — the server never got the claimed load. Measure ACCEPTED actions at the target and gate the instrument on "accepted ≥ target, otherwise CANNOT". Suspect: the same number across runs of different length.
- **Seen:** 4 different ways in one day, on one gate.

### A test on a stale artifact or an old log
- **Symptom:** "bug reproduces 2/2" — on an image 263 h older than the code; "reproduced three times" — read the same log three times.
- **Why:** instruments take the build artifact blindly; the build was started from the wrong directory and didn't run; the instrument refused to start and the log of the previous run was read.
- **Right way:** the instrument itself compares the artifact's mtime with the freshest source and refuses on a stale one; build by absolute path plus `stat` of the artifact; when reading a log, check its time against the run.
- **Seen:** 3 times.

### "Proven by reading the code" — proven only about the code you read
- **Symptom:** a "fixed" bug reproduced in a live run through another path; a command reports success on a truncated file.
- **Why:** reading proves the absence of the bug in THIS place and says nothing about other paths to the same harm.
- **Right way:** "verified by reading" is a separate, weaker class of evidence; the task stays open until the failure scenario has been run live (see [concurrency.md](concurrency.md) — one control point).
- **Seen:** once.

### A discrepancy between two channels taken from two different runs
- **Symptom:** "bug: the window list is blind" — the list from one run, the screenshot from another.
- **Why:** for "A contradicts B" simultaneity of measurements is a condition of validity; different runs = different system states.
- **Right way:** both measurements in one run, side by side (`ser:wins;shot`); before carrying a discrepancy further ask "is this one run or two?".
- **Seen:** once.

### The test input can't change anything; the measurement catches the extraneous
- **Symptom:** "didn't change" / "regression" — and the test proved nothing.
- **Why:** the test colour = the system's default colour; a wider checksum rectangle captured the clock and the version string; the test itself opened and closed a window "to make it repaint" — doing the system's job by hand.
- **Right way:** before "didn't change", check that the input is capable of changing something; no extraneous action between the action and the measurement; the measured frame contains no variable elements.
- **Seen:** once.

### Code the test never executed
- **Symptom:** a broken pattern lived in a script for 11 days; green test runs.
- **Why:** the test runs were empty (heartbeat) — execution never reached the line with the payload.
- **Right way:** the test must PASS THROUGH the line you are checking; after a deploy, an open loop "check the first live run".
- **Seen:** once.

### Visual check done blind
- **Symptom:** "screenshots of the live OS are proof" — and the screenshot shows mud instead of the sky; an icon in a tile's corner; a .docx with ragged words; a desktop drawn into an old rectangle under "OK -- live at 1920x1080".
- **Why:** the screenshot was taken for a tick-box and nobody looked; to a machine "right" and "crooked" look the same; the numbers measured the wrong thing.
- **Right way:** a report on visuals counts only with a description IN WORDS of what is visible on the artifact; judge the final look (stretched to full screen, in a row with others), not the thumbnail; documents — render to PNG (`soffice --headless --convert-to pdf` → `pdftoppm -png -r 110`) and look.
- **Seen:** 4 times.

### A detector verified on a different configuration than the one it catches
- **Symptom:** a detector silently failed to fire for a week in the real mode.
- **Why:** written and tested with one battery, while the main mode is two that discharge in sequence.
- **Right way:** accept a hardware detector only by running (or simulating) exactly the configuration it must catch.
- **Seen:** once.

### Channel silence ≠ a hang
- **Symptom:** "the kernel hangs on my code" — hours of hunting a deadlock in working code; a "hang" read off truncated serial output.
- **Why:** the instrument doesn't signal "not delivered": silence from non-delivery and silence from a hang are identical; the observation channel itself truncated the output.
- **Right way:** first find the command's echo (`[shell] <cmd>` is printed BEFORE execution): no echo = a delivery problem, not the code's; prove a "hang" with an independent signal (next stage, VM state); send a long diagnostic command first and alone.
- **Seen:** 2 times.

### A build failed with no error in the log
- **Symptom:** `exit status: 101`, `grep "^error"` = 0; a retry passes.
- **Why:** an internal compiler crash (here from overload) writes its reason to a file on disk, not to stdout.
- **Right way:** look at the FILES LEFT BEHIND (`git status --porcelain`, `ls -t | head`), not only the console; remove the crash file (see [git.md](git.md)).
- **Seen:** once.

### One cause out of several: a "flake", and a check narrower than the claim
- **Symptom:** everyone who found their cause of instability declared it THE cause; the symptom shrank but didn't vanish (5 real causes of one "flake").
- **Why:** their own hypothesis was checked in a controlled way, neighbouring observational lines were "read" to fit it; "run it again" is free — the uninvestigated lives for years.
- **Right way:** "cause found" → next to it a line "what else explains this symptom and why it isn't that"; separate a controlled experiment from observation; before announcing, read what others already found (the mistakes journal); write `runs_to_green` honestly. A hint: BrokenPipe = the process was killed; starvation changes the denominator, it doesn't tear pipes.
- **Seen:** 5+ times.

### A test that gives the same reading for "broken" and "works"
- **Symptom:** silence from recipients reads as "the channel is broken".
- **Why:** a delta channel delivers only FUTURE changes; a test about a past event is silent both when broken and when working as designed.
- **Right way:** a beacon with a unique token and time, sent NOW, when the bases are already up.
- **Seen:** once.

### Blind diagnosis instead of a test bench
- **Symptom:** 6+ iterations through a human, all missing the target; "nothing to check it on a phone".
- **Why:** every hypothesis was checked by someone else's hands, though the behaviour could be reproduced locally.
- **Right way:** if the target can be RUN locally — the bench is the FIRST move, before the first hypothesis (a Windows binary: `wine` + `wine32:i386` + `Xvfb`, trace with `WINEDEBUG=+…`; a frontend: the real script in node with a fake DOM). Verify the fix BEFORE handing it to a human.
- **Seen:** 2 times.

### A security value without bounds and without printing
- **Symptom:** certificate validation rejects a valid server (the opposite error would have silently accepted an expired one).
- **Why:** a two-digit clock year went into date arithmetic as is → a negative difference wrapped into a huge unsigned.
- **Right way:** wherever a security decision depends on a value: bounds of a sane range (outside — an honest refusal) and print EXACTLY THAT value in the refusal diagnostics.
- **Seen:** once.

### Someone else's recommendation passed on without checking its precondition
- **Symptom:** the advice "add `usb-tablet`" sat a day in the lead's queue; the kernel has no USB at all — the mouse would have vanished.
- **Why:** a recommendation from another postmortem silently assumed a USB stack.
- **Right way:** someone else's fix advice is a claim like any complaint: check the precondition with a grep in the code before signing it with your name.
- **Seen:** once.

### Editing a non-canonical artifact
- **Symptom:** a "fix" reinvented a worse version of what already existed.
- **Why:** three artifacts existed on the topic (a POC, the full rule, a simplified derivative); the first at hand was taken; the next version was built from the derivative, not from the richer original.
- **Right way:** before "fix/build", `grep` the files that already exist on the topic; edit only after the canonical one is established; when taking a template, first ask whether its shape (unit of analysis) fits the task.
- **Seen:** once.

### The third breakage of one component — you're patching symptoms
- **Symptom:** a month of patching each breakage separately; "why doesn't it work" keeps recurring.
- **Why:** the foundation ("state is guessed from the side") is crooked, and each patch looks cheap; "how do others do it" wasn't looked up.
- **Right way:** 3+ breakages of one component → stop patching, look up "how others do it" before the next patch; a third expensive mechanism for one task → an inventory of what has already been used in this session.
- **Seen:** 2 times.

### A `claude -p` permissions test inherited MY permissions — "proved" a hole with an instrument that allows everything
- **Symptom:** `claude -p --allowedTools "Bash(sed:*)"` runs `sed -i` — conclusion "the allowlist is leaky". But `; touch` also ran, and `touch` wasn't in the list.
- **Why:** `claude -p` reads the user's `~/.claude/settings.json`; there `"allow": ["Bash", …]` permits all of Bash. `--allowedTools` only ADDS, doesn't narrow. The test measured my settings, not the list under test.
- **Right way:** `claude -p --setting-sources project` (cwd in an empty directory) plus a **control command that MUST be rejected** (e.g. `python3 -c …` outside the list). Control passed → the test is invalid. A hook under test goes through `--settings <json>`. The mode must be the production one (`acceptEdits` allows `>`/`touch` in cwd, `default` doesn't).
- **Seen:** once.

### A "sandbox" test replaced one directory, but the function also writes to its neighbours — a side write into live data
- **Symptom:** testing reference creation with a patched `refs.REFS` pointing to a temp dir. `refs.create()` calls `publish()`, which copied the test frames into a live directory (a model trains on it), and the auto-commit cron committed them within minutes.
- **Why:** patched the variable that was visible instead of reading where else the function writes (`CLIP_AUTO`, `NO_AUTO`, `TRASH_PUB`).
- **Right way:** before testing a real function, grep its body for ALL write paths (`write_*`, `copy`, `move`, `mkdir`) and patch ALL of them or stub the calls (`publish = lambda d: None`). After the test: `git status --short` over the live directories and `find -newer` — did anything appear.
- **Seen:** once.

### Browser test via CDP: after `Page.navigate`, `readyState === complete` is answered by the OLD page
- **Symptom:** an e2e test of a web-shop project failed "randomly" 1 time in 3–4 under VM load: the form went through a plain submit (page reloaded, no API request) because the scenario clicked before the page script attached its handler. Raising the wait from 10 to 20 s didn't help — which proved it isn't about time.
- **Why:** `Page.navigate` returns before the new document replaced the old one; the first `document.readyState` check runs in the old (long `complete`) page → the wait passes. Especially visible when page code moved from inline `<script>` into external files (CSP): inline ran with parsing, external runs after the file loads.
- **Right way:** before navigating put a mark on the old page (`window.__e2e_old = true`) and wait for `!window.__e2e_old && document.readyState === 'complete'`; after a click that leads to another page wait for an element the new page's script draws (the header), not only `location.pathname`.
- **Same symptom, second cause:** a "wait for server /health" loop of 100 × 0.1 s without `else: raise` — under VM load (load 24+) uvicorn started in 11 s, the loop ended quietly, the test went on and the first page was a connection error. Reproduced twice in a row. Wait with a margin (60 s) and, if not met, fail with the server log tail (`for … else: raise`). A wait that silently ran out = a test on a nonexistent system.
- **Third cause of the same class:** after navigating, the scenario waited for `location.pathname === '/auth/google/fake'` and clicked at once — the page script (external file under CSP) hadn't attached `onclick` yet, the click went into the void. Gave "random" login FAILs that were twice blamed on "an edit in the middle of the run". Wait for a mark set by the new page's SCRIPT (`!!document.getElementById('go').onclick`, an element it draws), not for the address.
- **Seen:** 3 causes, 2026-10.

### Test bench "ready" because something answered on the port — but it's someone else's server
- **Symptom:** the instrument starts its own server and waits for `/health`; the port is already taken by another agent → the own server dies with Errno 98, while `/health` is answered by the foreign one — the instrument writes test data into a foreign database and gives wrong results to both.
- **Why:** readiness was judged by a response, not by whose response.
- **Right way:** before start check the port is free; in the wait loop check your process is alive (`p.poll() is None`); and that whoever answered started no earlier than you (start time / pid in `/health`).
- **Seen:** once.

### A link from a .eml extracted with a regex from the raw file — the token is cut
- **Symptom:** the link works on the local bench, on the test bench `/verify` → "invalid or expired".
- **Why:** a quoted-printable mail breaks lines longer than 76 characters with a soft `=` line break. Locally the address is short and the link fits — the test was green for years; on the test bench with a long address the token broke. Adding `=` to the regex is a false fix (it takes the break character and loses the tail).
- **Right way:** read the mail as a mail — `email.message_from_bytes(...)`, `part.get_payload(decode=True)` over all parts.
- **Seen:** once.

### Transcript mtime ≠ the agent's last activity
- **Symptom:** "last activity 12:30" for all sleeping agents alike.
- **Why:** a nightly session-hygiene job rewrites transcript files at 12:30 — mtime becomes the hygiene time.
- **Right way:** activity = the last `"timestamp"` mark in the file's tail (256 KB), not mtime.
- **Seen:** once.

### A test green only in the daytime: "today / tonight / until end of day" against the clock
- **Symptom:** a test passes in working hours and fails in the evening (here: after ~23:30 in the shop's time zone): a lot "in half an hour" is no longer "today", there are no free slots "today", "the second window of the first day" doesn't exist. The deploy gate runs at any hour — a red release twice in a row.
- **Why:** the test depends on the real "now" and the day boundary, while the data it creates is relative ("+30 min").
- **Right way:** build state that doesn't depend on the hour (here: a discount via retail instead of "tonight"; take "the second window" from the list of all days); when the condition truly needs a time of day — skip with a reason; run a new date-based test "in the evening" too (patch the time or run at 23:xx). Found one such defect → grep the neighbouring tests for the same.
- **Seen:** once.
