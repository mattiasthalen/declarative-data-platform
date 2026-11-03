"""Story #39's decisions and assumptions are recorded (AC15).

ADR-0034 (the rolling `explainer` release) and ADR-0035 (Kokoro, locally) are found by number and
indexed; ADR-0029 carries the addendum of 2026-11-02 pointing to ADR-0034; docs/assumptions.md
holds A29 (GitHub serves and plays the asset), A30 (the Kokoro files and kokoro-onnx) and A31
(the runner renders in time), each once. The lexicon is unchanged ([11]), which a diff shows.

- ``-k docs_record_story39``: AC15.
"""

from __future__ import annotations

import re
from pathlib import Path

from harness import REPO

DOCS = REPO / "docs"
ADR = DOCS / "adr"
ASSUMED = {
    "A29": ("release", "explainer"),
    "A30": ("kokoro",),
    "A31": ("runner", "render"),
}


def adr(number: str) -> Path:
    found = sorted(ADR.glob(f"{number}-*.md"))
    assert len(found) == 1, f"expected one ADR {number} in docs/adr/, found {[p.name for p in found]}"
    return found[0]


def index_rows(name: str) -> list[str]:
    return [line for line in (ADR / "README.md").read_text(encoding="utf-8").splitlines() if f"({name})" in line]


def test_docs_record_story39_adrs_are_indexed():
    """AC15: ADR-0034 and ADR-0035 are in docs/adr/, each linked by one row of its index."""
    for number, about in (("0034", "release"), ("0035", "kokoro")):
        path = adr(number)
        title = path.read_text(encoding="utf-8").splitlines()[0]
        assert title.startswith(f"# ADR-{number}") and about in title.lower(), f"{path.name}'s title is {title!r}"
        rows = index_rows(path.name)
        assert len(rows) == 1, f"docs/adr/README.md has {len(rows)} rows linking {path.name}"


def test_docs_record_story39_addendum():
    """AC15: ADR-0029 has a section "Addendum 2026-11-02" that points to ADR-0034."""
    text = adr("0029").read_text(encoding="utf-8")
    parts = re.split(r"^(#+\s+.*)$", text, flags=re.MULTILINE)
    sections = {parts[i].lstrip("#").strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}
    found = [body for heading, body in sections.items() if heading.startswith("Addendum 2026-11-02")]
    assert len(found) == 1, f"ADR-0029 has {len(found)} sections 'Addendum 2026-11-02'"
    assert "ADR-0034" in found[0] or "0034-" in found[0], "ADR-0029's addendum does not point to ADR-0034"


def test_docs_record_story39_assumptions():
    """AC15: docs/assumptions.md has one row each for A29, A30 and A31, on their subjects."""
    rows = [
        line for line in (DOCS / "assumptions.md").read_text(encoding="utf-8").splitlines()
        if re.match(r"^\| A\d+ \|", line)
    ]
    ids = [row.split("|")[1].strip() for row in rows]
    assert len(ids) == len(set(ids)), f"assumption ids repeat: {sorted(i for i in ids if ids.count(i) > 1)}"
    for name, words in ASSUMED.items():
        found = [row for row in rows if row.startswith(f"| {name} |")]
        assert found, f"docs/assumptions.md has no row | {name} |"
        assert all(word in found[0].lower() for word in words), f"{name} is not about {words}: {found[0]}"
