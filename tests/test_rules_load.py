"""AC1-AC3, EC1-EC4: reading a file loads exactly its layers' rules files, through their patterns.

Each case runs a headless ``claude -p`` session in a throwaway copy of the repo, makes it Read
one file, and reads back what Claude Code reported to its ``InstructionsLoaded`` hook. The hook
lives in a settings file passed with ``--settings``, so neither the working tree nor the user's
Claude settings are touched. Run with ``uv run pytest -m claude``; the default run deselects it.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import pytest

from harness import REPO

pytestmark = pytest.mark.claude

MODEL = "haiku"
SESSION_TIMEOUT = 300

# Files the copy gains, which the repo does not hold: path -> text.
CREATED_IN_THE_COPY = {
    # Under models/serve/ outside the USS folders, which no generator owns.
    "models/serve/marts/hand_written_orders.sql": (
        "-- hand-written serve model, outside the USS\nselect 1 as one\n"
    ),
    # A folder named anchor that is not the root's: /anchor/** must not match it.
    "docs/anchor/notes.md": "# notes filed under a nested anchor folder\n",
}

# The parent session's identity and remote wiring; the child must start a session of its own.
PARENT_SESSION_ENV = re.compile(
    r"^(CLAUDE_CODE_SESSION_ID|CLAUDECODE|CLAUDE_CODE_REMOTE.*|SESSION_INGRESS.*"
    r"|CLAUDE_ADDITIONAL_DIRECTORIES)$"
)


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
    for relative, text in CREATED_IN_THE_COPY.items():
        created = ws.root / relative
        created.parent.mkdir(parents=True, exist_ok=True)
        created.write_text(text)
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
                "--setting-sources",
                "project",
                "--tools",
                "Read",
                "--strict-mcp-config",
                "--no-session-persistence",
                "--max-turns",
                "4",
                "--output-format",
                "json",
            ],
            cwd=workspace,
            env={k: v for k, v in os.environ.items() if not PARENT_SESSION_ENV.match(k)},
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


def first_under(pattern: str) -> str:
    """The first file matching ``pattern`` in the repo, so the row survives files moving."""
    found = sorted(p.relative_to(REPO).as_posix() for p in REPO.glob(pattern) if p.is_file())
    assert found, f"no file in the repo matches {pattern}"
    return found[0]


# The file a session reads -> exactly the rules files that must load. One row per pattern, so
# a typo in any pattern fails a row.
EXPECTED_RULES = {
    "src/ingest/__init__.py": {"ingest"},  # **/ingest/**
    "src/conform/__init__.py": {"conform"},  # **/conform/**
    first_under("contracts/**/*.yaml"): {"conform"},  # /contracts/**
    first_under("models/raw/**/*.sql"): {"conform"},  # /models/raw/**
    "src/integrate/__init__.py": {"integrate"},  # **/integrate/**
    "anchor/model.yaml": {"integrate"},  # /anchor/**
    "src/serve/__init__.py": {"serve", "uss"},  # **/serve/**, /src/serve/**
    "macros/serve/uss.sql": {"serve", "uss"},  # /macros/serve/**
    "models/serve/uss/product.sql": {"serve", "uss"},  # /models/serve/uss*/**
    "models/serve/marts/hand_written_orders.sql": {"serve"},  # AC2: not uss
    "docs/lexicon.md": set(),  # AC3
    "docs/anchor/notes.md": set(),  # /anchor/** is anchored at the root
}


@pytest.mark.parametrize("relative", EXPECTED_RULES)
def test_reading_a_file_loads_exactly_its_rules(read_in_claude, relative):
    """AC1-AC3, EC2: reading the file loads exactly the expected rules files, by path match."""
    session = read_in_claude(relative)
    loaded = session.rules_loaded()
    expected = EXPECTED_RULES[relative]
    assert set(loaded) == expected, (
        f"reading {relative} loaded {sorted(loaded)}, expected {sorted(expected)}"
    )
    for rules in expected:
        load = loaded[rules]
        assert load.get("load_reason") == "path_glob_match", load
        trigger = Path(load.get("trigger_file_path", "")).resolve()
        assert trigger == (session.workspace / relative).resolve(), load
