"""AC1-AC3, EC1-EC4: reading a file loads exactly its layers' rules files, through their patterns.

Each case runs a headless ``claude -p`` session in a throwaway copy of the repo, makes it Read
one file, and reads back what Claude Code reported to its ``InstructionsLoaded`` hook, and to a
``PostToolUse`` hook on Read that proves the file was read. The hooks live in a settings file
passed with ``--settings``, so neither the working tree nor the user's
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

# The parent session's identity, wiring and behaviour switches; the child must start a plain
# session of its own. Auth does not depend on any of these (checked live).
PARENT_SESSION_ENV = re.compile(
    r"^(CLAUDE_CODE_|CLAUDE_SESSION_|SESSION_INGRESS)"
    r"|^(CLAUDECODE|CLAUDE_PID|CLAUDE_ADDITIONAL_DIRECTORIES)$"
)


@dataclass
class Session:
    workspace: Path
    reply: str
    loads: list[dict]
    reads: list[dict]

    def rules_loaded(self) -> dict[str, dict]:
        """The workspace's ``.claude/rules/<name>.md`` files reported loaded, by name."""
        rules_dir = (self.workspace / ".claude" / "rules").resolve()
        loaded = {}
        for load in self.loads:
            path = Path(load.get("file_path", "")).resolve()
            if path.parent == rules_dir and path.suffix == ".md":
                loaded[path.stem] = load
        return loaded

    def assert_read(self, relative: str) -> None:
        # The hook cannot show a Read when no rules file matched; the PostToolUse log can.
        target = (self.workspace / relative).resolve()
        read = [
            Path(self.workspace, r.get("tool_input", {}).get("file_path", "")).resolve()
            for r in self.reads
        ]
        assert target in read, (
            f"the session never read {relative}: PostToolUse(Read) logged {read}; "
            f"reply was {self.reply!r}"
        )

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
    assert after[0] == before[0], (
        f"git status changed:\nbefore:\n{before[0]}\nafter:\n{after[0]}"
    )
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
        assert target.is_file(), (
            f"representative file {relative} is missing from the repo"
        )
        claude = shutil.which("claude")
        if claude is None:
            pytest.fail(
                "claude is not on PATH: the live rules test needs the Claude Code CLI"
            )

        def appending_to(log: Path) -> list[dict]:
            log.touch()
            quoted = shlex.quote(str(log))
            return [
                {"type": "command", "command": f"cat >> {quoted}; echo >> {quoted}"}
            ]

        loads_log = tmp_path / "instructions_loaded.jsonl"
        reads_log = tmp_path / "reads.jsonl"
        settings = tmp_path / "settings.json"
        settings.write_text(
            json.dumps(
                {
                    "hooks": {
                        "InstructionsLoaded": [{"hooks": appending_to(loads_log)}],
                        "PostToolUse": [
                            {"matcher": "Read", "hooks": appending_to(reads_log)}
                        ],
                    }
                }
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
            env={
                k: v for k, v in os.environ.items() if not PARENT_SESSION_ENV.match(k)
            },
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
        session = Session(
            workspace=workspace,
            reply=reply,
            loads=json_lines(loads_log),
            reads=json_lines(reads_log),
        )
        session.assert_read(relative)
        session.assert_root_claude_md_loaded()
        return session

    return run


def json_lines(log: Path) -> list[dict]:
    return [json.loads(line) for line in log.read_text().splitlines() if line.strip()]


def first_under(pattern: str) -> str:
    """The first file matching ``pattern`` in the repo, so the row survives files moving."""
    found = sorted(
        p.relative_to(REPO).as_posix() for p in REPO.glob(pattern) if p.is_file()
    )
    assert found, f"no file in the repo matches {pattern}"
    return found[0]


# The file a session reads -> exactly the rules files that must load. One row per pattern, so
# a typo in any pattern fails a row. A ``glob:`` key is resolved by first_under() inside the
# test, so a missing file fails its row rather than collection of the default run.
EXPECTED_RULES = {
    "src/ingest/__init__.py": {"ingest"},  # **/ingest/**
    "src/conform/__init__.py": {"conform"},  # **/conform/**
    "glob:contracts/**/*.yaml": {"conform"},  # /contracts/**
    "glob:models/raw/**/*.sql": {"conform"},  # /models/raw/**
    "src/integrate/__init__.py": {"integrate"},  # **/integrate/**
    "anchor/model.yaml": {"integrate"},  # /anchor/**
    "src/serve/__init__.py": {"serve", "uss"},  # **/serve/**, /src/serve/**
    "macros/serve/uss.sql": {"serve", "uss"},  # /macros/serve/**
    "models/serve/uss/product.sql": {"serve", "uss"},  # /models/serve/uss*/**
    "models/serve/marts/hand_written_orders.sql": {"serve"},  # AC2: not uss
    "docs/lexicon.md": set(),  # AC3
    "docs/anchor/notes.md": set(),  # /anchor/** is anchored at the root
}


@pytest.mark.parametrize("row", EXPECTED_RULES)
def test_reading_a_file_loads_exactly_its_rules(read_in_claude, row):
    """AC1-AC3, EC2: reading the file loads exactly the expected rules files, by path match."""
    expected = EXPECTED_RULES[row]
    relative = (
        first_under(row.removeprefix("glob:")) if row.startswith("glob:") else row
    )
    session = read_in_claude(relative)
    loaded = session.rules_loaded()
    assert set(loaded) == expected, (
        f"reading {relative} loaded {sorted(loaded)}, expected {sorted(expected)}"
    )
    for rules in expected:
        load = loaded[rules]
        assert load.get("load_reason") == "path_glob_match", load
        trigger = Path(load.get("trigger_file_path", "")).resolve()
        assert trigger == (session.workspace / relative).resolve(), load
