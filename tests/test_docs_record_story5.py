"""Story 5's decision, addendum, term and assumption are recorded (AC6).

ADR-0033's file name, the addendum's date, the headword and A28's id were fixed at spec time, so
the tests name them.
"""

from __future__ import annotations

import re

from harness import REPO

DOCS = REPO / "docs"
ADR = DOCS / "adr"
TT_ADR = (
    "0033-expose-the-time-traveling-perspective-as-a-duckdb-table-macro-taking-a-changing-and-a-positing-time.md"
)


def addenda(prefix: str, day: str) -> list[str]:
    """The ``## Addendum <day>`` sections of the ADR numbered ``prefix``."""
    (path,) = ADR.glob(f"{prefix}-*.md")
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"^(?=## )", text, flags=re.MULTILINE)
    return [s for s in sections if re.match(rf"## Addendum {day}\s*$", s.splitlines()[0])]


def test_tt_adr_is_recorded_and_indexed():
    """AC6: ADR-0033 is in docs/adr/, accepted, and one row of the index links it."""
    path = ADR / TT_ADR
    assert path.exists(), f"docs/adr/{TT_ADR} is missing"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# ADR-0033"), lines[0]
    assert "table macro" in lines[0].lower(), lines[0]
    assert any(re.match(r"\*\*Status:\*\* Accepted", line) for line in lines), "ADR-0033 is not Accepted"
    index = (ADR / "README.md").read_text(encoding="utf-8").splitlines()
    rows = [line for line in index if f"({TT_ADR})" in line]
    assert len(rows) == 1, f"docs/adr/README.md has {len(rows)} rows linking {TT_ADR}"
    assert "0033" in rows[0] and "Accepted" in rows[0], rows[0]


def test_adr_0030_addendum_names_adr_0033():
    """AC6: ADR-0030 carries the 2026-11-02 addendum, and it names ADR-0033."""
    found = addenda("0030", "2026-11-02")
    assert len(found) == 1, f"ADR-0030 has {len(found)} 'Addendum 2026-11-02' sections"
    assert f"({TT_ADR})" in found[0] or "ADR-0033" in found[0], "ADR-0030's addendum does not name ADR-0033"


def test_as_known_at_is_in_the_lexicon():
    """AC6: docs/lexicon.md defines *as known at*."""
    text = (DOCS / "lexicon.md").read_text(encoding="utf-8")
    entry = re.search(r"^\*\*as known at\*\*.*$", text, re.MULTILINE)
    assert entry, "docs/lexicon.md has no **as known at** entry"


def test_tt_macro_is_assumed_as_a28():
    """AC6: docs/assumptions.md has one A28 row, and assumption ids do not repeat."""
    text = (DOCS / "assumptions.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if re.match(r"^\| A\d+ \|", line)]
    ids = [row.split("|")[1].strip() for row in rows]
    assert len(ids) == len(set(ids)), f"assumption ids repeat: {sorted(i for i in ids if ids.count(i) > 1)}"
    a28 = [row for row in rows if row.startswith("| A28 ")]
    assert len(a28) == 1, "docs/assumptions.md has no A28 row"
