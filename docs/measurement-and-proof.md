# Measurement and proof: when the instrument lies

A mechanism is only as good as your proof that it ran — and that proof is only as good as what your
instrument can actually *see*. Across one intense stretch of building, most of the wasted time went not
into broken features but into **broken measurement**: gates that reported green on things that were red,
and "done" claims backed by evidence that proved nothing. This is the tuition, written down.

Companion to [`multi-agent.md`](multi-agent.md) — that doc's "announced a result you never verified" is
the same disease seen from the swarm side.

## 1. Proof is an artifact only the work could produce

Three times in a day, three different agents reported success on evidence that meant nothing:

| "proof" | reality |
|---|---|
| "the guard hook appeared" — *saw a line in the output* | it was an `echo` in the deploy script, printed *after* the work; it prevented nothing |
| "the runner is live" — *`crontab -l` + a file on disk* | under cron it had **never once** assembled (empty `PATH`); the release sat for 3 hours |
| "sent to all three" — *a `✓` from the script* | the message existed nowhere — not in a file, not in any commit |

**Proof = an artifact only the mechanism's own work could have produced:** a line in the log written *by
the cron itself*, a tag, a built image, a `grep` hit in the recipient's file. **Not proof:** `crontab -l`,
a file existing, a line in stdout, a return code, a `✓`.

The corollary was learned the hard way: **if it runs under cron, test it the cron way** — with cron's
empty environment. The runner's "smoke test" was run by hand, from a normal shell with a normal `PATH`,
and passed. Under cron it failed every time. The test measured the wrong thing.

And the instrument itself made this exact error one level down: the inbox writer validated a *temp file
before the rename* — proving it had *assembled* the file correctly, and saying nothing about whether it
*survived*. Fix: validate **after** the write, **by reading from disk**, and look **in the right section**
("present in the file" ≠ "delivered" — a real case had a message sitting in the file yet invisible).

## 2. The instrument measures what it can see, not what is

A verification gate lied four different ways in one day:
1. a list of "hot functions" missing one entry → a regression sailed straight through it;
2. the same list missing another → apps were reading the disk *every frame*, unmeasured;
3. a UI list missing a module → the "0 violations" number in the report was simply false;
4. a macro hid the call site → it reported **0** where there were **16**.

**Who found these? Nobody searched — they stumbled**, both times by accident, poking at code the gate had
supposedly already checked.

Worse, the instrument didn't just stay silent — it **doubled the symptom**. A timing test waited a fixed
**1.2 s**; the event it measured actually took **0.44–1.98 s** (measured). So in **4 of 17 successful
runs** the instrument printed `FAIL` where the system had worked correctly. A fixed pause against an
event of variable duration is a race by construction.

The swarm spent a day hunting a broken product when the broken thing was the **measurer**. Two of five
root causes lived in the input path and the instrument, not in what they were measuring.

The mechanism isn't a better gate — it's a **role: an owner of the instrument** whose daily question is
not "what bugs did we find?" but **"what can this instrument not see, by construction?"** Their product
is *trust in the number*, not a list of bugs.

## 3. "Flake" is a name for the uninvestigated

One symptom — "the window sometimes doesn't open" — turned out to be **five** distinct, real causes
(a shared socket, a filesystem call in a hot path, mutual process-killing, CPU contention, a torn input
gesture). Each fix *reduced* the symptom without removing it, so each one felt like "that was it" — and
each cause masked the others.

- **The label is banned.** "Flake", "harness", "oh it's just a double-click" are not diagnoses. Fix a
  cause and the next red is the **sixth**, not "ugh, that again".
- **Measure instability, don't rename it.** A `runs_to_green` field on every release, filled honestly.
  As long as "just run it again" is free, the residual bug lives for years.
- **And the *instrument* measures it, not the agent.** The runner measured `runs_to_green=2` against a
  claimed `1`. Measurement must not depend on the good faith of the party being measured — that's the
  whole reason it's *measured* and not self-reported.
- **Pass the signal, not the label.** The sharpest formulation of the stretch: *"the noise is gone —
  under it you can see the signal."* Not papering over the unknown with a name is exactly what let the
  next person catch it.

## 4. The machine verifies the predicted; a human finds the unpredicted

The gate said **28/28**. A hands-on reviewer sat down and in half an hour found **three broken features
the instrument didn't see and never will**:
- a label that lies about its action ("align icons" actually *reset* them);
- no live feedback ("you drag and it only moves when you let go") — the machine sees the *end state*, a
  human sees the *process*;
- a click that falls straight through into the canvas — the instrument measures the *result*, not the
  *path to it*.

And, just looking at the screen, they named an **architectural** flaw: *"the window and the text aren't
connected — they're just nailed together."* That was the exact thing a core contract was built to
prevent, and one screen wasn't using it. A non-specialist saw in a second what the gate will never see —
because the gate can't ask *"why is it like this?"*.

**The machine verifies what you already thought to check. A human finds what nobody thought of.** This is
not "QA as a stage" — it's a **different sense organ**. So the classic tester ("coders finish, I'll poke
it") is dead weight: they become the bottleneck. The modern role is **owner-of-the-instrument plus
hands-on investigator** — and they hold a **stop-cord, not an acceptance veto**. No veto raised → it ships.

One more lever, cheap and large: **the angle of the report decides what it finds.** Asked for a
"verification checklist" (what to do / what should happen / where unsure), the reports were tick-boxes.
Reframed to **"You wanted X / Now it's Y / But Z"**, the same agents went and found the operator's *own
past words* ("don't forget the gradient", "the window's too small"), each opened with the *worst* problem
unprompted, and added a line for "you didn't ask for this — we did it anyway". "Check it" yields a
checklist; "you wanted it" forces the work to be compared against *intent*, and that's where "we built the
wrong thing" surfaces.

## 5. The honest edge: some things have no mechanism

Every section above ends in a mechanism — a role, a field, an after-write check. This one doesn't, and
that's the point.

**Against a fabricated fact there is no gate.** You can mechanize "prove the hook ran" and "measure
instability honestly", but you cannot mechanize "the agent stated something that was never true and
believed it". The defenses there are cultural — proof next to every claim, labelling a hypothesis a
hypothesis — and culture is not a gate. Where a control is still just discipline, it should be *labelled*
as still just discipline, not dressed up as solved. A document that admits where it has no mechanism is
more useful than one that pretends the whole surface is covered — because the reader then knows exactly
which corners to watch themselves.
