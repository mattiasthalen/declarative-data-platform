# Judged checks for S1

Two edge cases are judged at review rather than run. The reviewer reads the
generated output and the code, and records pass or fail for each line below.

## EC6: two loads at one PositedAt

Two loads that share a `_dlt__extracted_at` and carry different values for one
version (same product, same attribute, same ChangedAt) are two assertions of one
version by one positor at one PositedAt. The build fails on that contradiction
([8]). It does not pick one.

Pass when all of these hold:

1. The generated Anchor load SQL (the integrate posit/annex models, or the
   macros they call) detects more than one distinct value for one
   (PR_ID, attribute, ChangedAt, PositedAt, Positor) among the rows it is about
   to assert.
2. On that condition it raises: a DuckDB `error(...)`, a failing cast, a
   uniqueness or primary-key violation, or a dbt `raise_compiler_error` or
   error-severity test that stops the integrate models from committing. The
   build exits non-zero.
3. No `qualify row_number() ... = 1`, `any_value`, `max`, `min`, `first`,
   `last`, `arg_max` or `distinct on` picks a winner among such rows before
   that check runs. Deduplication of rows that are identical in value is fine.
4. Loads with different `_dlt__extracted_at` still apply oldest first. The check
   in (1) groups by PositedAt, so it does not fire for EC2's two loads.

## EC8: two builds on one target at once

DuckDB lets one writer hold a database file. A second `dbt build` on the same
target fails to open the file and changes nothing. We accept this and add no
locking of our own ([19]).

Pass when all of these hold:

1. No lock files, PID files, advisory locks, retry loops or waits on the
   DuckDB file appear in `src/`, `macros/`, the Taskfile or `profiles.yml`.
   Search for `lock`, `flock`, `fcntl`, `portalocker`, `filelock`, `.pid` and
   `retry`.
2. Nothing catches the DuckDB `IOException` ("Could not set lock on file") and
   swallows it or turns it into a success. The second `dbt build` exits
   non-zero with DuckDB's own message in its output.
3. Optional live confirmation: start `uv run dbt build --target dev`, and while
   it runs start a second one in another shell. The second fails with the lock
   error. The first completes and the load log shows one batch for it.

# Judged checks for story #12

## No rule stated twice (AC4, AC5, AC6)

The six files are the root `CLAUDE.md` and `.claude/rules/{ingest,conform,integrate,serve,uss}.md`.
The reviewer reads all six and `main`'s `CLAUDE.md` (from before the story), and records pass
or fail for each line below with the table that supports it.

Pass when all of these hold:

1. **One home per rule (AC4).** List every rule stated in the six files, one row each, with
   the file that states it. A rule is a constraint on how work is done, whatever its
   wording: a reworded or partial restatement in a second file counts as the same rule.
   Fail on any rule that appears in two files. A pointer that only names another file
   ("see `.claude/rules/integrate.md`") is not a rule.
2. **Layer files hold only their layer (AC4, AC6).** No rules file states something true of
   every layer (generated output is committed, `__` separates concerns, one `dbt build` per
   target, how to prove a change, read-first documents): those live in the root `CLAUDE.md`.
   Each rules file states only what holds for files matching its own `paths:`. `serve.md`
   states nothing specific to the USS (bridges, relationship steps, ghost rows), so it does
   not mislead a hand-written serve model; `uss.md` holds those.
3. **Every rule links its ADR (AC6).** Each rule in a rules file that an ADR decided links
   that ADR (by number, as a link into `docs/adr/`). A rule with no deciding ADR is fine
   unlinked; name it in the table so the reviewer's claim that no ADR exists is visible.
4. **Nothing lost (AC5).** Map each bullet and each sentence-level rule of `main`'s
   `CLAUDE.md` to its row in the table from (1). Fail on any that has no home. The one
   permitted loss is the reference to Lars Rönnbäck's anchor-snowflake-skill;
   `docs/ANCHOR.md` in Roenbaeck/anchor stays the integrate reference.
   `! grep -rn anchor-snowflake-skill CLAUDE.md .claude/` exits 0
   (`tests/test_rules_files.py` also checks this).
5. **The router routes.** The root `CLAUDE.md` says that the layer rules live in
   `.claude/rules/` and load by path, so a reader of the root file knows where the rest is.

# Judged checks for story #17 (ingest declared)

