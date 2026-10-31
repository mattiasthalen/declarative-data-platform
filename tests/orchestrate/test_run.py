"""Story #16: what a triggered `run` does, seen through the Prefect API and the fakes' call logs.

AC2 to AC8, AC15, AC16 and the edge cases E1 to E5. Every command a run would start is a
fake (``fake.py``), chosen per test through the run's parameters.
"""

from __future__ import annotations

import time

import pytest

from .live import Fakes, Prefect, when

# Distinct names, none a substring of another, so a message naming one never names two.
ALPHA, BRAVO = "src_alpha", "src_bravo"


def trigger_run(
    prefect: Prefect,
    fakes: Fakes,
    sources: list[str] | None = None,
    *,
    ingest: dict | None = None,
    build_exit: int = 0,
    log: str = "ingest",
    **parameters,
) -> str:
    """Trigger `run` with fake listing, ingest and build commands."""
    if "list_command" not in parameters:
        parameters["list_command"] = fakes.list_command(*(sources or []))
    if "ingest_command" not in parameters:
        parameters["ingest_command"] = fakes.ingest_command(ingest, log=log)
    if "build_command" not in parameters:
        parameters["build_command"] = fakes.build_command(exit=build_exit)
    return prefect.trigger("run", parameters)


def ended(prefect: Prefect, run_id: str) -> tuple[str, str]:
    run = prefect.wait(run_id)
    return run["state"]["type"], run["state"].get("message") or ""


def sources_of(runs: list[dict]) -> list[str]:
    return sorted(r["parameters"].get("source") for r in runs)


def test_fan_out(orchestrated, fakes):
    """AC2: one `ingest-source` flow run per listed source, then `build` after both ended."""
    run = trigger_run(
        orchestrated, fakes, [ALPHA, BRAVO], ingest={ALPHA: {"sleep": 3, "exit": 0}, BRAVO: 0}
    )
    state, message = ended(orchestrated, run)
    assert state == "COMPLETED", message

    ingests = orchestrated.children(run, "ingest-source")
    assert sources_of(ingests) == [ALPHA, BRAVO], [r["parameters"] for r in ingests]
    assert len({r["id"] for r in ingests}) == 2

    builds = orchestrated.children(run, "build")
    assert len(builds) == 1, f"{len(builds)} build runs under `run`"
    build_start = when(builds[0]["start_time"])
    ingest_ends = [when(r["end_time"]) for r in ingests]
    assert build_start is not None and None not in ingest_ends
    assert build_start >= max(ingest_ends), (
        f"build started at {builds[0]['start_time']}, before an ingest ended: "
        f"{[r['end_time'] for r in ingests]}"
    )

    calls = fakes.calls("ingest")
    assert sorted(c["argument"] for c in calls) == [ALPHA, BRAVO]
    # Commands run from the root of the repo that was deployed.
    assert {c["cwd"] for c in calls} == {str(orchestrated.ws.root)}
    assert {c["cwd"] for c in fakes.calls("build")} == {str(orchestrated.ws.root)}


def test_all_landed(orchestrated, fakes):
    """AC3: every source exits 0 and the build is green: `run` Completed, one build."""
    run = trigger_run(orchestrated, fakes, [ALPHA, BRAVO], ingest={ALPHA: 0, BRAVO: 0})
    state, message = ended(orchestrated, run)
    assert state == "COMPLETED", message
    assert [c["argument"] for c in fakes.calls("build")] == ["TARGET=prod"]
    assert len(orchestrated.children(run, "build")) == 1


def test_partly_landed(orchestrated, fakes):
    """AC4: exits 0 and 1: one build, `run` Failed naming the exit-1 source only."""
    run = trigger_run(orchestrated, fakes, [ALPHA, BRAVO], ingest={ALPHA: 0, BRAVO: 1})
    state, message = ended(orchestrated, run)
    assert state == "FAILED", message
    assert BRAVO in message, message
    assert ALPHA not in message, message
    assert len(fakes.calls("build")) == 1


