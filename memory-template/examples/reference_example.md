---
name: reference-example
description: Example reference-type memory — pointer to an external system and what it's for.
metadata:
  type: reference
---

# Internal dashboards (example)

- **grafana.internal/d/api-latency** — oncall watches this; if you touch request handling, that's the dashboard that pages someone
- **Linear project "INGEST"** — where all pipeline bugs are tracked; check it for context on related tickets
- **wiki.internal/eng/runbooks/** — runbooks for production incidents; reference, don't rewrite

When the user mentions any of these by name, check there first before answering — these are the source of truth for current state, not the codebase.
