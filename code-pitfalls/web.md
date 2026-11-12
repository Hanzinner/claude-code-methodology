# web

### State is lost on refresh
- **Symptom:** after F5 a slider snaps back to its default, or a handler fires twice.
- **Why:** state lived only in the DOM/JS. A refresh is a clean DOM, so init takes defaults. An init that isn't idempotent binds listeners a second time.
- **Right way:** keep state in `localStorage` or the URL and restore it on init. Make init idempotent: a second call must not duplicate listeners.
- **Seen:** 2 agents independently, same week.

### Non-ASCII text turns into mojibake
- **Symptom:** garbage characters instead of non-English text.
- **Why:** the browser guesses the encoding because it wasn't declared early enough.
- **Right way:** `<meta charset="utf-8">` as the FIRST element in `<head>`.

### A timer-driven re-render loses expanded state and typed input
- **Symptom:** an expanded block collapses, focus and typed text vanish every N seconds.
- **Why:** the re-render rebuilds the DOM without preserving UI state.
- **Right way:** before re-rendering, save open/focus/input values; restore them after.

### `addEventListener` adds, it doesn't replace
- **Symptom:** a value jumps between two streams, in a random direction while moving.
- **Why:** "use the better source if available" was written as TWO subscriptions to one handler (e.g. `deviceorientationabsolute` + `deviceorientation`). The sources aren't equivalent (different zero), so their events interleave.
- **Right way:** feature detection is a fork: subscribe to the fallback in the `else`, not after. If you must choose at runtime, probe briefly, pick ONE source, and `removeEventListener` the other. Test with the real script in node against a faked DOM and events, plus a control run without the fix that must reproduce the bug.

### "Done", but the human still sees the old thing
- **Symptom:** the system reports `saved` / `applied`, the screen shows the old state until a reload.
- **Why:** a visible thing has two sides: the source of truth (disk, cache, settings) and what is drawn. The code updated the first. The cache invalidator was written but nobody calls it; nobody scheduled a redraw; `apply` wrote to settings but not to live state. Both halves return OK.
- **Right way:** any `apply` / `set_*` that changes something visible updates BOTH sides and, in the same commit, measures before/after on the display (screenshot or checksum), not the word "applied". For caches: grep for a call to the invalidator. A definition with no callers is dead.
- **Seen:** 3 different features in one day.

### The `hidden` attribute doesn't hide when your CSS sets `display`
- **Symptom:** an overlay/lightbox marked `hidden` is visible on load, a dark layer over the whole page.
- **Why:** `hidden` is just `display:none` from the browser stylesheet; any `#x{display:flex}` of yours overrides it.
- **Right way:** write `#x[hidden]{display:none}` explicitly, or globally `[hidden]{display:none!important}`. Screenshot the DEFAULT state, not only the opened overlay.

### `classList.toggle(cls, cond)`: `undefined` toggles instead of switching off
- **Symptom:** a button is "highlighted" with no state behind it, and flips after every redraw.
- **Why:** an `undefined` second argument means "no argument", so it's a plain toggle. `a === 'x' && s.fn` yields `undefined` when `s.fn` is missing.
- **Right way:** `toggle('on', !!(cond))`.

### Headless Chrome with `--virtual-time-budget`: `requestAnimationFrame` barely runs
- **Symptom:** in a scripted test a library (a lightbox/gallery) "sees" a drag (`isDragging=true`) but the image doesn't move. Zoom animations work, because they are CSS transitions.
- **Why:** in virtual-time mode rAF runs at about 1 frame/s; anything drawn in an rAF loop stands still.
- **Right way:** in the TEST copy of the page, before the libraries load: `requestAnimationFrame = cb => setTimeout(() => cb(performance.now()), 16)`. Count frames per second before hunting a bug in your code. Synthetic `PointerEvent`s are accepted by such libraries; they lock the drag axis on the first move, so drag along an axis that has room to move.

