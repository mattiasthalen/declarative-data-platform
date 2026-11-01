"""Story #16: what `orchestrate/prefect.yaml` declares, and the repo around it.

AC1 schedule, AC9 target, AC10 commands, AC11 one project, AC14 the Taskfile tasks.
"""

from __future__ import annotations

import os
import re
import subprocess
import tomllib

import yaml

from harness import REPO, tail

LIST = ["uv", "run", "task", "ingest:list"]
INGEST = ["uv", "run", "task", "-x", "ingest:source", "--"]
BUILD = ["uv", "run", "task", "-x", "build"]
ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def default(deployment: dict, parameter: str):
    """The value a run of ``deployment`` gets for ``parameter`` when the trigger gives none."""
    if parameter in (deployment.get("parameters") or {}):
        return deployment["parameters"][parameter]
    properties = (deployment.get("parameter_openapi_schema") or {}).get("properties", {})
    assert parameter in properties, (
        f"{deployment['name']} has no parameter {parameter!r}; it has {sorted(properties)}"
    )
    assert "default" in properties[parameter], f"{deployment['name']}.{parameter} has no default"
    return properties[parameter]["default"]


def strings(node):
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for k, v in node.items():
            yield from strings(k)
            yield from strings(v)
    elif isinstance(node, list):
        for v in node:
            yield from strings(v)


def test_schedule(prefect):
    """AC1: `run` hourly at minute 0 in UTC, schedule active; the other two unscheduled."""
    run = prefect.deployment("run")
    schedules = run["schedules"]
    assert len(schedules) == 1, f"`run` has {len(schedules)} schedules: {schedules}"
    (schedule,) = schedules
    assert schedule["active"] is True, f"`run`'s schedule is not active: {schedule}"
    assert schedule["schedule"].get("cron") == "0 * * * *", f"`run`'s schedule: {schedule['schedule']}"
    assert schedule["schedule"].get("timezone") in ("UTC", "Etc/UTC"), (
        f"`run`'s schedule is not in UTC: {schedule['schedule']}"
    )
    assert not run.get("paused"), "`run` is deployed paused"
    for name in ("ingest-source", "build"):
        assert prefect.deployment(name)["schedules"] == [], f"`{name}` has a schedule"


def test_target(orchestrated, fakes):
    """AC9: `build` triggered with no target builds TARGET=prod."""
    run = orchestrated.trigger("build", {"command": fakes.build_command()})
    finished = orchestrated.wait(run)
    assert finished["state"]["type"] == "COMPLETED", finished["state"]
    calls = fakes.calls("build")
    assert [c["argument"] for c in calls] == ["TARGET=prod"], calls


def test_commands(prefect):
    """AC10: every default command is a Taskfile task, and none is `generate`."""
    run = prefect.deployment("run")
    ingest = prefect.deployment("ingest-source")
    build = prefect.deployment("build")
    assert default(run, "list_command") == LIST
    assert default(run, "ingest_command") == INGEST
    assert default(run, "build_command") == BUILD
    assert default(ingest, "command") == INGEST
    assert default(build, "command") == BUILD
    assert default(run, "target") == "prod"
    assert default(build, "target") == "prod"

    declared = yaml.safe_load((REPO / "orchestrate" / "prefect.yaml").read_text())
    generate = [s for s in strings(declared) if re.search(r"\bgenerate\b", s)]
    assert not generate, f"orchestrate/prefect.yaml mentions generate: {generate}"
    for deployment in (run, ingest, build):
        values = [deployment.get("parameters") or {}, deployment.get("parameter_openapi_schema") or {}]
        generate = [s for s in strings(values) if re.search(r"\bgenerate\b", s)]
        assert not generate, f"{deployment['name']}'s parameters mention generate: {generate}"


def test_one_project():
    """AC11: Prefect is the root project's `orchestrate` group; one pyproject.toml, one uv.lock."""
    project = tomllib.loads((REPO / "pyproject.toml").read_text())
    group = project.get("dependency-groups", {}).get("orchestrate")
    assert group is not None, "pyproject.toml has no `orchestrate` dependency group"
    assert any(re.match(r"prefect\b", str(dep)) for dep in group), (
        f"the orchestrate group does not bring prefect: {group}"
    )
    assert re.search(r'^name = "prefect"$', (REPO / "uv.lock").read_text(), re.M), (
        "uv.lock does not lock prefect: run `uv lock`"
    )

    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    for name in ("pyproject.toml", "uv.lock"):
        found = [p for p in tracked if p.rsplit("/", 1)[-1] == name]
        assert found == [name], f"expected only the root {name}, git tracks {found}"


def test_tasks_listed():
    """AC14: `uv run task --list` shows the three orchestrate tasks."""
    # go-task colours its listing when it sees CI=true, as on GitHub Actions. NO_COLOR
    # turns that off; stripping the escapes covers a go-task that ignores it.
    listing = subprocess.run(
        ["uv", "run", "task", "--list"],
        cwd=REPO,
        env={**os.environ, "NO_COLOR": "1"},
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert listing.returncode == 0, tail(listing.stdout + listing.stderr)
    shown = ANSI_ESCAPE.sub("", listing.stdout)
    for task in ("orchestrate:server", "orchestrate:worker", "orchestrate:deploy"):
        assert re.search(rf"^\* {re.escape(task)}:", shown, re.M), (
            f"`task --list` does not show {task}:\n{shown}"
        )
