"""The `film` workflow renders the explainer and, from main, deploys it to GitHub Pages
(story #39: AC11, amended at review 2026-11-03, ADR-0040).

It is read as YAML: its triggers and path filter ([1b]); a render job that holds only
``contents: read``, restores and saves the Kokoro files' cache under a key hashed from the file
that pins their checksums, and renders before uploading a Pages artifact holding the page and the
MP4; a deploy job only on ``refs/heads/main`` that needs the render, holds ``pages: write`` and
``id-token: write``, runs in the ``github-pages`` environment, is not cancelled once started and
deploys with ``actions/deploy-pages``. Every action is pinned to a commit SHA, and nothing writes a
release or contents. ``ci.yml`` keeps ``contents: read`` and installs Chromium for the stills. The
page the site serves plays the MP4 inline.

- ``-k film_workflow``: AC11.
"""

from __future__ import annotations

import re
from html.parser import HTMLParser

import yaml
from harness import REPO

WORKFLOWS = REPO / ".github" / "workflows"
FILM = WORKFLOWS / "film.yml"
CI = WORKFLOWS / "ci.yml"
PAGE = "src/film/site/index.html"
ASSET = "declarative-data-platform-explainer.mp4"
# [1b]: what a push to main must touch to render.
PATHS = {"src/film", "src/artwork", "sources", "contracts", "anchor", "orchestrate/prefect.yaml"}
FILES = {"orchestrate/prefect.yaml"}
PINNED = re.compile(r"^[\w.-]+/[\w./-]+@[0-9a-f]{40}$")
HASH_FILES = re.compile(r"hashFiles\(\s*'([^']+)'")
RENDER = re.compile(r"\btask\s+film(\s|$)")


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


def jobs(workflow: dict) -> dict:
    return workflow.get("jobs") or {}


def steps(workflow: dict) -> list[dict]:
    return [step for job in jobs(workflow).values() for step in job.get("steps") or []]


def grants(permissions) -> dict:
    """A permissions block as {scope: level}; the shorthands are spelt out for contents."""
    if permissions is None:
        return {}
    if isinstance(permissions, str):
        return {"contents": {"write-all": "write", "read-all": "read"}.get(permissions, permissions), "*": permissions}
    return dict(permissions)


def effective(workflow: dict, job: dict) -> dict:
    # A job's own block replaces the workflow's; without one it inherits it.
    return grants(job["permissions"] if "permissions" in job else workflow.get("permissions"))


def uses(step: dict) -> str:
    return str(step.get("uses", "")).split("@")[0]


def render_job(film: dict) -> tuple[str, dict]:
    found = [(name, job) for name, job in jobs(film).items()
             if any(RENDER.search(str(s.get("run", ""))) for s in job.get("steps") or [])]
    assert len(found) == 1, f"film.yml runs `task film` in {len(found)} jobs, expected one"
    return found[0]


def deploy_job(film: dict) -> tuple[str, dict]:
    found = [(name, job) for name, job in jobs(film).items()
             if any(uses(s) == "actions/deploy-pages" for s in job.get("steps") or [])]
    assert len(found) == 1, f"film.yml deploys with actions/deploy-pages in {len(found)} jobs, expected one"
    return found[0]


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


def nothing_writes_a_release(film: dict) -> None:
    """ADR-0040: no release is made or uploaded to, and no job or the workflow writes contents."""
    text = FILM.read_text(encoding="utf-8")
    assert "gh release" not in text, "film.yml still runs `gh release`"
    released = [uses(s) for s in steps(film) if "release" in uses(s).lower()]
    assert not released, f"film.yml still uses release actions {released}"
    scopes = [("the workflow", film.get("permissions"))]
    scopes += [(f"job {name}", job["permissions"]) for name, job in jobs(film).items() if "permissions" in job]
    for where, permissions in scopes:
        level = grants(permissions).get("contents")
        assert level != "write", f"film.yml grants contents: write in {where}"
        assert permissions != "write-all", f"film.yml grants write-all in {where}"