### Headless Chrome with `--virtual-time-budget`: CSS transitions stand still too
- **Symptom:** a layout measurement sees mid-animation state: a panel with `transition: transform` hasn't slid in, a transitioned `padding-right` keeps its previous value. Result: false "overlaps", extra padding, wrong column count.
- **Why:** same root as rAF. Animation frames barely advance in virtual time, so transitions don't finish while the script waits.
- **Right way:** in the TEST copy, put `<style>*,*::before,*::after{transition:none!important}</style>` first. Measure with `getBoundingClientRect()`, not `getComputedStyle(grid).gridTemplateColumns` (on a hidden tab it returns the template, not the layout). Give every run its own `--user-data-dir`, or `localStorage` leaks between runs.

### A test copy left in the directory the site serves
- **Symptom:** 12 hours later the site was still serving `_m.html`, a probe copy of a page with transitions disabled. Found by accident with a grep over all `*.html`.
- **Why:** a headless probe must open the copy from the same origin (so relative `api/...` calls work), so the copy goes into the served directory. Cleanup is a separate step that's easy to skip.
- **Right way:** one fixed name (`_probe.html`), overwritten each time and removed in the SAME command as the run. At the end, `ls <served-dir>/*.html` against the expected list.

### `@media` placed above the base rule silently loses
- **Symptom:** on a phone the desktop behavior stays (a sticky column with its own scroll) although the media query "turns it off".
- **Why:** equal specificity, so the rule that comes LATER wins. `@media(max-width:980px){aside{position:static}}` on line 863 and `aside{position:sticky;max-height:…}` on line 864.
- **Right way:** media queries go AFTER the base rules (end of the style block). In the media block reset everything that holds the behavior (`max-height:none;overflow:visible`), not one property. Check `getComputedStyle` at a narrow width.

### Sticky under sticky with a hardcoded `top:`
- **Symptom:** a second sticky bar (bulk actions) ends up completely hidden under the header after scrolling.
- **Why:** `top:64px` was computed for the header height on one screen. A header with `flex-wrap` grows to 113–290 px, and the bar's `z-index` is lower.
- **Right way:** one sticky wrapper containing both header and bar (the bar is then always below the header), or `top` from a measured height (`ResizeObserver` → CSS variable). Test: scroll, then `elementFromPoint` at the bar's center must return the bar.

### A page that writes state through GET: a headless run corrupts real data
- **Symptom:** after an automated screenshot, the app's "last opened file" is the test file.
- **Why:** on load the page sends `GET /api/last?set=<path>` (and `/api/settings?set=`). Any run without request interception makes a real write.
- **Right way:** in test runs intercept (Playwright route / CDP Fetch) every request with `?set=` and every non-GET, and compare md5 of the state files before and after. In new code, writes are POST only.

### `grid-template-columns:1fr` is stretched by wide content once `overflow` is removed
- **Symptom:** on a 390 px phone the page became 798 px wide and the cards are cut off on the right. This happened after a change that removed the inner scroll of a side column (`overflow:visible`).
- **Why:** `1fr` is `minmax(auto, 1fr)`: the column's minimum is the width of its widest unbreakable content (here a 738 px `pre`). While the column had `overflow:auto` the content hid in the scroll; without it, the content pushed the grid out.
- **Right way:** for a single column on a narrow screen use `minmax(0,1fr)`; give long `pre`/tables their own `overflow-x:auto`. After ANY CSS change run a layout check at several widths and both themes (e.g. 390, 768, 1280; dark and light) before handing over. `py_compile` is not a check.

### Someone else's site: a thread pool over all addresses hits one host in parallel and gets the IP banned for a day
- **Symptom:** `HTTP 429` on every request to a job-board host, even a single one after a pause; `error code: 1015` in the body, `Retry-After: 77030` in the headers.
- **Why:** the scanner spread boards over 8 threads. Several boards lived on the same host, so simultaneous requests from one IP got the IP blocked for 21 hours by the CDN. Retrying after 10–30 s against a ban of hours is pointless.
- **Right way:** limit per HOST, not per pool: one thread per host with a pause (a host → seconds map). On 429 read `Retry-After` first: seconds, wait; hours, store "banned until" in a state file, stay away until then, and show the reason in the report. Run a new collector's first pass sequentially.