Two acceptance criteria of story #17 are judged at review. The reviewer reads the
files named and records pass or fail for each.

## AC18: the business question on TransactionHistories

`sources/adventure_works/transaction_histories.yaml` records the approved business
question (design tree B9, Mattias 2026-10-31) in a comment block.

Pass when all of these hold:

1. The question is there word for word: "What is the total quantity of units sold
   per calendar month and product line?"
2. The block states each part of its anatomy: aggregation sum; measure `Quantity`;
   dimensions calendar month and product line; time every month the source holds
   (2013-07..2014-08).
3. The block carries the three definitions, in B9's words:
   - sold = TransactionType `S` (74,575 rows; `W` work orders and `P` purchases
     are not sales);
   - calendar month = month of `TransactionDate` (business date, not ModifiedDate
     or extraction);
   - product line = the product's line as of the transaction date, trimmed code,
     empty its own group.
4. Nothing in the block contradicts B9 or adds a definition B9 does not make, and
   the comment is a comment: the file still parses to the same dlt resource entry
   with it removed.

## AC20: the docs drafted in the design interview

The run folder's `docs/` (`doc-changes.md` and `adr/`) holds the drafts. Compare
the repo against them.

Pass when all of these hold:

1. `docs/adr/` holds ADR-0016 to ADR-0019 with the drafts' title, status, context,
   decision, rejected alternatives and consequences. Renumbering after a collision
   with a parallel story is fine when the links follow. A wording change is fine
   only where the build proved a draft wrong (the plan names ADR-0019's
   consequence sentence on repeats at the cursor boundary); it says what changed.
2. `docs/adr/README.md` has the four index rows.
3. ADR-0001 and ADR-0012 each end with the drafted `## Addendum 2026-10-31`, and
   their original text is otherwise unchanged.
4. `docs/lexicon.md` has the entries *source* and *resource* as drafted, and no
   other entry changed.
5. `docs/assumptions.md` has A12 and A13 as drafted (drafted as A7 and A8, renumbered after collisions), and the measured facts of
   2026-10-31 (the `$filter`/`$orderby`/`$top`/`$select`/`$count` support and the
   TransactionHistories row counts and date range).
6. Nothing in the repo's docs still says resources are declared in Python or that
   contracts sit flat in `contracts/*.yaml`.

# Judged checks for story #16

Two acceptance criteria of the scheduled run are judged at review rather than run. The
reviewer reads the evidence and the README, and records pass or fail for each line below.

## AC13: the schedule fires on its own, live

On a local Prefect server and process worker, with the real feed and the real
`task ingest:source`, `run` fires on its schedule at the top of an hour without being
triggered by hand, every source lands, `build` is green and `run` ends Completed ([4], [8]).

Pass when all of these hold:

1. The evidence shows the `run` flow run's scheduled start time equal to its expected
   start time, and that time is on the hour (hh:00:00) in UTC.
2. The run was created by the scheduler, not by hand: its `auto_scheduled` flag is true,
   or its creator is the scheduler service, and nothing in the evidence shows a
   `prefect deployment run`, a UI "Quick run" or an API `create_flow_run` call for it.
3. Its children are one `ingest-source` flow run per listed source and one `build` flow
   run, each with this `run` as parent, and every one of them ended Completed.
4. `run` itself ended Completed.
5. The `build` flow run's log, `task build`'s output, shows `PASS` for every node it
   ran, a final `ERROR=0`, and no `ERROR` line anywhere.
6. The ingest that ran was the real one: the `ingest-source` runs used the default
   command (`uv run task -x ingest:source -- <source>`), not a fake or an override.

## AC18: the README says how to run the schedule

The README's "Run it" section says how to run the schedule locally and what the infra
must provide: the server, the work pool name in the environment, and the repo as working
directory.

Pass when all of these hold:

1. A reader who has never used Prefect can, from the README alone, start a local server
   (`orchestrate:server`), start a worker (`orchestrate:worker`) and deploy
   (`orchestrate:deploy`), in that order, and knows which environment variables to set
   first and to what: `ORCHESTRATE_WORK_POOL`, and the Prefect API URL wherever the
   tasks do not set it themselves.
2. It says which parts the infra owns (the Prefect server and its state store, the work
   pool and its workers, the pool's name in the environment, a working directory holding
   the repo) and which the repo owns (`orchestrate/prefect.yaml`: what runs, when, the
   concurrency limits and timeouts; `orchestrate/flows.py`).
