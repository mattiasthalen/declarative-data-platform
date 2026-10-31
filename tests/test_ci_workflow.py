"""The CI workflow runs `task check` and the suite on every pull request and push to main (story 2, AC10)."""

from __future__ import annotations

import json

import pytest
import yaml

from harness import REPO

WORKFLOW = REPO / ".github" / "workflows" / "ci.yml"


@pytest.fixture(scope="module")
def workflow() -> dict:
    assert WORKFLOW.is_file(), f"{WORKFLOW.relative_to(REPO)} does not exist"
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def triggers(workflow: dict) -> dict:
    # PyYAML reads the bare key `on` as the boolean True.
    on = workflow.get("on", workflow.get(True))
    assert on is not None, "the workflow declares no triggers"
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {name: None for name in on}
    return on


def job(workflow: dict, name: str) -> dict:
    jobs = workflow.get("jobs") or {}
    assert name in jobs, f"no job named {name!r}; jobs are {sorted(jobs)}"
    return jobs[name]


def runs(job: dict) -> list[str]:
    return [step["run"] for step in job.get("steps") or [] if "run" in step]


def uses(job: dict) -> list[str]:
    return [step["uses"] for step in job.get("steps") or [] if "uses" in step]


def python_versions(workflow: dict, job: dict) -> set[str]:
    """Every Python version the job pins: a setup action's python-version, UV_PYTHON, or a uv --python."""
    found = set()
    for env in (workflow.get("env") or {}, job.get("env") or {}):
        if "UV_PYTHON" in env:
            found.add(str(env["UV_PYTHON"]))
    for step in job.get("steps") or []:
        with_ = step.get("with") or {}
        if "python-version" in with_:
            found.add(str(with_["python-version"]))
        if "UV_PYTHON" in (step.get("env") or {}):
            found.add(str(step["env"]["UV_PYTHON"]))
        run = step.get("run") or ""
        for marker in ("uv python install ", "--python ", "--python="):
            if marker in run:
                found.add(run.split(marker, 1)[1].split()[0])
    return found


def test_runs_on_pull_request_and_push_to_main(workflow):
    """AC10: the workflow runs on every pull request and on push to main."""
    on = triggers(workflow)
    assert "pull_request" in on, f"triggers are {on}"
    assert "push" in on, f"triggers are {on}"
    branches = (on["push"] or {}).get("branches") or []
    assert "main" in branches, f"push runs on branches {branches}, not main"


@pytest.mark.parametrize(
    ("name", "command"), [("check", "task check"), ("test", "uv run pytest")]
)
def test_job_runs_its_command(workflow, name, command):
    """AC10: `check` runs `task check`; `test` runs `uv run pytest`."""
    commands = runs(job(workflow, name))
    assert any(command in run for run in commands), f"job {name} runs {commands}"


@pytest.mark.parametrize("name", ["check", "test"])
def test_job_sets_up_uv_and_python_313(workflow, name):
    """AC10: each job uses astral-sh/setup-uv and Python 3.13."""
    j = job(workflow, name)
    assert any(u.startswith("astral-sh/setup-uv") for u in uses(j)), f"job {name} uses {uses(j)}"
    versions = python_versions(workflow, j)
    assert "3.13" in versions, f"job {name} pins Python {versions or 'nowhere'}:\n{json.dumps(j, indent=2)}"


def test_check_and_test_run_in_parallel(workflow):
    """Spec [6]: two parallel jobs, so drift does not hide test failures."""
    for name, other in (("check", "test"), ("test", "check")):
        needs = job(workflow, name).get("needs") or []
        needs = [needs] if isinstance(needs, str) else needs
        assert other not in needs, f"job {name} waits on {other}"
