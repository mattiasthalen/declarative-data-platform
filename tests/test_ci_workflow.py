"""How CI runs the suite: `task check` and the tests on every pull request and push to main (story 2, AC10), in parallel under pytest-xdist (story #35)."""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys
import tomllib

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


# Story #35: the suite runs in parallel under pytest-xdist.

PYPROJECT = REPO / "pyproject.toml"
LOCKFILE = REPO / "uv.lock"
TASKFILE = REPO / "Taskfile.yml"
CLAUDE_MD = REPO / "CLAUDE.md"

# Environment that would steer a nested pytest away from the repo's own configuration.
NESTED_ENV_OVERRIDES = ("PYTEST_ADDOPTS", "PYTEST_PLUGINS", "PYTEST_XDIST_AUTO_NUM_WORKERS")
WORKERS_CREATED = re.compile(r"created: (\d+)/(\d+) workers")
ONE_PASSED = re.compile(r"(?<!\d)1 passed")


def arguments(value: str | list[str]) -> list[str]:
    if isinstance(value, list):
        return [arg for item in value for arg in shlex.split(item)]
    return shlex.split(value)


def option_values(args: list[str], short: str, long: str) -> list[str]:
    """Every value given to an option, in any of `-n V`, `-nV`, `-n=V`, `--long V`, `--long=V`."""
    values = []
    for i, arg in enumerate(args):
        if arg in (short, long):
            values.append(args[i + 1] if i + 1 < len(args) else "")
        elif arg.startswith(long + "="):
            values.append(arg[len(long) + 1 :])
        elif arg.startswith(short) and not arg.startswith("--"):
            values.append(arg[len(short) :].removeprefix("="))
    return values


def addopts() -> list[str]:
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    ini = config.get("tool", {}).get("pytest", {}).get("ini_options", {})
    return arguments(ini.get("addopts", ""))


def test_xdist_in_dev_group_and_locked():
    """AC1: pytest-xdist is in the `dev` dependency group, and uv.lock locks it."""
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    dev = config.get("dependency-groups", {}).get("dev", [])
    names = [
        re.split(r"[\s\[<>=!~;@]", req, maxsplit=1)[0].lower().replace("_", "-")
        for req in dev
        if isinstance(req, str)
    ]
    assert "pytest-xdist" in names, f"dependency-groups.dev is {dev}"
    lock = tomllib.loads(LOCKFILE.read_text(encoding="utf-8"))
    locked = {package.get("name") for package in lock.get("package", [])}
    assert "pytest-xdist" in locked, "uv.lock has no package named pytest-xdist"


def test_addopts_runs_in_parallel():
    """AC2: addopts holds `-n auto` and `-p no:cacheprovider`, and names no `--dist`."""
    args = addopts()
    assert "auto" in option_values(args, "-n", "--numprocesses"), f"addopts is {args}"
    assert "no:cacheprovider" in option_values(args, "-p", "--plugin"), f"addopts is {args}"
    dist = [arg for arg in args if arg == "--dist" or arg.startswith("--dist=")]
    assert not dist, f"addopts names {dist}; the default load split is the one decided"


def turns_xdist_off_or_sets_workers(args: list[str]) -> list[str]:
    return [
        arg
        for arg in args
        if (arg.startswith("-n") and not arg.startswith("--"))
        or arg.startswith("--numprocesses")
        or "no:xdist" in arg
    ]


def test_test_job_keeps_xdist_on(workflow):
    """AC3: the test job runs `uv run pytest` and nothing that turns xdist off or sets its worker count."""
    j = job(workflow, "test")
    commands = runs(j)
    assert any("uv run pytest" in run for run in commands), f"the test job runs {commands}"
    for run in commands:
        found = turns_xdist_off_or_sets_workers(arguments(run))
        assert not found, f"the test job's {run!r} passes {found}"
    for scope in [workflow, j, *(j.get("steps") or [])]:
        env = scope.get("env") or {}
        assert "PYTEST_XDIST_AUTO_NUM_WORKERS" not in env, f"env sets the worker count: {env}"
        found = turns_xdist_off_or_sets_workers(arguments(str(env.get("PYTEST_ADDOPTS", ""))))
        assert not found, f"PYTEST_ADDOPTS passes {found}"


def nested_pytest(tmp_path, *extra: str) -> subprocess.CompletedProcess:
    """One trivial passing test, run by pytest under the repo's pyproject.toml (its addopts included).

    `--rootdir` and `--confcutdir` keep the run inside tmp_path, so it neither loads the repo's
    conftest nor collects the repo's suite.
    """
    (tmp_path / "test_trivial.py").write_text("def test_trivial():\n    assert True\n", encoding="utf-8")
    env = {k: v for k, v in os.environ.items() if k not in NESTED_ENV_OVERRIDES}
    return subprocess.run(
        [
            sys.executable, "-m", "pytest",
            "-c", str(PYPROJECT),
            "--rootdir", str(tmp_path),
            "--confcutdir", str(tmp_path),
            *extra,
            str(tmp_path / "test_trivial.py"),
        ],
        cwd=REPO,
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
    )


def test_plain_run_starts_workers(tmp_path):
    """AC4: a plain run under the repo's configuration starts xdist workers and passes."""
    result = nested_pytest(tmp_path)
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert ONE_PASSED.search(output), f"expected exactly the one trivial test to pass:\n{output}"
    created = WORKERS_CREATED.search(output)
    assert created, f"no `created: N/N workers` line:\n{output}"
    started, asked = int(created[1]), int(created[2])
    assert started == asked >= 1, created[0]


def test_serial_run_starts_no_workers(tmp_path):
    """EC4: `-n 0` runs serially, with no xdist workers, and the same test passes."""
    result = nested_pytest(tmp_path, "-n", "0")
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert ONE_PASSED.search(output), f"expected exactly the one trivial test to pass:\n{output}"
    assert "created:" not in output, f"`-n 0` started workers:\n{output}"


def test_test_rules_runs_serially():
    """AC5: `task test-rules` runs `pytest -m claude -n 0`."""
    tasks = yaml.safe_load(TASKFILE.read_text(encoding="utf-8")).get("tasks") or {}
    assert "test-rules" in tasks, f"no task test-rules; tasks are {sorted(tasks)}"
    cmds = tasks["test-rules"].get("cmds") or []
    commands = [c if isinstance(c, str) else str(c.get("cmd", "")) for c in cmds]
    for command in commands:
        args = arguments(command)
        if "pytest" in args and "claude" in option_values(args, "-m", "-m"):
            assert "0" in option_values(args, "-n", "--numprocesses"), f"test-rules runs {command!r}"
            return
    pytest.fail(f"test-rules runs no `pytest -m claude`: {commands}")


def test_claude_md_names_the_serial_run():
    """AC6: CLAUDE.md's "Proving a change" names `uv run pytest -n 0` as the serial run."""
    text = CLAUDE_MD.read_text(encoding="utf-8")
    section = re.search(r"^## Proving a change\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    assert section, "CLAUDE.md has no section 'Proving a change'"
    assert "uv run pytest -n 0" in section[1], section[1]