def render_reads_only(film: dict) -> None:
    """AC11: the workflow's permissions are contents: read, and the render job holds only that."""
    assert grants(film.get("permissions")) == {"contents": "read"}, (
        f"film.yml's workflow permissions are {film.get('permissions')}, expected contents: read only"
    )
    name, job = render_job(film)
    assert effective(film, job) == {"contents": "read"}, (
        f"film.yml's {name} job holds {effective(film, job)}, expected contents: read only"
    )


def models_are_cached(film: dict) -> None:
    """AC11: the render job restores and saves .models/ under a key hashed from the file that pins
    the Kokoro checksums."""
    _, job = render_job(film)
    job_steps = job.get("steps") or []
    caches = [s for s in job_steps if uses(s) in ("actions/cache", "actions/cache/restore", "actions/cache/save")
              and ".models" in str((s.get("with") or {}).get("path", ""))]
    kinds = {uses(s) for s in caches}
    assert "actions/cache" in kinds or {"actions/cache/restore", "actions/cache/save"} <= kinds, (
        f"film.yml's render job does not both restore and save .models/ (it uses {sorted(kinds)})"
    )
    for step in caches:
        key = str((step.get("with") or {}).get("key", ""))
        hashed = HASH_FILES.findall(key)
        assert hashed, f"film.yml caches .models/ under {key!r}, not keyed via hashFiles"
        pins = [REPO / path for path in hashed if (REPO / path).is_file()
                and re.search(r"\b[0-9a-f]{64}\b", (REPO / path).read_text(encoding="utf-8"))]
        assert pins, f"film.yml's cache key {key!r} hashes no file that pins a SHA-256 checksum"
    if "actions/cache" not in kinds:
        restore = [i for i, s in enumerate(job_steps) if uses(s) == "actions/cache/restore"]
        save = [i for i, s in enumerate(job_steps) if uses(s) == "actions/cache/save"]
        assert min(restore) < max(save), "film.yml saves the Kokoro cache before restoring it"


def render_uploads_the_site(film: dict) -> None:
    """AC11: in the render job, the render runs before an upload-pages-artifact step whose site
    holds src/film/site/index.html and the MP4."""
    _, job = render_job(film)
    job_steps = job.get("steps") or []
    runs = [str(s.get("run", "")) for s in job_steps]
    rendered = [i for i, run in enumerate(runs) if RENDER.search(run)]
    uploads = [i for i, s in enumerate(job_steps) if uses(s) == "actions/upload-pages-artifact"]
    assert len(uploads) == 1, f"film.yml's render job has {len(uploads)} upload-pages-artifact steps, expected one"
    (upload,) = uploads
    assert min(rendered) < upload, "film.yml uploads the Pages artifact before it renders"
    site = str((job_steps[upload].get("with") or {}).get("path", "")).rstrip("/")
    assert site, "film.yml's upload-pages-artifact step names no path"
    staged = " ".join(runs[:upload])
    assert PAGE in staged and ASSET in staged and site in staged, (
        f"before its upload, film.yml's render job does not put {PAGE} and {ASSET} into {site}/"
    )


