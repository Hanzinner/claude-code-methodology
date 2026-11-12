# python

### Inserting into markdown by substring search
- **Symptom:** the text landed in the header's instructions, a heading was torn in half, someone else's entry ended up under your heading — and the script "succeeded".
- **Why:** `s.index('## New')` finds the FIRST occurrence, often in a header where the instructions quote their own structure (in backticks, in an explanatory line); an anchor prefix `## 2026-07-27` also matches `## 2026-07-27 (Agent, …)`; under a bare heading sits someone else's text.
- **Right way:** `re.search(r'^## New\s*$', s, re.M)` — an exact line from its start; `assert` the match count == 1; look at what comes AFTER the anchor before replacing; after writing, compare other sections against git (md5). In shared files use your own signed heading. A shared inbox is written only through its sanctioned poster/closer scripts.
- **Seen:** 6 times across 5 agents.

### Anchor not found → silent no-op; replace before validation
- **Symptom:** the script reports no error, yet a task vanished from both files / a block was cut out and inserted nowhere.
- **Why:** the heading in the target differs (`## Open` vs `## Open loops`) or the section is gone → the insert did nothing; `os.replace` ran BEFORE post-validation.
- **Right way:** check the target's structure BEFORE anything destructive; anchor not found → a loud error; `os.replace` is the last step, after the tmp file is verified; read the result back after writing.
- **Seen:** 2 times (a git snapshot saved one).

### `str.splitlines()` on jsonl
- **Symptom:** a validator sees "broken" lines that don't exist → false ABORTs.
- **Why:** `splitlines()` splits not only on `\n` but on Unicode line separators inside JSON strings.
- **Right way:** `s.split("\n")`.
- **Seen:** once.

### Your own file named like a stdlib module
- **Symptom:** the import of a standard-library module breaks strangely.
- **Why:** `tools/inspect.py` shadows stdlib `inspect` for everything imported from that directory.
- **Right way:** never name files after stdlib modules (`phone_inspect.py`, not `inspect.py`).
- **Seen:** once.

### `terminate()` on a wrapper leaves an orphaned grandchild
- **Symptom:** after a "stop" the process is alive and holds a port.
- **Why:** under `taskset` or another wrapper the direct child is the wrapper and the real process is its child; `terminate()` kills only the wrapper; an external `kill` kills python before `finally` runs.
- **Right way:** `Popen(..., start_new_session=True)` + `os.killpg(os.getpgid(p.pid), SIGTERM)`; your own SIGTERM handler that cleans up the group.
- **Seen:** once.

### python-docx: Word ignores column widths
- **Symptom:** all columns are equal, words break in the middle in the narrow ones.
- **Why:** `cell.width` writes `w:tcW`, but Word/LibreOffice take the layout from `w:tblGrid`, which python-docx doesn't update.
- **Right way:** `table.autofit=False` + `w:tblLayout type=fixed` + widths in `tblGrid/gridCol` (twips, 1 cm = 567) + in the cells. All three are needed.
- **Seen:** once.

### python-docx: "landscape" stays portrait
- **Symptom:** the landscape flag is set, the page is portrait.
- **Why:** `sec.orientation` only sets a flag; it does not change the page size.
- **Right way:** swap `page_width` / `page_height` by hand; check the sum of column widths against the working width (page − margins) BEFORE saving.
- **Seen:** once.

### python-docx: Cyrillic comes out in a different font
- **Symptom:** part of the text is in another font.
- **Why:** Word reads a separate attribute `w:eastAsia` for some character ranges, and `run.font.name` does not set it.
- **Right way:** additionally `run._element.rPr.rFonts.set(qn("w:eastAsia"), FONT)` (and for the `Normal` style).
- **Seen:** once.

> A generated document is always rendered to PNG and looked at before it goes out — see [`verification.md`](verification.md).

### python-telegram-bot: a timeout on an album → a retry makes a duplicate in the group
- **Symptom:** `send_media_group` fails with `Timed out`, the code retries — the group now has two albums (the first without a caption).
- **Why:** the default `read_timeout` is ~5 s; Telegram takes longer to accept 4 photos — the message was already delivered while the client believes it wasn't. The retry is not idempotent.
- **Right way:** `send_media_group(..., read_timeout=90, write_timeout=90)`; retry after a timeout only when you know for certain nothing went out.
- **Seen:** once.

