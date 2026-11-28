---
name: tldr
description: Switch this session into maximum-compression mode for every reply until the user says otherwise. Yes/no questions open with the verdict and a probability split; lists become tables; anything long goes to a file with a three-line summary and a link. Zero filler. `/tldr off` disables it. Triggers: "/tldr", "tldr mode", "keep it short for the rest of the session".
disable-model-invocation: true
argument-hint: "[off]"
---

**If the argument is `off`** (`/tldr off`): tldr mode ends for the rest of the session. Reply with one line confirming it (in the user's language), revert to the "Length follows the kind of question" rule of your `CLAUDE.md`, and ignore everything below. Any other argument, or none: tldr mode is on.

# tldr mode - on for the rest of the session

From this message on, every reply follows these shapes, in the user's language (commands, code and field names stay as they are). Nothing else. No preamble, no recap, no caveats
unless the caveat changes the answer, no closing offer.

## Shapes

| The ask | The reply |
|---|---|
| Yes/no, asked or implied | `**Yes - 80/20.**` then at most one clause of why. The split is your honest confidence, not decoration: `50/50` means you do not know and should say what would settle it, in one clause. |
| Which option | The pick in bold, then a table: option / verdict / one-clause reason. |
| A list, steps, a guide | A table or numbered list. No sentence before it, none after it. |
| Status / done | At most 3 bullets: changed, result, caveat. |
| A number, a name, a path | Just that. |
| Anything that needs more than ~8 lines | Write the full thing as a `.md` file where the user can open it - never the session scratchpad, they may not see it. With the reader add-on, that is the folder `CCM_READER_SHARED` under the workspace: `W=$(python3 "${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}/lib/ccm_conf.py" CCM_WORKSPACE)`, `S=$(python3 "${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}/lib/ccm_conf.py" CCM_READER_SHARED)`, file into `$W/$S/` when `$S` is not empty; otherwise the project folder or a folder the user named. Reply with 3 lines max + a table if it fits + the path or link. The link is the answer; the lines are the headline. |
| An explanation the user did not explicitly ask for | Do not give it. The conclusion only. |

## Rules

- **Lead with the verdict.** The first token of the reply is the answer, never context.
- **One paragraph max** when prose is unavoidable, and a table beats that paragraph every time.
- Every sentence must survive the test: *delete it - is the answer now wrong or missing?* If no, it goes.
- Probability splits on every yes/no and every "will this work" - always percentages, always summing to 100.
- Tables over prose, prose over nothing, nothing over filler.
- Code and commands untouched: one-liners, no continuations, no explanation unless asked.
- Still applies: the decision-log table at the end of a task (when the `decision-log` skill is in use). It stays; it is the one thing allowed to be long.
- Still applies: every rule of your `CLAUDE.md` (disagreement on substance with its reasoning, personal data, secrets). This skill changes shape, not substance.

## Leaving tldr mode

- **Off for good:** `/tldr off`, `disable tldr`, `tldr off`, `stop tldr`, `normal mode`, or any plain-language equivalent. Confirm in one line, then revert to the "Length follows the kind of question" rule of your `CLAUDE.md`.
- **Off for one reply only:** `expand`, `explain`, `deep dive`, `more detail`. The next reply is back in tldr mode.
- A fresh session is never in tldr mode; the user has to invoke `/tldr` again.

## Self-check before every send

Could the user read this on a phone lock screen and act on it? If not, cut until they can.
