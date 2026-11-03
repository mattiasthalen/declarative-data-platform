"""The `film` workflow renders the explainer on main and replaces it on the `explainer` release
(story #39: AC11).

It is read as YAML: its triggers and path filter ([1b]), its permission to write releases, a
cache of ``.models/`` keyed on the Kokoro checksums, the render before the upload, and an upload
with ``gh release upload --clobber`` onto ``explainer`` that creates the release when it is
missing. ``ci.yml`` keeps ``contents: read``.

- ``-k film_workflow``: AC11.
"""

from __future__ import annotations

import re

import yaml
from harness import REPO

WORKFLOWS = REPO / ".github" / "workflows"
FILM = WORKFLOWS / "film.yml"
CI = WORKFLOWS / "ci.yml"
ASSET = "declarative-data-platform-explainer.mp4"
# [1b]: what a push to main must touch to render.
PATHS = {"src/film", "src/artwork", "sources", "contracts", "anchor", "orchestrate/prefect.yaml"}
FILES = {"orchestrate/prefect.yaml"}


def load(path) -> dict:
    assert path.is_file(), f"{path.relative_to(REPO)} does not exist"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def triggers(workflow: dict) -> dict:
    # PyYAML reads the bare key `on` as the boolean True.
    on = workflow.get("on", workflow.get(True))
    assert on is not None, "the workflow declares no triggers"
    if isinstance(on, str):
        return {on: None}
    if isinstance(on, list):
        return {name: None for name in on}
    return on


def steps(workflow: dict) -> list[dict]:
    return [step for job in (workflow.get("jobs") or {}).values() for step in job.get("steps") or []]


def contents(permissions) -> str | None:
    if isinstance(permissions, str):
        return {"write-all": "write", "read-all": "read"}.get(permissions, permissions)
    return (permissions or {}).get("contents")


def triggers_are_1b(film: dict) -> None:
    """AC11: on push to main with exactly [1b]'s paths, and on workflow_dispatch; nothing else."""
    on = triggers(film)
    assert set(on) == {"push", "workflow_dispatch"}, f"film.yml triggers on {sorted(on)}"
    push = on["push"] or {}
    assert push.get("branches") == ["main"], f"film.yml's push runs on branches {push.get('branches')}"
    paths = push.get("paths") or []
    for path in paths:
        if path.rstrip("*").rstrip("/") not in FILES:
            assert path.endswith("/**"), f"film.yml's path filter {path!r} does not match its folder's files"
    normalized = {path.rstrip("*").rstrip("/") for path in paths}
    assert normalized == PATHS and len(paths) == len(PATHS), (
        f"film.yml's push paths are {paths}, expected exactly {sorted(PATHS)}"
    )


def permissions_are_scoped(film: dict) -> None:
    """AC11: film.yml may write contents (to upload the asset); ci.yml keeps contents: read."""
    jobs = film.get("jobs") or {}
    granted = {contents(film.get("permissions"))} | {
        contents(job["permissions"]) for job in jobs.values() if "permissions" in job
    }
    assert "write" in granted, f"film.yml grants contents {granted - {None}}, expected write"

    ci = load(CI)
    assert contents(ci.get("permissions")) == "read", f"ci.yml's top-level contents is {ci.get('permissions')}"
    for name, job in (ci.get("jobs") or {}).items():
        if "permissions" in job:
            assert contents(job["permissions"]) in (None, "read", "none"), (
                f"ci.yml's {name} job raises contents to {job['permissions']}"
            )


def models_are_cached(film: dict) -> None:
    """AC11: a cache step keeps .models/ under a key derived from the Kokoro checksums."""
    caches = [s for s in steps(film) if str(s.get("uses", "")).startswith("actions/cache")]
    assert caches, "film.yml has no actions/cache step"
    keyed = []
    for step in caches:
        with_ = step.get("with") or {}
        if ".models" not in str(with_.get("path", "")):
            continue
        key = str(with_.get("key", ""))
        if re.search(r"hashFiles\(|[0-9a-f]{64}|sha256|checksum", key, re.IGNORECASE):
            keyed.append(step)
    assert keyed, "film.yml caches no .models/ under a key derived from the checksums"


def upload_replaces_the_asset(film: dict) -> None:
    """AC11: the render runs before an upload that replaces the asset on the explainer release
    (--clobber), creating the release when it is missing."""
    runs = [str(s.get("run", "")) for s in steps(film)]
    rendered = [i for i, run in enumerate(runs) if re.search(r"\btask\s+film(\s|$)", run)]
    assert rendered, "film.yml never runs `task film`"
    uploads = [
        i for i, run in enumerate(runs)
        if "gh release upload" in run and "--clobber" in run and re.search(r"\bexplainer\b", run) and ASSET in run
    ]
    assert uploads, f"film.yml has no `gh release upload explainer ... {ASSET} --clobber` step"
    assert min(rendered) < min(uploads), "film.yml uploads before it renders"
    creates = [
        i for i, run in enumerate(runs) if "gh release create" in run and re.search(r"\bexplainer\b", run)
    ]
    assert creates and min(creates) <= min(uploads), "film.yml does not create the explainer release before uploading"


def test_film_workflow():
    """AC11: film.yml's triggers and paths, its contents: write, its cache of the Kokoro files keyed
    on their checksums, and its upload with --clobber onto explainer, created when missing; ci.yml
    keeps contents: read."""
    film = load(FILM)
    triggers_are_1b(film)
    permissions_are_scoped(film)
    models_are_cached(film)
    upload_replaces_the_asset(film)
