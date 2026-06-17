---
name: register-as
description: Register the current Claude Code session as a named agent in the shared registry so other sessions can call it via /call-agent. Invoked when the user says "/register-as <name>", "register this chat as <name>", "this session is now <name>".
---

# register-as

Self-registration. The current session writes itself to `$CLAUDE_METHODOLOGY_DIR/agent-registry.json` under the given name.

## How to invoke

User passes a name (lowercase, ASCII, dashes/underscores allowed). Examples:
- `/register-as security`
- `/register-as research`
- `/register-as ops`

## What to do

Run the helper:

```bash
python3 "$CLAUDE_METHODOLOGY_DIR/scripts/register_agent.py" <name>
```

The script pulls `$CLAUDE_CODE_SESSION_ID` from the environment and adds:
```json
{"<name>": {"sid": "<uuid>", "cwd": "...", "user": "...", "registered_at": "..."}}
```

If the name is already taken, it's overwritten (the session moves to the new sid).

## Report back

Short: name + sid (first 8 chars) + path to the registry file. No prose.

If the name is invalid (empty, contains special chars beyond `-` and `_`), the script exits with an error — relay it to the user.

## Anti-patterns

- Don't register under a name the user hasn't explicitly said. No guessing.
- Don't duplicate the name into memory or other files. The registry is the single source of truth.