def test_one_failed(orchestrated, fakes):
    """AC5: exits 0 and 2: one build, `run` Failed naming the exit-2 source."""
    run = trigger_run(orchestrated, fakes, [ALPHA, BRAVO], ingest={ALPHA: 0, BRAVO: 2})
    state, message = ended(orchestrated, run)
    assert state == "FAILED", message
    assert BRAVO in message, message
    assert ALPHA not in message, message
    assert len(fakes.calls("build")) == 1


def test_none_landed(orchestrated, fakes):
    """AC6: every source exits 2: no build run, `run` Failed naming every source."""
    run = trigger_run(orchestrated, fakes, [ALPHA, BRAVO], ingest={ALPHA: 2, BRAVO: 2})
    state, message = ended(orchestrated, run)
    assert state == "FAILED", message
    assert ALPHA in message and BRAVO in message, message
    assert orchestrated.children(run, "build") == []
    assert fakes.calls("build") == []
    assert len(orchestrated.children(run, "ingest-source")) == 2


def test_build_failed(orchestrated, fakes):
    """AC7: the build exits non-zero: `run` Failed, saying the build failed."""
    run = trigger_run(orchestrated, fakes, [ALPHA, BRAVO], build_exit=1)
    state, message = ended(orchestrated, run)
    assert state == "FAILED", message
    assert len(fakes.calls("build")) == 1
    lowered = message.lower()
    assert "build" in lowered and "fail" in lowered, message
    assert ALPHA not in message and BRAVO not in message, message


def test_overlap(orchestrated, fakes):
    """AC8: a second `run` while the first runs ends Cancelled, starting nothing; the first completes."""
    first = trigger_run(orchestrated, fakes, [ALPHA], ingest={ALPHA: {"sleep": 15, "exit": 0}})
    orchestrated.wait_for(first, "RUNNING")
    second_fakes = Fakes(fakes.dir / "second")
    second_fakes.dir.mkdir()
    second = trigger_run(orchestrated, second_fakes, [BRAVO], ingest={BRAVO: 0})

    state, message = ended(orchestrated, second)
    assert state == "CANCELLED", f"the second run ended {state}: {message}"
    assert orchestrated.children(second) == []
    assert second_fakes.calls("ingest") == [] and second_fakes.calls("build") == []

    state, message = ended(orchestrated, first)
    assert state == "COMPLETED", message
    assert [c["argument"] for c in fakes.calls("ingest")] == [ALPHA]
    assert len(fakes.calls("build")) == 1


def test_timeout(orchestrated, fakes):
    """AC15: a source past the (shortened) timeout counts as failed; the build still runs."""
    run = trigger_run(
        orchestrated,
        fakes,
        [ALPHA, BRAVO],
        ingest={ALPHA: 0, BRAVO: {"sleep": 90, "exit": 0}},
        ingest_timeout_seconds=5,
    )
    state, message = ended(orchestrated, run)
    assert state == "FAILED", message
    assert BRAVO in message, message
    assert ALPHA not in message, message
    assert len(fakes.calls("build")) == 1


def test_build_queue(orchestrated, fakes):
    """AC16: a `build` started while another runs waits for it; both complete, never overlapping."""
    command = fakes.build_command(sleep=8)
    first = orchestrated.trigger("build", {"command": command})
    second = orchestrated.trigger("build", {"command": command})

    seen: dict[str, set[str]] = {first: set(), second: set()}
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        states = {r: orchestrated.state(r) for r in (first, second)}
        for r, (kind, name, _) in states.items():
            seen[r].add(f"{kind}/{name}")
        running = [r for r, (kind, _, _) in states.items() if kind == "RUNNING"]
        assert len(running) < 2, "both builds were Running at once"
        if all(kind in ("COMPLETED", "FAILED", "CANCELLED", "CRASHED") for kind, _, _ in states.values()):
            break
        time.sleep(0.5)

    runs = {r: orchestrated.wait(r) for r in (first, second)}
    for r, finished in runs.items():
        assert finished["state"]["type"] == "COMPLETED", (finished["state"], seen[r])

    calls = sorted(fakes.calls("build"), key=lambda c: c["start"])
    assert len(calls) == 2, calls
    assert calls[0]["end"] <= calls[1]["start"], f"the two builds overlapped: {calls}"
    a, b = sorted(runs.values(), key=lambda r: when(r["start_time"]))
    assert when(a["end_time"]) <= when(b["start_time"]), (
        f"build runs overlapped: {a['start_time']}..{a['end_time']} and {b['start_time']}..{b['end_time']}"
    )


