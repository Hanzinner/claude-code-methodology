#!/usr/bin/env python3
"""ai_studio_to_md.py - turn Google AI Studio chat exports (JSON with "chunkedPrompt") into Markdown an agent can read.

Usage:
    ai_studio_to_md.py [folder]     # every file under the folder (recursively) that is an AI Studio export; default: cwd
    ai_studio_to_md.py <file>       # one file

Why: AI Studio saves a chat (to Google Drive) as one JSON file, usually without an extension. Read raw, it is mostly
markup and the model's hidden "thought" chunks; the conversation itself is a fraction of it.
The .md lands next to the source: <name>.json -> <name>.md, a file without that extension -> <name>.md appended
(so "chat v1.2" and "chat v1.3" don't both become "chat v1.md"). An existing .md is overwritten.
Per chunk: thoughts are skipped, an attached file / Drive document becomes a one-line placeholder, empty text is skipped.
Roles: "user" is labelled with CCM_HUMAN_NAME, "model" as Gemini.
rc: 0 · 2 the path does not exist.
Test: tests/ai-studio-to-md-test.py
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.realpath(__file__)), "..", "lib"))
from ccm_conf import conf  # noqa: E402

HUMAN = conf("CCM_HUMAN_NAME", "the user")
HUMAN = HUMAN[:1].upper() + HUMAN[1:]


def is_ai_studio_file(path: Path) -> bool:
    try:
        with path.open(encoding="utf-8", errors="replace") as f:
            if "chunkedPrompt" not in f.read(4096):      # cheap filter before parsing a whole file
                return False
        with path.open(encoding="utf-8", errors="replace") as f:
            return "chunkedPrompt" in json.load(f)
    except Exception:
        return False


def chunk_to_md(chunk: dict) -> str | None:
    """The chunk's text, or None to skip it."""
    if chunk.get("isThought"):
        return None
    if "inlineFile" in chunk:
        mime = chunk["inlineFile"].get("mimeType", "unknown type")
        return f"_[attached file: {mime}]_"
    if "driveDocument" in chunk:
        doc = chunk["driveDocument"]
        name = doc.get("name") or doc.get("mimeType") or "Google Drive document"
        return f"_[Google Drive: {name}]_"
    text = chunk.get("text", "").strip()
    return text or None


def out_path(src: Path) -> Path:
    return src.with_suffix(".md") if src.suffix.lower() == ".json" else src.with_name(src.name + ".md")


def convert(src: Path) -> Path:
    with src.open(encoding="utf-8", errors="replace") as f:
        data = json.load(f)

    lines = [f"# {src.name}", ""]
    for chunk in data.get("chunkedPrompt", {}).get("chunks", []):
        content = chunk_to_md(chunk)
        if content is None:
            continue
        role = chunk.get("role", "")
        label = {"user": f"**{HUMAN}:**", "model": "**Gemini:**"}.get(role, f"**{role}:**")
        lines += [f"{label} {content}", "", "---", ""]

    while lines and lines[-1] in ("", "---"):    # drop the trailing separator
        lines.pop()

    out = out_path(src)
    out.write_text("\n".join(lines), encoding="utf-8")
    return out


def find_and_convert(folder: Path):
    converted = 0
    for path in sorted(folder.rglob("*")):
        if path.suffix == ".md" or path.is_dir():
            continue
        if is_ai_studio_file(path):
            out = convert(path)
            print(f"  {path.name} -> {out.name}")
            converted += 1
    if converted == 0:
        print("No files with chunkedPrompt found.")
    else:
        print(f"\nDone: {converted} file(s).")


def main():
    args = sys.argv[1:]
    if args and args[0] in ("-h", "--help"):
        print(__doc__.strip())
        return
    target = Path(args[0]) if args else Path.cwd()
    if target.is_file():
        out = convert(target)
        print(f"{target.name} -> {out.name}")
    elif target.is_dir():
        find_and_convert(target)
    else:
        print(f"ERROR: '{target}' does not exist", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
