"""Story 3's decision, terms and assumption are recorded in docs/ (AC11).

The ADR's number and the assumption's id are taken at PR time, so the tests find the ADR by its
title and the assumption by what it says, not by number.
"""

from __future__ import annotations

import re
from pathlib import Path

from harness import REPO

DOCS = REPO / "docs"
ADR = DOCS / "adr"
TITLE = "let a generator own a marked region of a hand-written file"


def owned_region_adr() -> Path:
    found = [
        path
        for path in sorted(ADR.glob("[0-9][0-9][0-9][0-9]-*.md"))
        if TITLE in path.read_text(encoding="utf-8").splitlines()[0].lower()
    ]
    assert len(found) == 1, f"expected one ADR titled {TITLE!r} in docs/adr/, found {[p.name for p in found]}"
    return found[0]


def test_owned_region_adr_is_indexed():
    """AC11: the ADR is in docs/adr/ and a row of its index links it."""
    name = owned_region_adr().name
    rows = [line for line in (ADR / "README.md").read_text(encoding="utf-8").splitlines() if f"({name})" in line]
    assert len(rows) == 1, f"docs/adr/README.md has {len(rows)} rows linking {name}"


def test_adr_0012_and_0013_carry_a_dated_addendum_linking_it():
    """AC11: ADR-0012 and ADR-0013 each carry a dated addendum that links the new ADR."""
    adr = owned_region_adr()
    number = adr.name[:4]
    for prefix in ("0012", "0013"):
        (path,) = ADR.glob(f"{prefix}-*.md")
        text = path.read_text(encoding="utf-8")
        addenda = re.split(r"^(?=## Addendum \d{4}-\d{2}-\d{2}\s*$)", text, flags=re.MULTILINE)[1:]
        linking = [a for a in addenda if f"({adr.name})" in a or re.search(rf"\]\([^)]*{number}-", a)]
        assert linking, f"{path.name} has no dated addendum linking {adr.name}"


def test_owned_region_is_in_the_lexicon_and_drift_covers_it():
    """AC11: docs/lexicon.md defines *owned region*, and *drift* is widened to cover it."""
    text = (DOCS / "lexicon.md").read_text(encoding="utf-8")
    assert re.search(r"^\*\*owned region\*\*", text, re.MULTILINE | re.IGNORECASE), "no **owned region** entry"
    drift = re.search(r"^\*\*drift\*\*.*$", text, re.MULTILINE)
    assert drift, "no **drift** entry"
    assert "region" in drift.group(0).lower(), f"*drift* does not cover owned regions: {drift.group(0)}"


def test_github_renders_the_diagrams_is_assumed():
    """AC11: docs/assumptions.md holds a new assumption that GitHub renders the README's erDiagrams."""
    rows = [line for line in (DOCS / "assumptions.md").read_text(encoding="utf-8").splitlines() if re.match(r"^\| A\d+ \|", line)]
    ids = [row.split("|")[1].strip() for row in rows]
    assert len(ids) == len(set(ids)), f"assumption ids repeat: {sorted(i for i in ids if ids.count(i) > 1)}"
    found = [row for row in rows if "github" in row.lower() and re.search(r"mermaid|erdiagram", row, re.IGNORECASE)]
    assert found, "docs/assumptions.md has no assumption that GitHub renders the README's Mermaid erDiagrams"