def deploy_is_gated(film: dict) -> None:
    """AC11: the deploy job runs only on refs/heads/main, needs the render, holds pages: write and
    id-token: write, runs in github-pages, is not cancelled in progress and uses deploy-pages."""
    render, _ = render_job(film)
    name, job = deploy_job(film)
    condition = str(job.get("if", ""))
    assert re.search(r"github\.ref\s*==\s*'refs/heads/main'", condition), (
        f"film.yml's {name} job runs on {condition!r}, not only on refs/heads/main"
    )
    needs = job.get("needs")
    needs = [needs] if isinstance(needs, str) else list(needs or [])
    assert render in needs, f"film.yml's {name} job needs {needs}, not the {render} job"
    held = effective(film, job)
    assert held.get("pages") == "write" and held.get("id-token") == "write", (
        f"film.yml's {name} job holds {held}, expected pages: write and id-token: write"
    )
    environment = job.get("environment")
    environment = environment.get("name") if isinstance(environment, dict) else environment
    assert environment == "github-pages", f"film.yml's {name} job runs in environment {environment!r}"
    concurrency = job.get("concurrency") or film.get("concurrency")
    assert concurrency, f"film.yml's {name} job has no concurrency group"
    if isinstance(concurrency, dict):
        assert concurrency.get("group"), f"film.yml's {name} job's concurrency names no group"
        assert concurrency.get("cancel-in-progress") in (None, False), (
            f"film.yml's {name} job cancels a deploy in progress: {concurrency}"
        )


def actions_are_pinned(film: dict) -> None:
    """AC11: every `uses:` in film.yml is pinned to a 40-hex commit SHA."""
    loose = [str(s["uses"]) for s in steps(film) if "uses" in s and not PINNED.match(str(s["uses"]))]
    loose += [str(j["uses"]) for j in jobs(film).values() if "uses" in j and not PINNED.match(str(j["uses"]))]
    assert not loose, f"film.yml's actions not pinned to a commit SHA: {loose}"


def ci_reads_and_installs_chromium() -> None:
    """AC11: ci.yml keeps contents: read, and its test job installs Chromium for the stills."""
    ci = load(CI)
    assert grants(ci.get("permissions")).get("contents") == "read", (
        f"ci.yml's top-level contents is {ci.get('permissions')}"
    )
    for name, job in jobs(ci).items():
        if "permissions" in job:
            assert grants(job["permissions"]).get("contents") in (None, "read", "none"), (
                f"ci.yml's {name} job raises contents to {job['permissions']}"
            )
    tests = [name for name, job in jobs(ci).items()
             if any(re.search(r"\bpytest\b", str(s.get("run", ""))) for s in job.get("steps") or [])]
    assert tests, "ci.yml runs no pytest"
    for name in tests:
        runs = [str(s.get("run", "")) for s in jobs(ci)[name].get("steps") or []]
        assert any(re.search(r"playwright install\b.*\bchromium\b", run) for run in runs), (
            f"ci.yml's {name} job does not install Chromium"
        )


def test_film_workflow():
    """AC11: film.yml's triggers and paths, its read-only render with the Kokoro cache and the
    Pages artifact, its gated deploy to GitHub Pages, its pinned actions and no release; ci.yml
    keeps contents: read and installs Chromium."""
    film = load(FILM)
    triggers_are_1b(film)
    nothing_writes_a_release(film)
    render_reads_only(film)
    models_are_cached(film)
    render_uploads_the_site(film)
    deploy_is_gated(film)
    actions_are_pinned(film)
    ci_reads_and_installs_chromium()


class Videos(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.doctype = False
        self.videos: list[dict] = []

    def handle_decl(self, decl: str) -> None:
        self.doctype = self.doctype or decl.lower().startswith("doctype html")

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag == "video":
            self.videos.append(dict(attrs))


def test_film_workflow_site_page():
    """[1b], ADR-0040: the site's page is an HTML page with one <video> playing the MP4 beside it,
    with controls and playsinline."""
    page = REPO / PAGE
    assert page.is_file(), f"{PAGE} does not exist"
    parsed = Videos()
    parsed.feed(page.read_text(encoding="utf-8"))
    assert parsed.doctype, f"{PAGE} does not declare <!doctype html>"
    assert len(parsed.videos) == 1, f"{PAGE} holds {len(parsed.videos)} <video> elements, expected one"
    (video,) = parsed.videos
    assert video.get("src") == ASSET, f"{PAGE}'s video plays {video.get('src')!r}, expected {ASSET!r}"
    assert "controls" in video and "playsinline" in video, f"{PAGE}'s video lacks controls or playsinline: {video}"
