"""Story 2's decisions, term and assumptions are recorded in docs/ (AC15)."""

from __future__ import annotations

import re

from harness import REPO

DOCS = REPO / "docs"


def index_row(phrase: str) -> str:
    rows = [line for line in (DOCS / "adr" / "README.md").read_text(encoding="utf-8").splitlines() if phrase in line]
    assert rows, f"docs/adr/README.md has no row with {phrase!r}"
    return rows[0]


def test_both_adrs_are_indexed_and_exist():
    """AC15: the two ADRs are in docs/adr/ and its index."""
    for phrase in ("byte for byte", "Require CI"):
        links = re.findall(r"\]\(([^)]+\.md)\)", index_row(phrase))
        assert links, f"the index row for {phrase!r} links no record"
        assert (DOCS / "adr" / links[0]).is_file(), f"docs/adr/{links[0]} does not exist"


def test_drift_is_in_the_lexicon():
    """AC15: **drift** is a lexicon entry."""
    text = (DOCS / "lexicon.md").read_text(encoding="utf-8")
    assert re.search(r"^\*\*drift\*\*", text, re.MULTILINE), "docs/lexicon.md has no **drift** entry"


def test_both_assumptions_are_recorded():
    """AC15: CI needs no live source; the suite fits a runner's time."""
    text = (DOCS / "assumptions.md").read_text(encoding="utf-8").lower()
    assert "live source" in text, "docs/assumptions.md does not assume CI needs no live source"
    assert "runner" in text, "docs/assumptions.md does not assume the suite fits a runner's time"
