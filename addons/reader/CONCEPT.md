# Concept: a document reader for agent output (not shipped)

## Problem

Agents write long Markdown (reports, plans, research notes). Reading them in a terminal scrollback or a raw file
viewer is poor, and the human often reads on a phone or a tablet, not at the machine. The agent needs one cheap way to
say "read this" and hand over a link.

## How it works

* A tiny HTTP server (Python standard library, one file, ~230 lines) serves one single-page reader (`reader.html`, one
  file, a bundled Markdown renderer, no build step) and a handful of read-only JSON routes:
  directory listing, file text, full-text search (name and body), a "last opened" pointer, per-user settings, a
  download route.
* **Safety model:** only an allow-list of extensions (`.md`, `.markdown`, `.txt`, `.fb2`), every path resolved with
  `realpath` and required to stay under one root, dot-files never served, heavy and secret folders skipped by search.
  It is "read-only" for documents but writes two small state files (last file, settings), so a page-load test can
  change them. There is no authentication: it is meant for a trusted LAN or behind a reverse proxy that authenticates.
* **The agent channel:** a "shared with you" folder. An agent drops a `.md` there and the reader lists it in a section
  at the top; or the agent gives a deep link `http://<host>/?open=<url-encoded path under the root>`.
  Questions that need an answer do NOT go there - typing on a phone into a reader is the wrong channel; the reader is
  for things the human only reads.
* **State lives on the server, not in the browser** (theme, layout mode, last file, collapsed sections), so the same
  reading experience follows the human across devices.
* The page itself is the product: paged and scrolling layouts, three themes, a table of contents from headings,
  a FB2 renderer for books, footnotes, adjustable font/width/line height. Most of its 100 KB is that interface.

## What a stranger would need

A static HTML page with a Markdown renderer, the server above with the root configurable (the live one hard-codes its
workspace path and a list of hidden folders), a decision about the shared folder name, and a decision about access
(LAN only, or a proxy with login). Do not expose it to the internet as is.

## Why it is not shipped here

1. The page is a 108 KB single file with a Ukrainian-only interface and live-workspace specifics (a section named after
   the agent swarm, junk filters for agent files such as briefings and inboxes, a deep-link format tied to one host).
   Making it generic means translating and re-skinning the interface, which is a product, not a port.
2. Its owner already has a plan to publish it as a **separate standalone repository** (configurable root, English
   interface, replaced demo content, its own README and licence). Duplicating half of it here would create two diverging
   copies of the same page, and the publication decision is the human's, not an add-on's.
3. The agent-side value in this repo is small and already covered without it: any static file server pointed at the
   shared folder, or the editor's Markdown preview, gives the same "here is the link" workflow.