### Two headless runs in one profile: the second starts from the state the first saved
- **Symptom:** a check scenario sometimes passes, sometimes shows a "defect" (an item "not bought" in a game shop, prices off). It passed without a screenshot and failed with one.
- **Why:** the runner took the screenshot and the result as two separate browser launches (`--screenshot`, then `--dump-dom`) with the same `--user-data-dir`. The page keeps state in `localStorage`. The first launch ran the scenario and saved the game; the second, the one whose output is read, started from that save. It surfaced the day the app gained save support.
- **Right way:** every browser launch in a test gets its own clean profile. If the page can save state, the scenario's first step checks that the start is clean (e.g. a `loadedFromSave` flag). A strange state at test start means ask "where did it come from" before "what broke in the app".

### Headless Chrome with `--virtual-time-budget` doesn't wait for a streamed read of a big file
- **Symptom:** after switching to one big file (20 MB, `fetch` + `body.getReader()` with a percentage display) no scenario starts: the page is frozen at "Images: 35%".
- **Why:** virtual time waits on an unfinished request but keeps running between stream chunks, so the budget runs out mid-download. A real browser doesn't do this.
- **Right way:** in test mode read the file in one piece (`arrayBuffer()`), and verify the real streaming path separately in real time by driving the browser over its remote-debugging port (Chrome `--remote-debugging-port` plus a websocket client, no Playwright needed).

### Porting logic from another language to JS: number truthiness differs
- **Symptom:** a warning like "reading a variable of a missing instance"; the "object is here" branch runs when there is no object.
- **Why:** in GameMaker `if (x)` is true for x > 0.5, so "none" (`noone` = −4) is false. In JS any non-zero number is true. A literal translation of `if (instance_position(...))` entered the branch with −4.
- **Right way:** don't patch places one by one. At build time wrap EVERY condition (if / while / `?:` and the parts of `&&` `||` `!`) in a function implementing the source language's truthiness (382 conditions in that port). The same applies to comparisons with a tolerance. Found by an automated scenario, not by a player.

