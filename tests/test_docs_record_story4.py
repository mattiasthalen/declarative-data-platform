"""Story 4's decision, addenda, term and assumption are recorded (AC9, AC10).

ADR-0030's number and A24's id were fixed at spec time, so the tests name them.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from harness import REPO

DOCS = REPO / "docs"
ADR = DOCS / "adr"
PIT_ADR = "0030-expose-the-point-in-time-perspective-as-a-duckdb-table-macro.md"
SIMULATE = REPO / "src" / "simulate"
DROP_OUT = "run that completes"


def addenda(prefix: str, day: str) -> list[str]:
    """The ``## Addendum <day>`` sections of the ADR numbered ``prefix``."""
    (path,) = ADR.glob(f"{prefix}-*.md")
    text = path.read_text(encoding="utf-8")
    sections = re.split(r"^(?=## )", text, flags=re.MULTILINE)
    return [s for s in sections if re.match(rf"## Addendum {day}\s*$", s.splitlines()[0])]


def test_pit_adr_is_recorded_and_indexed():
    """AC10: ADR-0030 is in docs/adr/, accepted, and one row of the index links it."""
    path = ADR / PIT_ADR
    assert path.exists(), f"docs/adr/{PIT_ADR} is missing"
    lines = path.read_text(encoding="utf-8").splitlines()
    assert lines[0].startswith("# ADR-0030"), lines[0]
    assert "table macro" in lines[0].lower(), lines[0]
    assert any(re.match(r"\*\*Status:\*\* Accepted", line) for line in lines), "ADR-0030 is not Accepted"
    rows = [line for line in (ADR / "README.md").read_text(encoding="utf-8").splitlines() if f"({PIT_ADR})" in line]
    assert len(rows) == 1, f"docs/adr/README.md has {len(rows)} rows linking {PIT_ADR}"
    assert "0030" in rows[0] and "Accepted" in rows[0], rows[0]


def test_adr_0011_addendum_keeps_backfill_in_serve():
    """AC10: ADR-0011 carries the 2026-11-01 addendum: the backfill is serve's, and it links ADR-0030."""
    found = addenda("0011", "2026-11-01")
    assert len(found) == 1, f"ADR-0011 has {len(found)} 'Addendum 2026-11-01' sections"
    assert f"({PIT_ADR})" in found[0], "ADR-0011's addendum does not link ADR-0030"
    assert "pPR_Product" in found[0] and "0001-01-01" in found[0], found[0]


def test_adr_0027_addendum_bounds_the_drop_out():
    """AC9: ADR-0027 carries the 2026-11-01 addendum saying a drop out lasts one load within a run that completes."""
    found = addenda("0027", "2026-11-01")
    assert len(found) == 1, f"ADR-0027 has {len(found)} 'Addendum 2026-11-01' sections"
    assert DROP_OUT in found[0], found[0]


def _docstrings(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    nodes = [tree, *(n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.ClassDef)))]
    return [ast.get_docstring(n) or "" for n in nodes]


def test_simulator_says_drop_out_holds_within_a_run_that_completes():
    """AC9: a docstring of the simulator and src/simulate/README.md say a drop out lasts one load within a
    run that completes."""
    said = [d for d in _docstrings(SIMULATE / "__init__.py") if DROP_OUT in " ".join(d.split())]
    assert said, f"no docstring in src/simulate/__init__.py says {DROP_OUT!r}"
    readme = " ".join((SIMULATE / "README.md").read_text(encoding="utf-8").split())
    assert DROP_OUT in readme, f"src/simulate/README.md does not say {DROP_OUT!r}"


def test_backfill_is_in_the_lexicon():
    """AC10: docs/lexicon.md defines *backfill* as serve's, with 0001-01-01."""
    text = (DOCS / "lexicon.md").read_text(encoding="utf-8")
    entry = re.search(r"^\*\*backfill\*\*.*$", text, re.MULTILINE)
    assert entry, "docs/lexicon.md has no **backfill** entry"
    assert "0001-01-01" in entry.group(0) and "serve" in entry.group(0).lower(), entry.group(0)


def test_pit_macro_is_assumed_as_a24():
    """AC10: docs/assumptions.md has one A24 row, about the macro, and assumption ids do not repeat."""
    rows = [line for line in (DOCS / "assumptions.md").read_text(encoding="utf-8").splitlines() if re.match(r"^\| A\d+ \|", line)]
    ids = [row.split("|")[1].strip() for row in rows]
    assert len(ids) == len(set(ids)), f"assumption ids repeat: {sorted(i for i in ids if ids.count(i) > 1)}"
    a24 = [row for row in rows if row.startswith("| A24 ")]
    assert len(a24) == 1, "docs/assumptions.md has no A24 row"
    assert "macro" in a24[0].lower(), a24[0]
