# Web playbook: how agents in a swarm build sites

Agents that build small internal sites (a document reader, a status panel, a catalog, a review UI, a game
prototype) kept re-learning the same things. This is the shared file they read before starting a new site
or a big change, and append to afterwards. Each entry exists because someone got it wrong first.

Code-level traps (HTML/JS/CSS) live separately in [`code-pitfalls/web.md`](../code-pitfalls/web.md); a hook
shows the matching headings before an edit to `.html/.js/.css`. This file is the **recipe and the
experience**; that one is the **traps**.

Placeholders used below: `<site>` (a site's name), `<port>`, `<code dir>`, `<lan-domain>`.

## 1. Who owns what

- **One agent owns the shared look** (a starter template, a layout test, this playbook) and signs off the
  look before it goes to the human. Visual corrections from the human go to that agent as a letter.
- **The agent of the case owns the site's code** (what it can do). The reader site belongs to the library
  agent, a project's UI to that project's agents, and so on.
- **A separate infrastructure agent owns "is it alive and reachable"**: the service unit, the reverse proxy,
  the certificate, name resolution. A site's author does not write units or proxy blocks; they send a letter.

The repo ships none of these agents; see [`multi-agent.md`](multi-agent.md) for how roles and letters
(`scripts/inbox_post.sh`) work.

## 2. The stack, and why it is boring

- Server: Python standard library (`http.server` + `json`), no framework, no frontend build.
- Page: one HTML file with inline JS and CSS.
- Reason: zero dependencies, survives years without updates, any agent reads the whole thing in a minute.
- Exception: a site that already sits on a Python pipeline with dependencies may use a venv.
- A small vendored library is fine when it replaces something hard. A Markdown renderer dropped in as a
  separate `<script>` took half an hour; a hand-written parser would have eaten an evening on tables and
  nested lists. Vendor files locally (`vendor/`), never from a CDN, and load heavy ones only when the user
  enters the mode that needs them.

## 3. New site from zero: checklist

0. **Do not start from zero: copy the starter template** (`page.html` + `server.py`) that already contains
   every fix the human asked for on earlier sites. *(Not in this repo: the starter template and its layout
   checker are private. Section 4 describes what the checker does, so you can build your own.)*
1. **Port:** check the port map and the listening sockets, take a free one, write it into the map. Bind
   `127.0.0.1` if people only come through the reverse proxy.
2. **Code** goes in the project's folder, not in a home directory of a service account.
3. **Letter to the infrastructure agent:** service unit (enabled, restart on failure), proxy server block,
   certificate, favicon, a card on the landing page, name resolution on the people's machines, and a
   **functional supervisor check** (the page returns 200 *and* the expected content). The supervisor is
   `scripts/supervisor.py` with checks in `config/supervisor-checks.template.json`; `scripts/checks_lint.py`
   validates the file.
4. **Add a line to the mechanism catalog** (`swarm-template/LIBRARY.md`). A site that is not in the catalog
   does not exist for other agents.
5. **Show the human one named link**, never a bare numeric address. If the site uses a private CA, the
   phone will warn; that is expected, say so.

## 4. "Done" for a page means seen, not "it started"

- Run a layout checker (headless browser, several widths, with panel states if the page has panels). It must
  exit non-zero on failure. **A test that exits 0 on FAIL is not a test for automation**; check the exit
  code of your own run. *(The checker is not in this repo.)*
- A screenshot of the **default state**, not only of an open dialog. Describe in words what is visible.
- **Phone width (~390 px).** The humans look from phones. One reader site shipped for two months with zero
  media queries and the side panel ate the whole text; it was found by a separate review, not by its author.
  Check the phone width on the day of delivery.
- A **scenario run** of clicks and buttons in a real browser, not only `node --check`. One agent broke its JS
  three times in a day with patches that passed the syntax check: a pasted `//` comment swallowing the rest
  of a line, a reassigned `const`. The page must never hide its own errors in an empty `catch`.
- **Refresh (F5)** does not lose state and does not bind handlers twice.
- For changes the human will feel by hand: one line "was -> now".
- **One element, one function, one owner.** A shared element (item card, header, action button) is drawn by
  one function for every page and role; differences are parameters, not copies. A story that splits a page
  by role (guest/buyer, phone/desktop) lists the deliberate differences in its "done when"; everything else
  must match, and QA compares them with an instrument on every surface. Real case: a "N bids" badge existed
  in the guest storefront and was missing for ten days in the buyer's feed, because two functions drew the
  same card.

## 5. Human preferences (only what the human said or corrected)

- **Data notes describe content, never attitude.** A catalog entry that said "can be skipped" was a decision
  made for the human, and was called out. Before handing over, walk your own notes and delete every one
  about attitude instead of content.
- **UI state is not tied to a device.** Settings, collapsed sections, "last opened" live on the server, not in
  `localStorage`: the human works from two laptops and was tired of re-switching.
- **Long text:** vertical scroll, a narrow centered column, sans-serif, **no hyphenation**, left-aligned.
- **A quote is a background plate with a side stripe**, not muted or italic text. Tables have no vertical lines.
- **Side-panel sections are collapsible and collapsed by default**, with a visible triangle.
- **The default OS scrollbar is unwelcome:** thin, rounded, theme-colored.
- **Navigation:** links in text colour, not muted; current item filled; group labels smaller and dimmer. Grey
  links next to grey labels were unreadable.
- **A complaint is not an instruction to change what you did.** Change only what was pointed at. "Looks
  strange" about empty gaps above each row of tabs was about the group labels sitting on their own line, not
  about tab widths; an agent that also narrowed the tabs was reverted.
- **A double-meaning complaint gets one clarifying question.** "Squashed text" was treated as spacing twice;
  it was the font. One question is cheaper than two wrong edits.
- **The human views at browser zoom.** "1885 px" on their screen is not 1885 CSS pixels. Check a range of
  widths, not one.
- **The human may open sites by raw IP, not the nice name.** A script that enables the shared palette only
  on the proper domain then leaves the page white with black boxes. Give every page its own fallback colour
  variables and run the layout test without the shared script as well.

## 6. Side panels, tabs, sticky headers

- **A side panel takes width, it does not overlay.** The page narrows smoothly; the grid takes its columns
  from the **container's** width (`auto-fill/minmax`, container queries for small things). A fixed
  `padding-right` plus a hard minimum column width collapsed cards to one column; an overlay was rejected as
  "covers content". On a phone the panel is a sheet over the page.
- **Test widths x panel states, not two screenshots.** "1440 and 400 with no panels" missed a broken tab row at
  ~1100 px with a panel open. Run 6 widths (e.g. 1885/1440/1280/1100/1000/400) x 4 states (none/left/right/both)
  and assert programmatically: container `scrollWidth <= clientWidth`, every button inside container and
  window, no page-level horizontal scroll.
- **Tabs are equal shares of a row** (`grid-template-columns:repeat(auto-fit,minmax(12em,1fr))`; minimum = the
  longest label plus its counter, or text is cut with a panel open). A row's group label sits at the left of
  the same row, fixed width.
- **Measure a sticky header's height at 390 px and at mid widths with panels** (one site's header took 53% of
  the window). Never put a second sticky element under it with a hardcoded `top:`; the header grows when it wraps.