### An image created by page code isn't ready for the automated screenshot
- **Symptom:** the picture is there in the game, but the headless screenshot shows a placeholder.
- **Why:** `new Image()` loads asynchronously, while the driven scenario runs and draws the last frame immediately.
- **Right way:** collect the load promises of your own images and start the scenario after them (a `ready()` hook in the page's main script).

### A driven game scenario gives different results per run despite a fixed random seed
- **Symptom:** the same scenario with `?seed=3` gets a customer with one order in one run and another in the next; the check flips between green and red.
- **Why:** two real-time inputs into a game that should be advanced only by scenario steps. (1) After loading, the engine started its own frame loop and managed an arbitrary number of frames while the scenario awaited a promise. (2) The game asks the browser's audio player "is the sound still playing" and draws random numbers based on the answer.
- **Right way:** in driven mode the own loop doesn't start at all (`boot({ driven })`), and everything time-dependent (sound, timers) is computed from a frame counter and measured durations. Repeatability check: the same scenario three times in a row, output must match verbatim.

### Behind nginx: testing against the app port doesn't see the proxy's limits
- **Symptom:** file upload works on `127.0.0.1:8000`, but through the real hostname everything over 1 MB gets `413 Request Entity Too Large`.
- **Why:** nginx has its own limits (request body 1 MB by default, read timeouts) and they sit BEFORE your server. Server tests and curl straight to the port never pass through them.
- **Right way:** run the acceptance probe through the same address people use (`curl --resolve name:443:127.0.0.1 https://name/...`), with data of a typical size (a file of several MB, not 17 bytes). When you accept uploads, set `client_max_body_size` in that site's block right away.

### An empty flex frame around buttons catches the pointer over a map
- **Symptom:** the map can't be dragged in a rectangle next to the buttons, although only the map is visible there.
- **Why:** the button container (flex, `align-items:flex-end`) is as tall as its tallest child. Above the shorter children is empty area that still belongs to the container. An exception like `e.target.closest('#dock')`, or a z-index above the map, makes that area dead.
- **Right way:** frame `pointer-events:none`, visible children `pointer-events:auto`. Verify by sweeping the scene with an `elementFromPoint` grid, not by clicking a few chosen points.

### Parsing font size from a `font` string with `/(\d+)px/`: a fractional size is read as its tail
- **Symptom:** the page hangs with no console error.
- **Why:** `parseFloat(/(\d+)px/.exec('italic 36.369999999px')[1])` returns 999999999: the regex catches the digits after the dot. The label height came out in trillions of pixels, and a loop over collision-grid cells became effectively infinite.
- **Right way:** `/([\d.]+)px/`, and round the font size before composing the string. How the hang was found without an error: CDP `Debugger.pause` 10 s after load → stack, then `Debugger.evaluateOnCallFrame` on the variables.

### earcut on a valid outline lays a triangle over others: a light/dark wedge in the fill
- **Symptom:** polygons built from grid cells (combs of 1–3 m gaps between cells along roads, loops after simplify and rounding) get overlays up to 100,000 m² when triangulated with earcut. Even an outline valid by shapely can be cut wrongly.
- **Right way:** before saving, apply the even-odd rule, then `buffer(2).buffer(-2)` (mitre), then remove loops after rounding. On the page, after earcut, compare the triangle area sum with the outline area. If they differ by more than 0.2 %, re-cut from another start vertex (8 attempts). Check: a node replica of triangulate plus shapely, sum of triangle areas minus area of their union = 0.

### Someone else's API: "send both spellings of the field just in case" can make the server reject unknown keys
- **Symptom:** after a "safe" change every request returns `400 Unrecognized key`. The test is green because HTTP is mocked in it.
- **Right way:** one spelling, plus a switch on the server's concrete rejection. After any change to a request, make ONE real request and look at its output before the word "done".
- **Cost:** 4 days with no results from a scheduled pipeline.

### An inline `<script>` shares the global scope with the shared `app.js`: a same-named `const` kills the whole script
- **Symptom:** a prototype page is empty; the console says `SyntaxError: Identifier 'pct' has already been declared`; the blocks the script draws never appear.
- **Why:** top-level `const`/`let`/`function` in classic (non-module) scripts share one scope per page. The shared `app.js` already had `pct` and `offPct`; a second `const` is a parse error, so not one line of the inline script runs. It happened twice in 5 minutes (renamed to `offPct`, and another agent had just added the same name).
- **Right way:** before a new top-level name, `grep -n "name" static/app.js`. Wrap page code in `(() => { … })()` or prefix it with the page name. Take shared logic (here a discount rule) from the shared file's function instead of duplicating it. Verify with the layout check's JS-error output, not only a screenshot.

### A proxy "for checking pages behind a login" drops security headers: the CSP doesn't apply, inline scripts "work"
- **Symptom:** a page behind login passes the layout check but is empty for a human running the same code. The auth proxy (it injected a cookie for headless Chrome) forwarded only `Content-Type`/`Cache-Control`. `Content-Security-Policy: script-src 'self'` was lost, so the prototype's inline `<script>` ran only under the tool.
- **Right way:** the proxy forwards ALL response headers except hop-by-hop ones (`Content-Length`, `Transfer-Encoding`, `Connection`). Control check: a page with an inline script under the proxy must break exactly as it does directly. A designer's staging without a CSP also hides this, so compare headers with production (`curl -sI`).

### html5-qrcode in a frame with `video{position:absolute;inset:0;100%}`: the reader is 0×0, the camera "works" but reads nothing
- **Symptom:** the viewfinder is black, an exception `minimum size of 'config.qrbox' dimension value is 50px`, no barcode is read. The camera stream exists (`videoWidth 720`), so "camera started" checks pass.
- **Why:** the library gives its container inline `position: relative`, which becomes the reference for the absolute `<video>`. The container is a flex child without a size, so 0×0; the video is 100 % of zero; `qrbox(w, h)` is called with 0×0.
- **Right way:** give the reader container the frame's size (`#reader{position:absolute!important;inset:0}` or explicit width and height). Feed the camera from a video containing a barcode (`--use-file-for-fake-video-capture=*.y4m`; not mjpeg, which gives black frames) rather than calling the handler around the camera.

### FastAPI ≥0.118: a `yield` dependency closes AFTER the response is sent, so a commit in `get_db` is late
- **Symptom:** the browser got "ok", and the next request sees old data; a commit failure (SQLite locked) is invisible to the user. Tests with `TestClient` are green because it waits for the app to finish.
- **Why:** since 0.118 the exit code of a `Depends` with `yield` runs by default (scope="request") after `http.response.body`.
- **Right way:** `Depends(get_db, scope="function")` (exit before the response) or an explicit `s.commit()` in every route that writes. Test at the ASGI level: on `http.response.start` inside `send`, re-read the database.
- **Found by:** an end-to-end test during an upgrade from 0.115 to 0.159.

### A CSS variable that JS fills from an element's measurement, while the same element reads it as `min-height`: a growth loop
- **Symptom:** the header grew to 5000+ px on the staging site.
- **Why:** a ResizeObserver wrote the header height into `--hdr-h`, and the header's inner element had `min-height:var(--hdr-h)`. Without the staging banner the measurement equals min-height and is stable. With the "TEST SITE" banner (a `::before` adding 23 px) each measurement is larger than the last.
- **Right way:** write the measurement into a variable the measured element does NOT read (or make the min-height a constant). Measure on staging with all overlays (the banner), not only on a clean page.

### SVG in CSS via a `data:` URI with double quotes inside `url("…")`: the icon becomes a solid square
- **Symptom:** a `mask-image` from `data:image/svg+xml` draws a filled square instead of an icon; the check "mask-image ≠ none" passes.
- **Why:** SVG attributes in double quotes (`d="…"`) terminate `url("…")`. The mask fails to parse and the element keeps its `currentColor` background without a mask.
- **Right way:** inside `url("…")` use single quotes in the SVG (or `%22`). Verify that each `data:` URI actually loads as an Image (`onload`, `naturalWidth > 0`), not just that the property is set.

### A `//` comment inserted by a script swallows the rest of a JS line
- **Symptom:** after an edit the page is "alive" but buttons are dead: either a `SyntaxError` at load, or (worse) a runtime `ReferenceError` like `b is not defined`, because the `const b = …` declaration ended up inside a comment.
- **Why:** the replacement anchor ends in the MIDDLE of a line, and the replacement puts `// explanation` after the code. Everything that followed in the original line is now a comment. `node --check` catches only broken syntax; if a whole declaration was swallowed, the syntax is valid. The same happens in minified one-line JS: a script appended `// note` after `function f(n){` and the code after it (`const evs=…`) was disabled; a static page test stayed green and the error appeared only in the state that calls the function.
- **Right way:** in a replacement put a comment on its OWN line above the code, never as a tail, unless the anchor reaches `\n` (or use `/* … */`). After editing JS, run a scenario in a browser that reaches the changed function, not only `node --check`. Page `catch` blocks must not hide errors silently (show them in the UI and `console.error`).
- **Mirror case (twice in one night):** an INSERTION after an anchor that ends before an OLD trailing comment (`x = y;   // note`) puts the new code between the code and its comment, and the comment moves to a new line. Syntax is intact, `node --check` is silent, only a human eye on the output catches it. Anchor insertions to the end of the line (`…;\n` including the comment), not to the `;`.
- **Related:** reassigning a `const` (`dest = null` with `const dest`) is also runtime-only and caught only by a scenario.

### A "show" rule loses to a "hide" rule of equal weight when it sits earlier in the file
- **Symptom:** diagram lines were hidden for a day and nobody noticed, because the layout check didn't test line visibility.
- **Why:** `#svg:not(.allE) path.e:not(.hl){display:none}` and `#svg.schE:not(.allE) path.e{display:inline}` both have specificity (1,3,1). The "show" rule came first, so it lost.
- **Right way:** compute the specificity of both, or put `!important` on the exception. In the test run, add a state that fails if `getComputedStyle(path).display==='none'` where the lines must be visible.