### `Path.rename` on Windows doesn't overwrite an existing file
- **Symptom:** code that ran for years on Linux fails on Windows with `FileExistsError: [WinError 183] Cannot create a file when that file already exists` on `f.rename(f.with_suffix(".no"))`.
- **Why:** on POSIX `rename` quietly replaces the target; on Windows it doesn't. It triggers when the same file is processed a second time (a judge re-scored a candidate → a new `.json` next to the old `.no`).
- **Right way:** `f.replace(target)` — replaces on both OSes. Search for every `.rename(` in code that may run on Windows.
- **Seen:** once — a run crashed right after start, twice.

### An identity key taken from an LLM response
- **Symptom:** a record, message or button is tied to an "almost the same" key: `@name` instead of `name`, different case, a space. Data quietly goes to a non-existent object.
- **Why:** the model returns the key field (a handle, id, path) in its own format. It mostly copies exactly, so the hole stays hidden for a long time.
- **Right way:** take the key from your own data (the folder name, the database id) and overwrite the model's key field right after parsing. For data already stored — normalize on input (`lstrip("@")`) wherever the key comes back from outside (buttons, callbacks).
- **Seen:** once (a card in a chat whose buttons pointed at `@name`).

### Incremental API fetching with back-to-back windows loses late-arriving records
- **Symptom:** the fetcher works, rc 0, "N new" — but some records that exist in the API are never in your data. Visible only by a direct query for the same period.
- **Why:** the API's after/before filter is often on the time of the EVENT (published, created at the source), while the record appears in the database later. A window [last success, now] with no overlap skips everything published before the boundary but indexed after it.
- **Right way:** a window with overlap (after = last success − margin, margin ≥ the measured delay with some headroom) + idempotent dedup by record identity (id, or key + event time). Measure the delay on your own data: the difference between the "event" and "appeared" fields.
- **Seen:** once.

### A frequent cron that re-reads whole log files grows with the data
- **Symptom:** VM load up to 26–30, hooks fail on a 20 s timeout; a quota script under cron `*/1` took ~10 s of CPU and piled up (5 copies).
- **Why:** an mtime cutoff doesn't help: active transcripts are tens of MB, and every run read them from the start (twice, even). When it was written the files were small — "it worked".
- **Right way:** for append-only logs use a read-ahead cache: remember the inode and the byte offset read so far (complete lines only); the next run reads the tail; a shorter file or another inode → start over. Compare the numbers of the new and old version at the same moment (11.6 s cold → ~1 s warm, identical output). Give the cron `flock -n`.
- **Seen:** once.

### A mass replace of "marker line → new line" erases the text around the marker
- **Symptom:** whole paragraphs vanished from 5 of 49 entries.
- **Why:** the marker (a status) sometimes sat in the middle of a long paragraph, and the replacement took the whole line.
- **Right way:** before a mass replace, select all target lines and check they are of one kind (`startswith`, length); replace only the fragment, not the line; afterwards read the diff, not a counter.
- **Seen:** once.

