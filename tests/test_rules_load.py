"""AC1-AC3, EC1, EC3, EC4: Claude Code loads each layer's rules file, and only it.

Each case runs a headless ``claude -p`` session in a throwaway copy of the repo, makes it Read
one file, and reads back what Claude Code reported to its ``InstructionsLoaded`` hook. The hook
lives in a settings file passed with ``--settings``, so neither the working tree nor the user's
Claude settings are touched. Run with ``uv run pytest -m claude``; the default run deselects it.
"""

from __future__ import annotations

import json
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from harness import REPO

pytestmark = pytest.mark.claude

RULES = ("ingest", "conform", "integrate", "serve", "uss")
MODEL = "haiku"
SESSION_TIMEOUT = 300

# A file under models/serve/ outside the USS folders, which no generator owns.
HAND_WRITTEN_SERVE = "models/serve/marts/hand_written_orders.sql"
HAND_WRITTEN_SERVE_TEXT = "-- hand-written serve model, outside the USS\nselect 1 as one\n"


@dataclass
class Session:
    workspace: Path
    reply: str
    loads: list[dict]

    def rules_loaded(self) -> dict[str, dict]:
        """The workspace's ``.claude/rules/<name>.md`` files reported loaded, by name."""
        rules_dir = (self.workspace / ".claude" / "rules").resolve()
        loaded = {}
        for load in self.loads:
            path = Path(load.get("file_path", "")).resolve()
            if path.parent == rules_dir and path.suffix == ".md":
                loaded[path.stem] = load
        return loaded

    def assert_root_claude_md_loaded(self) -> None:
        # Without this, a hook that stopped firing would pass every "not loaded" assertion.
        root = (self.workspace / "CLAUDE.md").resolve()
        reported = [Path(load.get("file_path", "")).resolve() for load in self.loads]
        assert root in reported, (
            f"InstructionsLoaded never reported the root CLAUDE.md; reported: {reported}"
        )


@pytest.fixture(scope="module")
def leaves_repo_and_user_settings_untouched():
    """EC4: a live run changes neither the repo's git status nor ``~/.claude/settings.json``."""
    user_settings = Path.home() / ".claude" / "settings.json"

    def snapshot():
        status = subprocess.run(
            ["git", "-C", str(REPO), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        settings = user_settings.read_bytes() if user_settings.exists() else None
        return status, settings

    before = snapshot()
    yield
    after = snapshot()
    assert after[0] == before[0], f"git status changed:\nbefore:\n{before[0]}\nafter:\n{after[0]}"
    assert after[1] == before[1], f"{user_settings} changed during the live run"


@pytest.fixture(scope="module")
def workspace(make_workspace, leaves_repo_and_user_settings_untouched) -> Path:
    ws = make_workspace("rules_load", sync=False)
    hand_written = ws.root / HAND_WRITTEN_SERVE
    hand_written.parent.mkdir(parents=True, exist_ok=True)
    hand_written.write_text(HAND_WRITTEN_SERVE_TEXT)
    return ws.root


@pytest.fixture
def read_in_claude(workspace, tmp_path):
    """Run one headless session that Reads ``relative`` and return what it reported."""

    def run(relative: str) -> Session:
        target = workspace / relative
        assert target.is_file(), f"representative file {relative} is missing from the repo"
        claude = shutil.which("claude")
        if claude is None:
            pytest.fail("claude is not on PATH: the live rules test needs the Claude Code CLI")

        log = tmp_path / "instructions_loaded.jsonl"
        log.touch()
        hook = f"cat >> {shlex.quote(str(log))}; echo >> {shlex.quote(str(log))}"
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps(
                {"hooks": {"InstructionsLoaded": [{"hooks": [{"type": "command", "command": hook}]}]}}
            )
        )
        prompt = (
            f"Use the Read tool to read the file {relative}. "
            "Then reply with only the exact text of its first line, nothing else."
        )
        result = subprocess.run(
            [
                claude,
                "-p",
                prompt,
                "--model",
                MODEL,
                "--settings",
                str(settings),
                "--allowedTools",
                "Read",
                "--max-turns",
                "4",
                "--output-format",
                "json",
            ],
            cwd=workspace,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=SESSION_TIMEOUT,
        )
        if result.returncode != 0:
            pytest.fail(
                f"claude exited {result.returncode} (is it logged in?)\n"
                f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
            )
        try:
            reply = json.loads(result.stdout).get("result", "")
        except json.JSONDecodeError:
            reply = result.stdout
        loads = [json.loads(line) for line in log.read_text().splitlines() if line.strip()]
        # The reply proves the Read happened, which the hook cannot show when nothing matched.
        opening = re.findall(r"\w+", target.read_text().splitlines()[0])[:3]
        replied = set(re.findall(r"\w+", reply))
        assert set(opening) <= replied, (
            f"the session did not read {relative}: expected {opening} in its reply {reply!r}"
        )
        session = Session(workspace=workspace, reply=reply, loads=loads)
        session.assert_root_claude_md_loaded()
        return session

    return run


def assert_loaded_by_reading(session: Session, rules: str, relative: str) -> None:
    loaded = session.rules_loaded()
    assert rules in loaded, (
        f"reading {relative} did not load .claude/rules/{rules}.md; loaded: {sorted(loaded)}"
    )
    load = loaded[rules]
    assert load.get("load_reason") == "path_glob_match", load
    trigger = Path(load.get("trigger_file_path", "")).resolve()
    assert trigger == (session.workspace / relative).resolve(), load


LAYER_FILES = {
    "ingest": "src/ingest/__init__.py",
    "conform": "src/conform/__init__.py",
    "integrate": "anchor/model.yaml",
    "serve": "src/serve/__init__.py",
}


@pytest.mark.parametrize("layer", LAYER_FILES)
def test_a_layer_file_loads_its_layers_rules_only(read_in_claude, layer):
    """AC1: reading a file of the layer loads its rules file and no other layer's."""
    relative = LAYER_FILES[layer]
    session = read_in_claude(relative)
    assert_loaded_by_reading(session, layer, relative)
    others = {"ingest", "conform", "integrate", "serve"} - {layer}
    if layer != "serve":
        others.add("uss")
    stray = sorted(others & session.rules_loaded().keys())
    assert not stray, f"reading {relative} also loaded other layers' rules: {stray}"


def test_a_uss_file_loads_serve_and_uss_rules(read_in_claude):
    """AC2: a USS model loads both serve.md and uss.md."""
    relative = "models/serve/uss/product.sql"
    session = read_in_claude(relative)
    assert_loaded_by_reading(session, "serve", relative)
    assert_loaded_by_reading(session, "uss", relative)
    stray = sorted({"ingest", "conform", "integrate"} & session.rules_loaded().keys())
    assert not stray, f"reading {relative} also loaded: {stray}"


def test_a_hand_written_serve_file_loads_serve_rules_not_uss(read_in_claude):
    """AC2: a serve model outside the USS folders loads serve.md and not uss.md."""
    session = read_in_claude(HAND_WRITTEN_SERVE)
    assert_loaded_by_reading(session, "serve", HAND_WRITTEN_SERVE)
    stray = sorted({"ingest", "conform", "integrate", "uss"} & session.rules_loaded().keys())
    assert not stray, f"reading {HAND_WRITTEN_SERVE} also loaded: {stray}"


def test_a_general_file_loads_no_layer_rules(read_in_claude):
    """AC3: reading docs/lexicon.md loads no layer rules file."""
    session = read_in_claude("docs/lexicon.md")
    loaded = sorted(session.rules_loaded())
    assert not loaded, f"reading docs/lexicon.md loaded layer rules: {loaded}"
