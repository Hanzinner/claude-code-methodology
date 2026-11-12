---
name: register-as
description: Register the current chat as a named agent of the swarm (creates the agent folder from the template, adds a line to the AGENTS.md registry, records the session identity). Use when the user says "/register-as <name>", "register as <name>", "this session is now <name>".
---

# register-as

Turns the current chat into a named agent: a folder with a briefing, an inbox and two TODO files, one line in the
registry, and the session identity so the per-prompt watchman recognises you from now on.

Names: letters, digits, `-` and `_`, no spaces, no leading `_` (a leading `_` marks a template). The folder name IS
the agent's name; other agents address letters to it.

## Steps

Run this once, with the name in `NAME` (take it from the user's message; ask if it is missing or contains spaces):

```bash
NAME="<name>"
eval "$(python3 "${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}/lib/ccm_conf.py" --shell)"
AGENTS="$CCM_AGENTS_DIR"; TEMPLATE="$AGENTS/_example-agent"; REGISTRY="$CCM_WORKSPACE/AGENTS.md"
DIR="$AGENTS/$NAME"
case "$NAME" in ""|_*|*[!A-Za-z0-9_-]*) echo "bad name: $NAME"; exit 2 ;; esac
[ -d "$TEMPLATE" ] || { echo "no template folder $TEMPLATE (copy swarm-template/ into the workspace first)"; exit 2; }
if [ -e "$DIR" ]; then echo "$DIR already exists - nothing copied"; else
  mkdir -p "$DIR" && cp -r "$TEMPLATE"/. "$DIR"/
  sed -i "s/<agent-name>/$NAME/g" "$DIR"/*.md
  echo "created $DIR"
fi
if [ -f "$REGISTRY" ] && ! grep -q "^| $NAME |" "$REGISTRY"; then
  printf '| %s | (fill in after the first conversation) | (fill in) | `Agents/%s/briefing.md` |\n' "$NAME" "$NAME" >> "$REGISTRY"
  echo "added a line to $REGISTRY"
fi
mkdir -p "$HOME/.claude/agent-identity"
```

Then record the identity (the session id is in your hook context; if you do not have it, the watchman records it by
itself when the user's first prompt in a chat is the agent's name):

```bash
echo "$DIR" > "$HOME/.claude/agent-identity/<session_id>"
```

## After registering

1. Fill in the scope in `briefing.md` yourself after the first real conversation with the user: role in one line,
   what the agent owns, what it does not touch, where its tasks come from.
2. Check the registry row (`AGENTS.md` at the workspace root): its `Owns` and `Doesn't touch` columns are the part
   people read; two agents owning one file is how work gets lost.
3. The registry is a table for humans. The source of truth is the folders that contain a `briefing.md`.

## Idempotent

Running it again for an existing name creates nothing and adds no second registry line.
