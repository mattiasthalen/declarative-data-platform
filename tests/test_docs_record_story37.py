"""Story #37's decision, term, assumption, rubrics and font dependency are recorded (AC12).

The ADR is found by its title and the assumption by its id, A23, reserved for this story.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from harness import REPO

DOCS = REPO / "docs"
ADR = DOCS / "adr"
TITLE = "ship the readme's artwork as svg committed under docs/"


def artwork_adr() -> Path:
    found = [
        path
        for path in sorted(ADR.glob("[0-9][0-9][0-9][0-9]-*.md"))
        if TITLE in path.read_text(encoding="utf-8").splitlines()[0].lower()
    ]
    assert len(found) == 1, f"expected one ADR titled {TITLE!r} in docs/adr/, found {[p.name for p in found]}"
    return found[0]


def test_artwork_adr_is_indexed():
    """AC12: the ADR is in docs/adr/ and a row of its index links it."""
    name = artwork_adr().name
    rows = [line for line in (ADR / "README.md").read_text(encoding="utf-8").splitlines() if f"({name})" in line]
    assert len(rows) == 1, f"docs/adr/README.md has {len(rows)} rows linking {name}"


def test_declaration_is_in_the_lexicon():
    """AC12: docs/lexicon.md defines *declaration*."""
    text = (DOCS / "lexicon.md").read_text(encoding="utf-8")
    assert re.search(r"^\*\*declaration\*\*", text, re.MULTILINE), "docs/lexicon.md has no **declaration** entry"


def test_embedded_fonts_on_github_is_assumed():
    """AC12: docs/assumptions.md holds A23, that GitHub renders the hero in its embedded fonts."""
    rows = [line for line in (DOCS / "assumptions.md").read_text(encoding="utf-8").splitlines() if re.match(r"^\| A\d+ \|", line)]
    ids = [row.split("|")[1].strip() for row in rows]
    assert len(ids) == len(set(ids)), f"assumption ids repeat: {sorted(i for i in ids if ids.count(i) > 1)}"
    found = [row for row in rows if row.startswith("| A23 |")]
    assert found, "docs/assumptions.md has no row | A23 |"
    assert "github" in found[0].lower() and "font" in found[0].lower(), f"A23 is not about GitHub and fonts: {found[0]}"


def test_hero_rubrics_are_judged():
    """AC12: tests/judged.md holds the rubrics "Hero drawing" and "Hero on GitHub"."""
    headings = re.findall(r"^#+\s+(.*)$", (REPO / "tests" / "judged.md").read_text(encoding="utf-8"), re.MULTILINE)
    for rubric in ("Hero drawing", "Hero on GitHub"):
        assert any(h.startswith(rubric) for h in headings), f"tests/judged.md has no section {rubric!r}"


def test_fonttools_is_a_dev_dependency():
    """AC12: fonttools and brotli (for WOFF2) are in the dev group and the lock, and import."""
    dev = tomllib.loads((REPO / "pyproject.toml").read_text(encoding="utf-8"))["dependency-groups"]["dev"]
    names = {re.split(r"[\s\[<>=!~;]", spec, maxsplit=1)[0].lower() for spec in dev}
    lock = (REPO / "uv.lock").read_text(encoding="utf-8")
    for package in ("fonttools", "brotli"):
        assert package in names, f"pyproject.toml's dev group lacks {package}: {dev}"
        assert f'name = "{package}"' in lock, f"uv.lock has no package {package}"
    import brotli  # noqa: F401
    import fontTools.ttLib  # noqa: F401
