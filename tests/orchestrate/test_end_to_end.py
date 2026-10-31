"""Story #16, AC12: a `run` with real dbt, in a throwaway copy of the repo.

The listing and the ingest are fakes (the ingest lands the synthetic Products lake under the
worker's ``$LAKE_ROOT``, as ``harness.write_load`` writes it); the build is the deployment's
own default, the real ``uv run task build`` with the default target.
"""

from __future__ import annotations

from harness import CONTRACT, Snapshot, tail

# Real dbt builds take minutes; cap the wait well inside the build's own 30-minute timeout.
BUILD_SECONDS = 900


def test_end_to_end(orchestrated, fakes):
    """AC12: the run lands its source, builds the warehouse green, ends Completed; serve answers."""
    run = orchestrated.trigger(
        "run",
        {
            "list_command": fakes.list_command(CONTRACT),
            "ingest_command": fakes.lake_command(),
        },
    )
    finished = orchestrated.wait(run, BUILD_SECONDS)
    builds = orchestrated.children(run, "build")
    assert finished["state"]["type"] == "COMPLETED", (
        f"`run` ended {finished['state']}; build runs: {[b['state'] for b in builds]}\n"
        f"Worker log:\n{orchestrated.worker_log()}"
    )
    assert [c["argument"] for c in fakes.calls("ingest")] == [CONTRACT]
    assert len(builds) == 1 and builds[0]["state"]["type"] == "COMPLETED", builds

    warehouse = orchestrated.ws.root / "warehouse" / "prod.duckdb"
    assert warehouse.exists(), (
        f"no {warehouse}: the build did not run in the deployed repo's root\n{tail(orchestrated.worker_log())}"
    )
    snap = Snapshot(warehouse, "", None, None)
    assert snap.count("serve__uss", "product") > 0
    assert snap.count("serve__uss", "_bridge") > 0
    assert snap.count("integrate", "lPR_Product") == 3, "the three landed products are not all integrated"