- **Close-state details inside `overflow:hidden` cards** can be reported as clipped by a layout checker:
  `details:not([open])>:not(summary){display:none}`.
- A name made of two inline pieces in `inline-flex` with `gap` gets a visible space between them; use margin.
- A large number in a small card (`$22,499.98` in 141 px): size the font from the card's width
  (`container-type:inline-size` + `clamp()` with `cqi`).
- Touch targets: a global `@media(pointer:coarse){button{min-height:44px}}` loses to any button class with its
  own `min-height`; repeat the minimum in the coarse block for that class.
- `flex:1.6` on one panel in a row of `flex:auto` panels has basis 0 and collapses to a column. For "all in
  one row by content", use `flex:1 1 auto` for all.

## 7. Showing only proven state (status panels)

An early version of a status panel claimed "working/done" from indirect signals (file mtimes, a substring
match of a commit subject that attributed a commit to the wrong agent).

- **Show only a state with evidence visible on the card:** a live process, a hook event younger than N
  minutes, the time of the agent's own event. No evidence -> an honest "idle" or "-". An indirect signal is a
  lie the reader takes as fact.
- **Degrade stale state on every render, do not wait for someone to overwrite it.** A Stop hook left WORKING
  and the file froze for 13 hours. The page now turns WORKING older than 15 minutes without events into
  "IDLE (auto-degraded, stale N min)". Then anyone sees the truth, even a reader of the raw file.
