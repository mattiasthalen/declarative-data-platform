"""Story 6's decisions, addenda, term, assumptions and measurements are recorded (AC16).

The ADRs' file names, the addenda's date, the headword and the assumption ids were fixed in the
spec's record drafts, so the tests name them.
"""

from __future__ import annotations

import re

import pytest
from harness import REPO

DOCS = REPO / "docs"
ADR = DOCS / "adr"
ADRS = {
    "0036": "0036-load-a-to-one-tie-as-an-attribute-of-its-identifier-role.md",
    "0037": "0037-resolve-a-ties-reference-through-the-other-anchors-key-and-skip-one-not-yet-known.md",
    "0038": "0038-split-a-staged-bridge-at-every-change-of-what-it-reaches-over-to-one-ties.md",
    "0039": "0039-backfill-a-ties-first-version-in-serve-as-an-attributes.md",
}


def addenda(prefix: str, day: str) -> list[str]:
    """The ``## Addendum <day>`` sections of the ADR numbered ``prefix``."""
    (path,) = ADR.glob(f"{prefix}-*.md")
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"^(?=## )", text, flags=re.MULTILINE)
    return [s for s in sections if re.match(rf"## Addendum {day}\s*$", s.splitlines()[0])]


def assumption_rows() -> list[str]:
    text = (DOCS / "assumptions.md").read_text(encoding="utf-8")
    return [line for line in text.splitlines() if re.match(r"^\| A\d+ \|", line)]


@pytest.mark.parametrize("number", sorted(ADRS))
def test_story6_adrs_are_recorded_and_indexed(number):
    """AC16: ADR-0036 to ADR-0039 are in docs/adr/, accepted, and one row of the index links each."""
    name = ADRS[number]
    path = ADR / name
    assert path.exists(), f"docs/adr/{name} is missing"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith(f"# ADR-{number}"), lines[0]
    assert any(re.match(r"\*\*Status:\*\* Accepted", line) for line in lines), f"ADR-{number} is not Accepted"
    index = (ADR / "README.md").read_text(encoding="utf-8").splitlines()
    rows = [line for line in index if f"({name})" in line]
    assert len(rows) == 1, f"docs/adr/README.md has {len(rows)} rows linking {name}"
    assert number in rows[0] and "Accepted" in rows[0], rows[0]


@pytest.mark.parametrize(("prefix", "named"), [("0006", ("0036",)), ("0011", ("0038", "0039"))])
def test_story6_addenda(prefix, named):
    """AC16: ADR-0006 and ADR-0011 carry one 2026-11-03 addendum each, naming the ADRs it points to."""
    found = addenda(prefix, "2026-11-03")
    assert len(found) == 1, f"ADR-{prefix} has {len(found)} 'Addendum 2026-11-03' sections"
    for number in named:
        assert f"({ADRS[number]})" in found[0] or f"ADR-{number}" in found[0], (
            f"ADR-{prefix}'s addendum does not name ADR-{number}"
        )


def test_pit_key_is_in_the_lexicon():
    """AC16: docs/lexicon.md defines *PIT key*, pointing at ADR-0038."""
    text = (DOCS / "lexicon.md").read_text(encoding="utf-8")
    entry = re.search(r"^\*\*PIT key\*\*.*$", text, re.MULTILINE)
    assert entry, "docs/lexicon.md has no **PIT key** entry"
    assert "0038" in entry.group(0), entry.group(0)


def test_story6_assumptions():
    """AC16: docs/assumptions.md has one A32 row and no repeated id; A2 is widened to subcategories, A20 to
    the committed subcategory snapshot; the 2026-11-02 feed measurements name the 37 subcategories."""
    rows = assumption_rows()
    ids = [row.split("|")[1].strip() for row in rows]
    assert len(ids) == len(set(ids)), f"assumption ids repeat: {sorted(i for i in ids if ids.count(i) > 1)}"
    a32 = [row for row in rows if row.startswith("| A32 ")]
    assert len(a32) == 1, "docs/assumptions.md has no A32 row"
    assert "ProductSubcategoryId" in a32[0], a32[0]
    (a2,) = [row for row in rows if row.startswith("| A2 ")]
    assert "subcategor" in a2.lower(), f"A2 is not widened to subcategories: {a2}"
    (a20,) = [row for row in rows if row.startswith("| A20 ")]
    assert "adventure_works__product_subcategories.jsonl" in a20, f"A20 does not name the subcategory snapshot: {a20}"

    text = (DOCS / "assumptions.md").read_text(encoding="utf-8")
    sections = re.split(r"^(?=## )", text, flags=re.MULTILINE)
    measured = [
        s for s in sections if re.match(r"## Measured \(2026-11-02, the AdventureWorks OData feed\)", s.splitlines()[0])
    ]
    assert len(measured) == 1, "docs/assumptions.md has no 'Measured (2026-11-02, the AdventureWorks OData feed)' section"
    assert "ProductSubcategories" in measured[0] and "37" in measured[0], measured[0]
