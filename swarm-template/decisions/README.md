# decisions/

A decision journal in the ADR format (Architecture Decision Record, Nygard): one file, one decision.

- **The rule: a decision that is not in the journal does not exist.** Agents and sessions forget; a file does not. Before you reopen a question, look here.
- **One file per decision**, named `NNNN-YYYY-MM-DD.md`. Copy `0000-template.md`, take the next free number.
- **A number is never reused**, including for withdrawn drafts.
- **A replaced decision is not deleted.** Set its status to `replaced by #N` and write the new one as a new file. The history of why things changed is the point.
- **Write the why in one or two lines**, not the what: the reasoning is what a later reader cannot reconstruct from the code.
- Statuses: `current`, `replaced by #N`, `deferred` (decided to postpone; say where the work is parked).
- Who decides: the field "who" names the person or role that made the call. An agent proposing is not deciding.

Why it exists: the first version of this journal was one file inside a methodology document. A review against the ADR practice flagged it: each decision should have a stable number and its own status, so a replaced one stays readable. The norm comes from the ADR practice; there is no source showing one big file does measurable harm, so this is following the established form, not a proven fix.

Optional: keep an index (one line per decision) in your methodology document; the files stay the source of truth.