### `open(f, 'r+').write(text)` doesn't truncate: a shorter text leaves the old tail
- **Symptom:** after replacing a line with a shorter one, 2–3 stray characters appear at the end of the file; Python raises IndentationError.
- **Why:** `r+` overwrites from the start and does not shorten the file.
- **Right way:** `fh.truncate()` after writing, or `open(f,'w')` (the owner and mode of an existing file are NOT changed by it — `r+` isn't needed for that). After a scripted edit: `git diff --numstat` and a syntax check.
- **Seen:** once.

### shapely: "grow +ε → union → shrink −ε" can collapse a polygon to nothing
- **Symptom:** the trick for merging neighbours without slivers (`unary_union([a.buffer(.05), b.buffer(.05)]).buffer(-.05)`) gave 0 m² instead of 8795 m² on some outlines in GEOS — a cell silently vanished, a hole on the map.
- **Why:** a numerical degeneracy in GEOS on particular shapes.
- **Right way:** compare with a plain `unary_union(...).buffer(0)` and take it if the area dropped by more than 1 %; at the end of the pipeline add a check "what of the land/road is left without a cell". Also: land inflated by 1 cm and not clipped to the frame after the buffer leaves a centimetre strip along the edge that glues all edge pieces into one cell — clip to the frame AFTER the buffer.
- **Seen:** once.

### A long parallel run (`Pool.map`) with no chunk cache and a collapse on one failure
- **Symptom:** 25 min of slicing on 4 cores, one tile raised GEOSException "Ring edge missing" → `pool.map` raised → all finished results in memory were lost.
- **Why:** `Pool.map` re-raises the first worker exception and drops everything else; nothing was persisted.
- **Right way:** a run longer than ~5 min — each chunk writes its result to disk (key: input + hash of the code) and reads it back on restart; the chunk wrapper catches the exception and returns "failed" into the report instead of killing the pool; have a way to run one chunk alone (reproduce the failure in seconds). For shapely: `shapely.union_all(make_valid(...), grid_size=0.001)` for a robust union.
- **Seen:** once.

### Smoothing by shrink/grow (`buffer(−r).buffer(+r)`) cuts narrow necks and makes islands
- **Symptom:** in the source data every alley was attached to streets, but after slicing 47 of 336 became islands and 61 vanished: a 2 m shrink cut every neck narrower than 4 m. Conclusions about connectivity drawn on the smoothed geometry are about the smoothing, not the data.
- **Why:** shrinking by r removes every feature narrower than 2r; growing back doesn't restore the connection.
- **Right way:** measure connectivity/topology on the raw data; smooth only the edge of a wide shape (or protect narrow parts separately); after smoothing, count how many objects changed connectivity.
- **Seen:** once.

### "Even-odd" rings read as "first is the outline, the rest are holes" lose 86–92 % of the area
- **Symptom:** blocks from a data file (rings of several parts and holes mixed) read via `Polygon(rs[0], rs[1:])` gave 31 km² instead of 226 — and the indexes/districts built from them were assembled from scraps.
- **Why:** the data was written with the even-odd rule, the reader assumed another convention.
- **Right way:** read with the same rule it was written with (`from_rings`: symmetric_difference of the rings); after reading, compare the sum of areas with the source.
- **Seen:** once.

### An audit-log write before `raise HTTPException` disappears with the rollback
- **Symptom:** a refusal ("attempt to bind someone else's card") left no trace in the audit log — exactly the entries a security log needs most.
- **Why:** a FastAPI dependency `get_db` does `rollback()` on any exception; `audit(...)` + `raise HTTPException(409)` → the audit row was rolled back with everything else. A test that looked for the record after the refusal caught it.
- **Right way:** a separate `audit_refusal()` — `add` + `commit()` BEFORE the `raise`. A test for every refusal path: after a 4xx the log entry exists.
- **Seen:** once.

### A moved venv is dead: scripts remember the absolute path
- **Symptom:** a service in a crash loop `status=203/EXEC … venv/bin/uvicorn: No such file or directory`, although the file is there.
- **Why:** `python -m venv X` writes `#!X/bin/python` into every `bin/*` script; the venv was built in `rel.part/` and renamed to `rel/` — the shebang points at a non-existent interpreter, and the kernel reports ENOENT about the script itself.
- **Right way:** create the venv where it will live; get "atomicity" from a readiness marker (`.complete`) or a symlink to the finished directory, not from `mv` of the venv itself. Proof: run `venv/bin/<script> --version` after the build.
- **Seen:** once (found in a drill on a clean Debian 13).

### A deferred import inside a function after a refactor — a 500 only at request time
- **Symptom:** after splitting a big module, `python -c "import app.main"` and most tests are green, while one route returns 500.
- **Why:** `from .main import NO_PASSWORD` sits inside a function (to dodge an import cycle); the name moved to another module and wasn't re-exported. Importing the module doesn't execute it; only the call breaks.
- **Right way:** after moving code, `grep -rn "from .main import\|from . import main" app/` and check every name (`python -c "import app.main as m; m.X"`); better, import from the owning module, not from the aggregate. Mechanized: a test that walks `app/*.py` with `ast` and requires every `from .main import X` / `main.X` to exist in `app.main`; a deliberate sabotage (an invented name) turns it red with file and line. Ruff F821 doesn't catch this — the import is syntactically valid.
- **Seen:** 2 times (a red test deploy).

### SQLite: rebuilding a table with foreign keys on cascades and erases child rows
- **Symptom:** a migration that changes a column (Alembic batch / "create new → copy → DROP old") — after the commit the child rows (bids with `ON DELETE CASCADE` on lots) are gone.
- **Why:** `DROP TABLE` in SQLite with `PRAGMA foreign_keys=ON` performs an implicit DELETE and fires the FK actions.
- **Right way:** `PRAGMA foreign_keys=OFF` for the duration of the migration (outside a transaction, on the connection); before the commit `PRAGMA foreign_key_check` → an error = rollback. Keep a test: `test_sqlite_table_rebuild_keeps_child_rows`.
- **Seen:** once.

### Alembic doesn't see CHECK constraints; batch `copy_from` loses indexes
- **Symptom:** `alembic revision --autogenerate` / `compare_metadata` say "matches" although the model has new CHECKs; after `batch_alter_table(copy_from=…)` the table's indexes are gone.
- **Why:** autogenerate doesn't compare CHECKs at all; batch with `copy_from` creates the table from the passed Table and doesn't recreate indexes separately.
- **Right way:** CHECKs get their own test "CHECK names in the database = in the model" (`inspector.get_check_constraints`) and the migration is written by hand; after a batch rebuild, compare the schema again and recreate indexes from the reference. Also: a `naming_convention` in MetaData BEFORE the first migration — otherwise SQLite constraints are nameless and a migration can't drop them.
- **Seen:** once.

### A hash from `repr()` of a set drifts between runs
- **Symptom:** `sha256(json.dumps(repr(snapshot)))` with a `set` of strings in the snapshot — the same database gave different fingerprints in different processes.
- **Why:** the iteration order of a `set`/`frozenset` of strings depends on `PYTHONHASHSEED`, which is random per run; `sort_keys` sorts only dict keys.
- **Right way:** canonicalize before hashing — sets → `sorted(...)`, recursively, only then `json.dumps`. Check: the same fingerprint in ≥2 separate processes (only a cross-process run catches it, not two calls in one).
- **Seen:** once.

### python-telegram-bot: `BadRequest` is a subclass of `NetworkError` (and chunking by characters breaks HTML)
- **Symptom:** retry logic "NetworkError → retry, everything else → skip" retries "Chat not found" / broken HTML forever; one such reply blocks the whole send queue.
- **Why:** in PTB `telegram.error.BadRequest(NetworkError)` — checked: `issubclass(BadRequest, NetworkError) → True`; `Forbidden` and `RetryAfter` are not. Separately: `RetryAfter.retry_after` must be waited out (int or timedelta), or the ban continues.
- **Right way:** transient = `isinstance(e, RetryAfter) or (isinstance(e, NetworkError) and not isinstance(e, BadRequest))`. Cut long text BEFORE converting to HTML (by lines, count the limit in UTF-16: an emoji = 2), each piece → HTML separately; cutting finished HTML by characters splits a tag → BadRequest. Don't send an empty chunk ("Message text is empty").
- **Seen:** once (found in a 10-round cross-review).

### A nested `conftest.py` shadows `from conftest import X` in tests
- **Symptom:** after adding `tests/db/conftest.py`, a test with `from conftest import make_user` failed at collection: "cannot import name 'make_user' from 'conftest' (…/db/conftest.py)".
- **Why:** pytest (rootdir/prepend) imports every conftest as a module named `conftest`; whichever is first in `sys.modules`/`sys.path` answers the import.
- **Right way:** shared code for a subfolder goes into a separate module with its own name, not conftest; after adding any conftest, run `pytest --collect-only` over all tests.
- **Seen:** once.

### A subprocess started in a test outlives the test if `setUp` fails
- **Symptom:** a test starts a server with `Popen` in setUp and stops it in tearDown. The start dragged on (busy machine) → setUp raised → tearDown is not called → the server lives forever and eats CPU (7 orphans, load 20, other work on the machine slowed down).
- **Why:** unittest skips tearDown when setUp raises.
- **Right way:** in `Popen(preexec_fn=...)` call `prctl(PR_SET_PDEATHSIG, SIGTERM)` via ctypes (`libc.prctl(1, signal.SIGTERM)`) — the child dies with the test run; on a failed start `p.kill()` BEFORE the raise. Check after a run: `pgrep -f <tag of the temp dir>` = 0.
- **Seen:** once.

### Inserting a line after the first substring match (`from app import`) puts it inside a function
- **Symptom:** a script inserted `from app.config import …` right after the first `from app import` in a tool file — that one was inside the body of `def seed()`, the line landed without indentation → a syntax error. pytest doesn't see it (the file isn't imported by tests); the package's ruff gate failed.
- **Why:** a substring match doesn't know about nesting.
- **Right way:** insert after a top-level anchor (a line with no indentation) or edit with the Edit tool and visible context; after any mass edit run `ast.parse`/ruff over the changed files, not only pytest.
- **Seen:** once.

### SQLAlchemy: `MetaData.reflect(only=[...])` also pulls in the tables these reference
- **Symptom:** dropping a few tables — `md.reflect(conn, only=gone)`, then `for t in reversed(md.sorted_tables): t.drop(conn)` — also dropped `users`. Reflection added the parent table through the FK, and the loop dropped it too (caught by an adoption test: KeyError 'users' on the next step).
- **Why:** `only=` selects the named tables but reflection follows foreign keys to their parents.
- **Right way:** `if t.name in gone` in the loop; never run drop/delete over the whole `sorted_tables` of a reflected MetaData.
- **Seen:** once.
