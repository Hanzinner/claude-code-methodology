---
name: edit
description: Analyze a video edit/montage. Extracts scene-change keyframes, builds a per-frame log with cultural/historical/geographic markers, and writes a narrative about the editing choices. Use when the user says "analyze this edit", "break down this video", "break it into frames", "/edit", or provides a video URL/file for visual analysis.
---

# Edit analysis

## Step 1: Context (auto-extract metadata, then the user narrates the beats)

**1a. Auto metadata (YouTube URL):**
```bash
yt-dlp --print "TITLE: %(title)s%(\n)sCHANNEL: %(uploader)s%(\n)sDATE: %(upload_date)s%(\n)sDURATION: %(duration_string)s%(\n)s---DESC---%(\n)s%(description)s" "<URL>"
```
Do not ask about what is visible in the description.

**1b. The user narrates the editorial beats:**
Before extraction, ask the user to briefly describe the key editorial beats (30-60 seconds). Example:
> "opening: a series of photos of the dead, each with more crosses; climax at 1:30: the embassy balcony; coda: ordinary patrols. The music peaks at 1:05 with an explosion."

This is not a wasted step; it is an **inverted flow** that works more reliably. The user has an editorial eye the agent lacks (layers 4-5: cultural reading + audio sync). Without their narrative the agent describes frames technically correctly but misses what the edit actually does.

**Lesson from a past run:** on a single video the agent misread culturally specific content three times even with context: the opening photo (read as the attackers instead of the victims), a photo-sequence decay (did not notice it was a series), and an explosion synced to a music peak (saw "birds", not an explosion).

**If the user says "just analyze it, I don't want to explain":** go through Steps 2-4 with an explicit warning in the output: "without the user's editorial narrative the risk of misinterpretation is high, especially for openings, transitions and music-synced moments".

## Step 2: Extract scenes

```bash
"${CLAUDE_METHODOLOGY_DIR:-$HOME/.claude}/scripts/extract_scenes.sh" <url_or_path> [threshold] [outdir]
```

`$CLAUDE_METHODOLOGY_DIR` is set by the installer (settings.json env). Requires `ffmpeg` (and `yt-dlp` for URLs).

- `url_or_path`: YouTube URL or a local file path
- `threshold` (optional): 0.0..1.0, default 0.25. Lower means more frames. 0.3 for dense montage, 0.15 for slow.
- `outdir` (optional): default `/tmp/edit_TIMESTAMP`

The script writes `scenes.tsv` (frame name TAB timestamp) and the frames into `frames/`.

## Step 3: Read frames sequentially

Load all frames (the Read tool; batches of 10 are fine). For each:

- Timecode from `scenes.tsv`
- **Subject:** who/what, action, composition
- **Markers:** country/place/period (architecture, uniforms, cars, fonts, equipment)
- **Cut type** if explicit (hard cut, match cut, jump cut, dissolve)
- If the context from Step 1 creates an expectation, compare against it ("expecting the 1991 coup, seeing Yeltsin: confirmed" or "does not match: flag it")

Not pixel-perfect, but detailed enough to tell similar frames apart and to spot patterns.

## Step 4: Narrative

After the per-frame log, the narrative:

- **Editing tempo:** average shot length, dynamics (speeding up / slowing down)
- **Recurring visual themes:** what repeats
- **Archive vs staged vs mix:** whether the editor uses original footage or composites later material
- **Editor's thesis:** which emotion or idea the edit builds through its choice of cuts
- **Points of effect:** where the edit "works" (music sync, contrast, build-up)
- **Weak spots**, if any

## Output format

```markdown
## Context
[short, from Step 1]

## Log
[scene by scene per Step 3]

## Analysis
[narrative per Step 4]
```

## When NOT to use this skill

- The user wants a single screenshot described: that is not an edit, just read the image
- Audio-only podcast or recorded conversation: that is transcription (yt-dlp + subtitles)
- The user asks to "just download the video": that is not analysis, call yt-dlp directly

## Anti-patterns

- Skipping Step 1 to "show results faster" produces hallucinated context
- Skipping 1b (user narrates beats): even with full context the agent will miss the editorial meaning
- Analyzing without `scenes.tsv`: timecodes are mandatory
- Describing a frame outside its time position: an edit is a sequence, not a catalog
- Stretching every frame into a paragraph: the log must be compact
- Flattery ("what a great edit") without concrete points of effect and weaknesses: calibration over comfort
- Interpreting photo-flip / document-flip sequences as one frame: scene detection does not catch them (see Limitations)

## Limitations (pipeline blind spots)

- **Audio / music sync:** the script extracts video frames only. Beat drops, music peaks and sound effects are outside the analysis. It relies on the user.
- **Photo/document flip sequences:** scene detection at threshold 0.25 does not catch switches between photos or documents with a similar composition. The editor may show a series of shots between detected "scenes". Marker: a gap of 3 seconds or more between scenes in the opening is suspect; ask the user.
- **Slow dissolves / continuous camera moves:** also not captured as cuts. Same symptom.
- **Culturally specific identification (layers 4-5):** a general limit of seeing without understanding; context from the user is the only reliable fix.