3. Every command it gives exists: each task appears in `uv run task --list`, and each
   variable it names is one the deploy or the worker reads.

# Judged checks for story #25 (seeded change simulator)

Three rows of story #25 are judged at review. The reviewer reads the files named and
records pass or fail for each line below.

## AC9: `task simulate`

`tests/simulate/test_simulate.py::test_cli_surface` runs `uv run task --list` and
`uv run simulate --help`. The reviewer reads the Taskfile.

Pass when all of these hold:

1. `Taskfile.yml` has a task `simulate` with a `desc`, so `task --list` shows it.
2. Its `cmds` are exactly one command, `uv run simulate`, with no `--seed` and no
   `--loads`: one load, a random seed, into the live lake (`$LAKE_ROOT`, or the default
   lake ingest lands in). It passes no `{{.CLI_ARGS}}` rewrite that changes those
   defaults; forwarding `{{.CLI_ARGS}}` unchanged is fine.
3. Nothing in the task deletes, moves or rewrites files in the lake, and it does not run
   `task ingest`, `task generate` or `dbt build`.
4. `uv run simulate --help` names `--seed` and `--loads` and says what each does.

## AC13: the docs drafted in the design interview

The run folder's `docs/` holds the drafts. Compare the repo against them.

Pass when all of these hold:

1. `docs/adr/` holds ADR-0027 with the draft's title, status, context, decision, rejected
   alternatives and consequences. A wording change is fine only where the build proved the
   draft wrong, and it says what changed. Renumbering after a collision with a parallel
   story is fine when the links follow.
2. `docs/adr/README.md` has ADR-0027's index row.
3. ADR-0014 ends with the drafted addendum (the simulated lake runs beside the hand-written
   lakes in `tests/test_end_to_end.py`, not instead of them), and its original text is
   otherwise unchanged.
4. `docs/lexicon.md` has the entry *late arrival* as drafted, and no other entry changed.
5. `docs/assumptions.md` has A20 and A21 as drafted (renumbered after a collision is fine
   when the links follow), and no other row changed.
6. The README tour names `task simulate`, and the root `CLAUDE.md` layout names
   `src/simulate/`.
7. Nothing in the repo's docs says the simulator lives under `src/ingest/`, runs through a
   dlt pipeline, or simulates a resource other than Products.

## EC7: a real ingest after a simulated load

A simulated load lands, then a real `task ingest` runs. The real load's id must be later
than the simulated one, so conform appends it as the newest load.

Pass when all of these hold:

1. On a lake that holds Products loads, the simulator stamps each new load with the current
   time, or one second after the latest load id when the clock is behind it (AC5, EC4).
   It never stamps a load id ahead of the clock unless the lake's latest load is itself
   ahead of it. Read the code that chooses the load id.
2. On an empty lake it stamps 2014-02-09 onward, so any later real load (stamped now by
   dlt) is newer than every simulated one.
3. dlt's load id for a real ingest is the current time in epoch seconds, so (1) and (2)
   leave the real load's id the largest; conform's incremental filter (load id greater than
   the newest staged) then appends it.
4. The evidence stage shows one live round trip: `task simulate`, then `task ingest`, then
   `task build`, with the real load's id larger than the simulated one and the build green.

# Judged checks for story #3 (generated ERDs in the README)

## AC12: the README renders on GitHub

