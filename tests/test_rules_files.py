"""AC5, AC7-AC10: what holds the per-layer rules in place without running Claude."""

from __future__ import annotations

import re
import subprocess
import sys

import yaml

from harness import REPO

LIVE_TEST = "tests/test_rules_load.py"


def test_no_rules_file_mentions_the_snowflake_skill():
    """AC5: the Snowflake skill reference is gone from CLAUDE.md and .claude/."""
    files = [REPO / "CLAUDE.md", *(p for p in (REPO / ".claude").rglob("*") if p.is_file())]
    mentions = [
        str(path.relative_to(REPO))
        for path in files
        if "anchor-snowflake-skill" in path.read_text(errors="replace")
    ]
    assert not mentions, f"still mention anchor-snowflake-skill: {mentions}"


def test_the_root_of_macros_holds_only_generate_schema_name():
    """AC7: no layer macro is left at the root of macros/."""
    at_root = sorted(p.name for p in (REPO / "macros").glob("*.sql"))
    assert at_root == ["generate_schema_name.sql"], at_root


def test_each_layer_macro_lives_under_its_layer():
    """AC7: the layer macros moved to macros/<layer>/, one copy each."""
    expected = {
        "read_lake.sql": "conform",
        "anchor.sql": "integrate",
        "batch_log.sql": "integrate",
        "uss.sql": "serve",
    }
    for name, layer in expected.items():
        found = sorted(p.relative_to(REPO).as_posix() for p in (REPO / "macros").rglob(name))
        assert len(found) == 1, f"{name}: expected one copy under macros/{layer}/, found {found}"
        assert found[0].startswith(f"macros/{layer}/"), f"{name} is at {found[0]}"


def collect(*args: str, strict_markers: bool = True) -> subprocess.CompletedProcess:
    strict = ["--strict-markers"] if strict_markers else []
    return subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", *strict, *args, LIVE_TEST],
        cwd=REPO,
        capture_output=True,
        text=True,
    )


def test_the_default_run_deselects_the_live_tests():
    """AC8: plain pytest collects no claude-marked test and says it deselected them."""
    result = collect()
    output = result.stdout + result.stderr
    assert result.returncode in (0, 5), output
    assert f"{LIVE_TEST}::" not in output, output
    assert "deselected" in output, output


def test_the_claude_marker_selects_the_live_tests():
    """AC8: -m claude collects the live tests; --strict-markers proves the marker registered."""
    result = collect("-m", "claude")
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert f"{LIVE_TEST}::" in output, output


def test_another_mark_expression_does_not_select_the_live_tests():
    """AC12: a -m that does not name claude, like "not nonexistent", still deselects them."""
    # --strict-markers would refuse the unregistered marker before collecting anything.
    result = collect("-m", "not nonexistent", strict_markers=False)
    output = result.stdout + result.stderr
    assert result.returncode in (0, 5), output
    assert f"{LIVE_TEST}::" not in output, output
    assert "deselected" in output, output


def test_task_test_rules_runs_the_claude_marked_tests():
    """AC9: Taskfile.yml has test-rules, running pytest -m claude."""
    tasks = yaml.safe_load((REPO / "Taskfile.yml").read_text())["tasks"]
    assert "test-rules" in tasks, sorted(tasks)
    cmds = tasks["test-rules"].get("cmds", [])
    commands = [c if isinstance(c, str) else c.get("cmd", "") for c in cmds]
    assert any(re.search(r"\bpytest\b.*-m[ =]['\"]?claude\b", c) for c in commands), commands


def test_adr_0013_is_indexed_and_partly_supersedes_0012():
    """AC10: ADR-0013 is in the index; ADR-0012's status names it."""
    adr = REPO / "docs" / "adr"
    assert list(adr.glob("0013-*.md")), "no docs/adr/0013-*.md"
    assert "[0013](0013-" in (adr / "README.md").read_text()
    (adr_0012,) = adr.glob("0012-*.md")
    status = next(line for line in adr_0012.read_text().splitlines() if line.startswith("**Status:**"))
    assert re.search(
        r"partly superseded by (ADR-0013\b|\[ADR-0013\]\(0013-[^)]*\.md\))", status, re.IGNORECASE
    ), status


def test_assumptions_a7_and_a8_are_recorded():
    """AC10: docs/assumptions.md has rows A7 and A8."""
    text = (REPO / "docs" / "assumptions.md").read_text()
    for row in ("A7", "A8"):
        assert re.search(rf"^\| {row} ", text, re.MULTILINE), f"no row {row}"