- **Block buttons only on proven state.** A stale status that blocks "wake" means you cannot wake the one you
  need to.
- A summary page built from other documents does not hold state itself: it reads the source on a schedule and
  shows when the source last changed, or it shows "in progress" for a project that has been paused for a month.
- **Show the result "as it will be", not the raw input.** Drop a PNG -> next to it the render through the same
  processing the product uses (48x48 icon, cursor with alpha threshold). The human checks the outcome.

## 8. Testing browser pages

- **Headless measurement:** disable CSS transitions and shim `requestAnimationFrame` in a test copy, measure
  `getBoundingClientRect`, give each run its own `--user-data-dir` (two runs in one profile start from each
  other's saved state).
- **Own driver over the DevTools protocol, no framework install:** real mouse clicks, `Input.insertText`,
  a temporary database. A test proves it catches breakage only when run on a deliberately broken copy
  (12/14 failed on the broken copy).
- **Three checks that do not replace each other:** a scripted scenario with virtual time (fast, logic), a
  real-time run (loading, frame loop), and real touch events via `Input.dispatchTouchEvent` (the phone's path).
- **Pair every behaviour test with a control:** the scenario with the change and the same scenario with the
  change off. The control proves the test can see the difference and the original is not broken.
- **A self-test inside the page** (`?selftest=1`, its own storage key, result in a `<pre id=selftest>`; headless
  `--dump-dom` reads PASS/FAIL). Clicks go through the same handlers a person uses.
- **A scenario must prepare its own data.** A test that took "the first card of a tab" failed once people
  started sorting cards in the live copy. Move the cards you need into your own tab in the DOM copy, exclude
  already-touched ones.
- **A state-click scenario must throw on failure**, so the run says "could not" instead of green.
- **A page that writes state through GET** (`?set=`) makes any test that opens it change the user's data. If
  you did this, say so in the site's docs. Better: do not.
- **A local copy on `127.0.0.1` has no shared palette** if the palette script only turns on for the real domain:
  fake variables, transparent panels, a PASS on an unstyled page. Map the real hostname to localhost in the
  browser (`--host-resolver-rules`) and check the shared banner appears in the screenshot.
- **Behind a login:** a tiny proxy that adds the session cookie to each GET. It must not strip security
  headers (a proxy that dropped CSP made inline scripts "work" in tests that failed on the real stand).
- **After a release of the backend, restart your own preview process too.** A preview older than the release
  does not see the new security headers: pages with inline `<script>` worked there and were blank everywhere
  else. Page scripts as files only, no `onclick=`. And include a state that needs drawn content, or "blank
  page" counts as PASS.
- **Layout-checker `--settle` was seconds, not milliseconds**: `--settle 2500` meant 40 minutes per cell and a
  "hung" run. Do not switch desktop/phone variants by `@media (hover:...)`: headless has no mouse, so the
  desktop variant never reaches a screenshot; use width.

## 9. Deploying a site people already use

- **Do not restart the service in the middle of someone's clicks.** Check for quiet in the access log for
  >= 2 minutes (mind the timezone in the log) and restart in the first quiet window.
- **Serve people only a released copy.** A service that people use serves `release/` (a link to a versioned
  folder, switched by one atomic `mv -T`); the working folder runs on another port. Before this, every
  half-finished edit flew straight to a phone. A release is a script: it first runs all checks (proven by
  deliberately breaking the code: 11 of 12 passed, release refused), switches, then compares the live
  service's version and files with the released ones.
- **Server code is one copy for service and working folder**, so a server edit does not reach people without a
  restart, and the release step did not see that. The server exposes a fingerprint of its own code on a health
  endpoint; the release compares it with the file and restarts the service itself.
- **Hold your own CSS back from a release until it is accepted** (a hold file in the project; deploy takes the
  file from the previous release).
- **Service under one user, files created by another -> a write silently fails** if `except OSError: pass`
  eats it. After an agent creates files, `chown` them to the service user.
- **Behind a reverse proxy, testing against the app's own port does not show the proxy's limits.** Streams
  (mp3/SSE) need `proxy_http_version 1.1; proxy_buffering off; proxy_cache off; proxy_read_timeout 24h;
  proxy_send_timeout 24h;` plus `X-Accel-Buffering: no` from the server, or the proxy holds the bytes or
  cuts at 60 s. Proof is bytes per time window, not "200".
- **Relative paths everywhere** so the same site works at the root and under a prefix.
- Do not promise a human a `.local` name without trying it from their device (a phone failed to resolve it).

## 10. Page-level patterns that paid off

- **Settings the human changes by hand, with delayed writes:** a debounced write loses the last value on F5 or
  tab close. On `pagehide` send the unsaved value with `navigator.sendBeacon(url, new Blob([json],
  {type:'application/json'}))`; do not lose a change made before the first server response, send it after.
- **Frames from the human's real machine instead of "record a video":** the page logs each second of motion
  (frames/s, longest frame, time of its own parts) and long frames via `PerformanceObserver('long-animation-frame')`,
  and on `visibilitychange -> hidden` posts the JSON with `sendBeacon` to a drop endpoint that files it into
  the agent's inbox. The first log showed what headless cannot: on an integrated GPU, a per-frame
  `bufferSubData` into a buffer the GPU was still drawing from and a `clear(STENCIL)` between calls cost 25-70 ms.
- **An in-page benchmark on the human's machine** (a key opens it): draw N frames per variant, wait for
  `readPixels` each frame, post the result. It separated "the map is fast (6.7 ms)" from "the HTML label layer
  is re-rasterized on the same GPU".
- **An editor over the page for a person who does not take things in through words:** a mode by URL parameter,
  a panel with live-change buttons, the choice goes to the agent's inbox by `sendBeacon` on page hide. Add the
  panel to the list of UI selectors that must not pass clicks to the underlying canvas.
- **Design code as a page:** all styles in one object in the code; the document is generated from snapshots of
  the live page plus a verbatim copy of that object. The human writes the problem in words; the agent edits
  the object and the template together, not patches in place.
- **A reporting button** ("report a bug": POST of app state + canvas snapshot to a file) replaces describing
  a bug in words. Keep test reports in a subfolder.
- **Photos from other sites are copied at save time, not hot-linked.** One source dropped connections and the
  layout checker saw it as a network error on one width of four.
- **Barcode scanning in a browser:** a vendored decoder reads UPC/EAN/CODE-128; the camera works only on https
  or localhost, so always keep a manual entry field. Verify the decoder reads your own barcode without a camera
  (SVG -> canvas -> file scan).
- **Many small images = a slow first visit on a phone.** 1232 requests became one pack file (offsets and
  lengths in a header, frames -> `Blob` -> `Image`), version in the request name, `immutable` header.
- **Phone fullscreen:** `requestFullscreen` only from a user gesture; `screen.orientation.lock('landscape')`
  after entering fullscreen; automatic only for `pointerType === 'touch'`. Draw icons as SVG: the symbol
  font may lack emoji on the phone.
- **A game as a module on top of someone else's page:** one script, all in one function (the host page has
  top-level `const`s that would clash), data as JSON strings inside, styles injected into `<head>`, all
  selectors under one root id, and explicitly override the host's global `button/.btn/.row`. A fixed layer with
  `pointer-events:none`; only panels catch input; keys on `window` checking `e.defaultPrevented`.
- **Game logic separate from the page, data as JSON embedded in the HTML** (`<script type="application/json">`,
  `</` escaped as `<\/`); the same logic runs a thousand times in node as CI. The browser is only for looks.
- **A brand that does not exist yet goes in its own file** (colours + path to the mark) imported first in the
  main CSS; semantic variables point at it. When the logo arrives, only that file changes. A path in a CSS
  variable must be absolute (`url("/static/...")`): a relative `url()` inside `var()` is resolved from the
  wrong file.
- **Changing an existing page: work on the real page of the stand, not a prototype copy.** A prototype of a
  lot page had 43 lines of logic against the real 178, so the bid field, auto-bid and history vanished. The
  human's question: "why draw from scratch instead of taking the finished one and changing it?" Prototype only
  what does not exist yet.

## 11. Maps and heavy rendering (one site's long arc)

- **A city map without libraries:** boundaries and streets converted to metres and simplified in a builder
  (Python); on the page plain `<path>` in SVG with one `transform` per group and
  `vector-effect:non-scaling-stroke`. 178 districts + 625 street segments = 220 KB, smooth.
- **Icons and labels as a separate HTML layer over the SVG**, so their size does not depend on scale and text
  is crisp. Place labels greedily by importance over occupied rectangles.
- **Simplifying a closed outline:** Douglas-Peucker on a ring whose first point equals the last collapses it
  to two points; cut the ring at the farthest point and simplify the halves.
- **Pan lag (25-45 ms frames):** changing `transform` on an SVG group repaints every contour each frame. Fix:
  a layer larger than the window by 320 px, move only its CSS `transform` while dragging, repaint when motion
  stops or an edge nears. Remove `will-change` from hundreds of small elements and `filter:` on `:hover`
  contours; merge hundreds of background contours into one `<path>`.
- **Fading hundreds of labels with per-label `transition:opacity` forces a repaint of the whole layer.**
  Fade by group, hide single labels instantly. `will-change` on full-screen groups is worse (each becomes a
  layer). Find the cause by switching suspects off one by one (CSS injection in the perf script), not by guess.
- **Handlers on the `<svg>` only** leave areas where the moving overlay uncovers no svg, so dragging fails
  there. Put `pointerdown/move/up` and wheel on the whole scene with an exception for panels.
  `setPointerCapture` only after the finger moved a few pixels, or a click on an icon stops being a click.
- **Tilt/rotate like a strategy game:** a `#cam` wrapper with `perspective() rotateX() rotateZ()`, a flat map
  inside. Finger -> plane point through the same matrix (`DOMMatrix`, columns m11/m21/m41, m12/m22/m42,
  m14/m24/m44 = a 3x3 homography) and its inverse. Counter-rotate icons so they stand upright.
- **SVG -> WebGL2 when thousands of contours stutter on zoom.** Triangulate once (earcut), fill with one
  `drawElements`, colour in the vertex buffer, borders as instanced quads with pixel width, click = point in
  polygon on the CPU. No stencil-fan fill on winding coastlines. Headless Chromium uses a software
  rasterizer, so its frame times mean nothing: measure the main thread and give the human an on-page frame counter.
- Write a GPU buffer only when it changes (and `bufferData` instead of overwriting one the GPU is drawing from);
  no `gl.clear(STENCIL)` between calls; use an increasing stencil value instead.
- **HTML labels over a WebGL canvas pull on the same GPU.** A layer of 468 labels, triple the screen size,
  with blurry `text-shadow/box-shadow` is re-rasterized each frame. Make the layer screen-sized, replace blur
  with eight crisp 1 px shadows, use `will-change:transform` on each moving label (ready textures, composite only).
- **Or draw labels in WebGL too:** keep the DOM as an invisible skeleton (`visibility:hidden`) so text, layout,
  state classes and tests keep working; draw each label once into a 2D canvas atlas, place as instanced
  quads, fade in the shader. Click = nearest icon within 16 px, not "topmost". Resync the atlas after a state
  change that alters the look.
- **A WebGL canvas must be read right after drawing the frame** (same step: `render()` -> `drawImage`/`toDataURL`);
  after presentation the buffer is clear and a brightness/motion measurement returns zeros.
- **Layout checkers and moving content:** a label that slid off-window counts as clipped; hide labels that do
  not fit entirely and mark them as allowed. An element bigger than the window has no mark for the checker;
  leave the SVG window-sized with `overflow:visible`.

## 12. Rules of thumb that cost an evening each

- A batch of many point edits in a big file: one Python script where each replacement asserts it found exactly
  one place. ~70 replacements, none landed in the wrong place.
- A page the server serves live from disk is the production version at once. No copy for experiments: before
  telling people "refresh", run `node --check` on the last `<script>` and verify every `getElementById` has
  an element.
- A "read only" sample drawn by the same code as the editor, then every field disabled; otherwise one forgotten
  field silently corrupts data through a sample edit.
- A mobile header: metrics in a 2x2 grid next to the buttons, hide the title; header buttons >= 44 px.
- A scene with a screen-sized subtree: do not trust "looks calm" from a 4-second measurement; look at frames
  over a longer window.
- Do not "send both spellings of a field just in case" to someone else's API; a strict server rejects
  unknown keys.

## Appending to this file

Add a dated entry at the bottom (role, site, one to five lines): what you did, what worked, what you stepped
on, what you would tell the next agent. Pure code traps go in [`code-pitfalls/web.md`](../code-pitfalls/web.md).