The reviewer opens the PR branch's `README.md` on github.com (the rendered file view, not
the raw text) and records pass or fail for each line below. The diagrams are GitHub's Mermaid,
whose version may parse less than the Mermaid 11 the type format was measured against
(assumption on GitHub rendering the README's `erDiagram`s, in `docs/assumptions.md`).

Pass when all of these hold:

1. Under the section "The model" there are three rendered diagrams, conform, integrate and
   serve, in that order. No Mermaid error box ("Unable to render rich display", a parse
   error, or the code block shown as plain text) appears in their place.
2. The conform diagram shows the entity `adventure_works__products` with the row
   `bigint product_id PK`.
3. The integrate diagram shows `PR_Product` with `PR_ID` marked PK and seven attributes,
   including the parenthesised types (`varchar(25)`) and the "historized" comments.
4. The serve diagram shows `product` and `_bridge` (the leading underscore intact), and one
   relationship line between them labelled `_key__product`.
5. None of the HTML comment markers around the diagrams is visible on the rendered page.

A failure in (1)-(4) sends the type format back to the spec ([S1]), and the assumption is
recorded as broken.

# Judged checks for story #37 (hero artwork at the top of the README)

The reference for the drawing is `hero-mockup.svg`, the mockup approved in the design interview
and kept with the run's spec. The reviewer records pass or fail for each line below.

## Hero drawing (AC8)

Render `assets/hero.svg` (moved from `docs/` by story #38; with its animation off, or once the motion has come to rest) and place it beside `hero-mockup.svg`. Pass when all hold:

1. Left to right: the wordmark DECLARATIVE / DATA PLATFORM on two lines with the layer line `ingest · conform · integrate · serve` under it; nine raw tiles slightly out of line; a fanned stack of three pages, the front one with indented key and value lines; a star of one lit diamond, the bridge, at the centre and eight tiles on a ring, each joined to it, the bridge drawn as the explainer film draws it.
2. A dotted trail of three dots sits in each gap and brightens toward the star.
3. The gaps between raw, pages and star are equal to the eye.
4. Raw tiles, pages, dots and star tiles share one shade; the centre diamond is the only thing in the accent colour.
5. No line shows through or beneath a tile or page.

## Hero on GitHub (AC9, EC4)

Screenshots of the branch's README on github.com, whose hero is `assets/hero.svg` (story #38), taken once its motion has come to rest: light and dark theme, desktop width and 390px. Pass when all hold:

1. The README opens with the hero; no `# declarative-data-platform` heading above or below it.
2. The wordmark is in Spectral, the layer line in Inter: neither falls back to Georgia, Times or Arial.
3. On the light theme the hero reads as a dark card with rounded corners; on dark it sits on the page with no seam but its corners.
4. At 390px the whole banner is visible, nothing cropped, and both the wordmark and the layer line are legible.

# Judged checks for story #38 (the hero in motion)

The reference for the motion is `tests/fixtures/hero-motion-mockup.svg`, storyboard C in its third
revision, the mockup approved in the design interview. The reviewer records pass or fail for each
line below.

## Hero in motion (AC8, AC9)

**Storyboard (AC8).** Open `assets/hero.svg` in a browser with motion allowed, beside
`tests/fixtures/hero-motion-mockup.svg`, reloading to replay it. Pass when all hold:

1. The wordmark, the layer line, the nine raw tiles and the three pages stay where #37's still has them throughout; only copies of the raw tiles, the Anchor shapes, the stage lines and the dots of the two trails move.
2. Four stages, in this order, each change lighting one page, back to front: (1) raw, the copies appear on the raw tiles; (2) the back page lights and the copies tidy into a 3 by 3 grid; (3) the middle page lights and they become Anchor notation: two anchors (squares, both lit in the accent), each with three historized attributes (double circles), the anchors joined by a tie (diamond); (4) the front page lights, the tie slides into the centre and lights up as the bridge, still a diamond, the attributes and anchors move out to the ring as dimensions, the anchors' light passes to the bridge, and the spokes and the glow appear.
3. The two dot trails move with the stages. The mockup predates this revision (Mattias, 2026-11-02), so the trails are judged against this item, not the mockup. The raw-to-pages dots (the feed) pulse as data coming in until the star forms. The pages-to-model dots stay dark until the first shape forms, and at each change of model they drop and reconnect dot by dot. At each change the feed pulse runs on into the reconnecting trail, so the change reads as one wave from the raw tiles to the new model. One extra feed pulse runs between changes. At rest both trails show the still's opacities.
4. It ends on #37's still (the "Hero drawing" rubric above holds for the last frame) and stays there: about 6 s of motion within an 11 s run, played once, and it does not loop.
5. Nothing flickers, jumps or shows a half-built frame at the start or the end; the stages read in the mockup's order and spacing (exact easing and per-tile stagger are not judged).

**On GitHub (AC9).** On github.com, the branch's README, in Chrome, Firefox and Safari, each in the light and the dark theme, then with reduced motion requested by the system (macOS: Accessibility, Display, Reduce motion; Windows: Settings, Accessibility, Visual effects, Animation effects off). Pass when all hold:

1. With motion allowed, in each of the three browsers and both themes, the hero opens on the raw tiles and the pages, plays the four stages once, and rests on the still until the page reloads.
2. With reduced motion requested, in each browser, the hero shows #37's still at once: no motion, no half-built frame.
3. The wordmark and the layer line keep their embedded fonts (Spectral, Inter) throughout the motion and at rest.
4. A recording of the motion on github.com (one browser, motion allowed, from load to rest) is on the evidence page, with a note per browser and theme and for reduced motion.

A browser that keeps the hero still with motion allowed, or moves it with reduced motion requested, breaks assumption A27 (`docs/assumptions.md`): record which, and the still it should have shown.

# Judged checks for story #35 (the suite runs in parallel)

Four acceptance criteria and one edge case are judged at review rather than run. The reviewer
reads the evidence named in each and records pass or fail for each line below.

## AC7: the CI `test` job, green in at most half the serial time

Three runs of the PR's head commit: the push and two re-runs ([7], [8]), each set against the
serial `test` job of the PR's base commit: the `main` push run of that base SHA, which ran
before `-n auto` existed. The spec was amended on 2026-11-02 from 4 minutes to 6, then
from 6 minutes to this ratio (Mattias, decision card 09:14Z), and then from each run to the
median of the three, because runner noise is about a minute either way (Mattias, decision
card 13:04Z).

Pass when all of these hold:

1. The evidence reads the runs from the GitHub Actions API (`gh run list --commit <sha>`,
   `gh run view <id> --json jobs`, or `/repos/{owner}/{repo}/actions/runs/{id}/jobs`), not
   from memory or a screenshot of a different commit. It does so for the head runs and for
   the base's `main` run, and shows both SHAs; the base SHA is the PR's base commit, and its
   run is a `push` run on `main`.
2. There are three attempts of the `ci` workflow on the head SHA (run attempts 1, 2 and 3, or
   three distinct runs), and the `test` job of each has conclusion `success`.
3. The `test` job of the base's `main` run has conclusion `success`, and the evidence states
   its duration, `completed_at` minus `started_at`.
4. The median of the three head `test` jobs' durations, each `completed_at` minus
   `started_at`, is at most half the base's duration. The evidence lists all three head
   durations, each with its ratio to the base's duration, and the median.
5. Each head job ran the committed `uv run pytest` step unchanged: no re-run with debug
   options, a changed workflow, or `-n` passed by hand.

## AC8: five full runs in a row, all green

Five consecutive full `uv run pytest` runs in the sandbox, on the head commit ([8]).

Pass when all of these hold:

1. One script ran the five runs back to back, with no edits, retries or skipped runs between
   them, on the head commit (the evidence shows `git rev-parse HEAD` and a clean
   `git status`).
2. Each run is a plain `uv run pytest`: no `-n`, `-k`, `-m`, `--lf`, `-x` or path argument.
3. Each run's summary line reads `N passed`, with the same N in all five, and none names
   `failed` or `error`. (Under xdist the summary does not print the deselected count; that
   the `claude` tests stay deselected is judged in AC9.)
4. The evidence gives each run's wall time.

## AC9: the parallel run passes what the serial run passed

The passed node ids of `uv run pytest -n 0 -rA` at the base equal those of `uv run pytest -rA`
at the head, except for tests this change adds ([8]).

Pass when all of these hold:

1. The evidence holds both lists of `PASSED` node ids, sorted, from the base commit and the
   head commit, with their SHAs; the base run used `-n 0` (or the base's own serial default)
   and the head run used no `-n`.
2. The head list minus the base list is exactly the tests this change adds (the new
   tests in `tests/test_ci_workflow.py`), and the base list minus the head list is empty.
   The base list has 218 ids, or the evidence says why the count differs.
3. Neither run has a `FAILED` or `ERROR` line.
4. The same `claude` tests (`tests/test_rules_load.py`) are deselected at both commits. Under
   xdist the parallel run's summary does not print a deselected count, so the evidence shows
   `uv run pytest --collect-only -q` at the base and at the head (xdist turns itself off for
   collection, so each prints `x/y tests collected (n deselected)`) with the same n, and no
   `tests/test_rules_load.py` id among either run's `PASSED` lines.

## AC10: the records

`docs/assumptions.md` and ADR-0014 against the spec's *Records*, with the CI timing from AC7.

Pass when all of these hold:

1. `docs/assumptions.md` row A8 reads as the spec's restated A8: the `test` job, run in
   parallel, takes at most half as long, as the median of three runs on one commit, as the
   same suite run serially (`-n 0`), on a GitHub-hosted `ubuntu-latest` runner with 4 CPUs
   while the repository is public. It stops holding when the median of three `test` jobs on
   one commit takes more than half the serial time, or when `psutil` enters `uv.lock`. It
   says `loadgroup` is not the fix, having measured slower in the sandbox (7m05s against
   4m54s), and names no `loadgroup` remedy. It says that for story #35 the serial time is its
   base's `test` job on `main`, the last one run before `-n auto`. The standing wording does
   not tie the serial time to a `main` run, since `main` runs in parallel once this merges.
2. Rows A25 (two xdist workers never get the same free port) and A26 (every test is
   independent of the others) appear with the spec's assumption, area `ci` and
   "stopped holding" text. A wording change is fine only where the build proved the spec
   wrong, and the evidence says what changed.
3. A section "Measured (2026-11-02, CI)" records the head runs' `test` job times with
   `-n auto` and the base's serial `test` job time, both taken from AC7.
4. ADR-0014 ends with "Addendum 2026-11-02" as in the spec, with the head timing, the serial
   base timing and the PR number (#41) filled in (no `<filled from AC7>` or `<n>`
   placeholder left), and its original text is otherwise unchanged.
5. ADR-0014's row in `docs/adr/README.md` is unchanged, no new ADR was added, and no other
   row of `docs/assumptions.md` changed.

## EC5: a failing test under xdist

A test that fails under xdist is reported as a serial run reports it ([5]).

Pass when all of these hold:

1. During the build, one deliberately failing throwaway test was run with `-n auto` (the
   output shows a `created: N/N workers` line).
2. The output's failures section names the test by its node id and shows its traceback,
   down to the failing assertion, and the short summary has a `FAILED <node id>` line.
3. The throwaway test is not in any commit of the branch.

# Judged checks for story #39 (the longer explainer)

The film itself is judged at the evidence gate (AC14, Done-when 2): what it teaches, how it
looks and how it sounds are not run. The reviewer records pass or fail for each line below.

## J39-1: the film (AC14)

Watch the rendered cut, `out/film/declarative-data-platform-explainer.mp4` from `uv run task
film` (or the film on GitHub Pages, https://mattiasthalen.github.io/declarative-data-platform/),
once with sound, then again muted. It passes
when all of these hold:

1. Each of ingest, conform, integrate and serve has a chapter that says what the layer does and
   why it's there, in the narration and in the captions.
2. Each chapter centres its declaration, with the shape before it on the left and its output on
   the right.
3. Serve is presented as today's USS, never as the only serve format.
4. The look follows the design system (Nocturne: indigo ground, one blurple accent, Spectral
   wordmark, Inter text, layers gaining light as they integrate), and the shapes match the
   hero's.
5. Muted, the captions alone tell the story.
6. The music never covers the voice.

A viewer who comes away unable to say what one of the four layers does, or why it is there,
fails item 1 for that layer: record which, and at what time in the cut.

# Judged checks for story #49 (the explainer's own sound)

## J49-1: the explainer's own sound (AC1, AC2, EC3)

Render the cut with `uv run task film` and listen to it beside the approved reference,
`80s-e-blend-kick.mp3`: the approved sketch, in the project's files for story #49 and attached to
its evidence page, not in this repo. The reviewer records pass or fail for each item, and for a
fail, what was heard and at what time in the cut.

Pass when all of these hold:

1. AC1, the palette matches the sketch:
   1. The tempo is 96 BPM.
   2. A pad plays the chords Am, C/G, F, E, one a bar.
   3. The bass jumps octaves in 16ths on the chord roots.
   4. A pulse arpeggio runs in 8ths.
   5. A dry kick plays on every beat, and a short, dry snare on beat 3.
2. AC1, nothing of daana-promo's: no plucked arpeggio, no hi-hat, no bell at a chapter's start,
   no washy gated snare.
3. AC1, the voice is a British male (Lewis).
4. AC2, the instruments enter as arranged; at each time, name what plays:
   1. 0:05: the pad only.
   2. 0:15: the pad, with kick and bass.
   3. 0:35: as at 0:15, with the snare.
   4. 0:55: as at 0:35, with the arpeggio.
   5. 1:15: everything.
   6. 1:45: the lockup, the pad only, resting on Am.
5. EC3, the last seconds: the pad alone, fading out, and no note is cut off.