def test_no_sources(orchestrated, fakes):
    """E1: the listing lists no source: no child runs, `run` Failed saying no sources."""
    run = trigger_run(orchestrated, fakes, list_command=fakes.list_command(stdout="\n  \n\n"))
    state, message = ended(orchestrated, run)
    assert state == "FAILED", message
    assert "no source" in message.lower(), message
    assert orchestrated.children(run) == []
    assert fakes.calls("ingest") == [] and fakes.calls("build") == []


def test_list_failed(orchestrated, fakes):
    """E2: the listing exits non-zero: no child runs, `run` Failed with its stderr."""
    stderr = "feed catalogue unreachable (7f3a)"
    run = trigger_run(
        orchestrated,
        fakes,
        list_command=fakes.list_command(ALPHA, exit=1, stderr=stderr),
    )
    state, message = ended(orchestrated, run)
    assert state == "FAILED", message
    assert stderr in message, message
    assert orchestrated.children(run) == []
    assert fakes.calls("ingest") == [] and fakes.calls("build") == []


def test_odd_exit(orchestrated, fakes):
    """E3: a source exiting 137 counts as nothing landed and is named; the build still runs."""
    run = trigger_run(orchestrated, fakes, [ALPHA, BRAVO], ingest={ALPHA: 0, BRAVO: 137})
    state, message = ended(orchestrated, run)
    assert state == "FAILED", message
    assert BRAVO in message, message
    assert ALPHA not in message, message
    assert len(fakes.calls("build")) == 1


def test_odd_exit_alone(orchestrated, fakes):
    """E3: a lone source exiting 137 landed nothing, so no build runs."""
    run = trigger_run(orchestrated, fakes, [BRAVO], ingest={BRAVO: 137})
    state, message = ended(orchestrated, run)
    assert state == "FAILED", message
    assert BRAVO in message, message
    assert fakes.calls("build") == []
    assert orchestrated.children(run, "build") == []


def test_duplicate_source(orchestrated, fakes):
    """E4: a source listed twice gets one `ingest-source` run."""
    run = trigger_run(
        orchestrated, fakes, list_command=fakes.list_command(ALPHA, BRAVO, ALPHA)
    )
    state, message = ended(orchestrated, run)
    assert state == "COMPLETED", message
    assert sources_of(orchestrated.children(run, "ingest-source")) == [ALPHA, BRAVO]
    assert sorted(c["argument"] for c in fakes.calls("ingest")) == [ALPHA, BRAVO]


@pytest.mark.parametrize("name", ["a b;touch x"])
def test_source_name_quoted(orchestrated, fakes, name):
    """E5: a name a shell would split reaches the command as one argument, never through a shell."""
    command = fakes.ingest_command({name: 0})
    run = trigger_run(orchestrated, fakes, [name], ingest_command=command)
    state, message = ended(orchestrated, run)
    assert state == "COMPLETED", message
    calls = fakes.calls("ingest")
    assert len(calls) == 1, calls
    assert calls[0]["argument"] == name
    assert calls[0]["argv"] == [*command[2:], name], calls[0]["argv"]
    for folder in (orchestrated.ws.root, fakes.dir, orchestrated.ws.root / "orchestrate"):
        assert not (folder / "x").exists(), f"a shell ran `touch x` in {folder}"
