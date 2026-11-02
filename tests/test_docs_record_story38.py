"""Story #38's decision, assumption and rubrics are recorded (AC11).

The ADR is found by its number, 0032, and its title, and the assumption by its id, A27, both
reserved for this story. No lexicon entry is admitted or changed ([S3]).
"""

from __future__ import annotations

import re
from pathlib import Path

from harness import REPO

DOCS = REPO / "docs"
ADR = DOCS / "adr"
TITLE = "keep the readme's artwork in assets/"
PARTLY = re.compile(r"partly superseded by \[?ADR-0032\b", re.IGNORECASE)
JUDGED = REPO / "tests" / "judged.md"


def assets_adr() -> Path:
    found = sorted(ADR.glob("0032-*.md"))
    assert len(found) == 1, f"expected one ADR 0032 in docs/adr/, found {[p.name for p in found]}"
    title = found[0].read_text(encoding="utf-8").splitlines()[0]
    assert TITLE in title.lower(), f"ADR-0032's title is {title!r}, expected it to read {TITLE!r}"
    return found[0]


def index_rows(name: str) -> list[str]:
    return [line for line in (ADR / "README.md").read_text(encoding="utf-8").splitlines() if f"({name})" in line]


def test_assets_adr_is_indexed():
    """AC11: ADR-0032 "Keep the README's artwork in assets/ at the repo root" is in docs/adr/ and
    a row of its index links it."""
    name = assets_adr().name
    rows = index_rows(name)
    assert len(rows) == 1, f"docs/adr/README.md has {len(rows)} rows linking {name}"


def test_svg_adr_is_partly_superseded():
    """AC11: ADR-0029's status line and its index row say "partly superseded by ADR-0032"."""
    (adr,) = sorted(ADR.glob("0029-*.md"))
    status = [line for line in adr.read_text(encoding="utf-8").splitlines() if re.match(r"\**Status", line)]
    assert status, f"{adr.name} has no Status line"
    assert PARTLY.search(status[0]), f"{adr.name}'s status line does not say partly superseded by ADR-0032: {status[0]}"
    rows = index_rows(adr.name)
    assert len(rows) == 1, f"docs/adr/README.md has {len(rows)} rows linking {adr.name}"
    assert PARTLY.search(rows[0]), f"ADR-0029's index row does not say partly superseded by ADR-0032: {rows[0]}"


def test_motion_on_github_is_assumed():
    """AC11: docs/assumptions.md holds A27, that browsers play the hero's CSS animation on GitHub
    and honour prefers-reduced-motion inside it."""
    rows = [line for line in (DOCS / "assumptions.md").read_text(encoding="utf-8").splitlines() if re.match(r"^\| A\d+ \|", line)]
    ids = [row.split("|")[1].strip() for row in rows]
    assert len(ids) == len(set(ids)), f"assumption ids repeat: {sorted(i for i in ids if ids.count(i) > 1)}"
    found = [row for row in rows if row.startswith("| A27 |")]
    assert found, "docs/assumptions.md has no row | A27 |"
    row = found[0].lower()
    assert "github" in row and "animat" in row and "reduced" in row and "motion" in row, (
        f"A27 is not about GitHub, animation and reduced motion: {found[0]}"
    )


def sections(text: str) -> dict[str, str]:
    """heading -> the text under it, up to the next heading of any level."""
    parts = re.split(r"^(#+\s+.*)$", text, flags=re.MULTILINE)
    return {re.sub(r"^#+\s+", "", parts[i]).strip(): parts[i + 1] for i in range(1, len(parts) - 1, 2)}


def test_hero_rubrics_name_assets():
    """AC11: in tests/judged.md the hero rubrics "Hero drawing" and "Hero on GitHub" stay, the
    drawing's names assets/hero.svg, none names docs/hero.svg, and "Hero in motion" is there,
    naming assets/hero.svg and the mockup fixture."""
    found = sections(JUDGED.read_text(encoding="utf-8"))
    hero = {heading: body for heading, body in found.items() if heading.startswith("Hero ")}
    for rubric in ("Hero drawing", "Hero on GitHub", "Hero in motion"):
        assert any(h.startswith(rubric) for h in hero), f"tests/judged.md has no section {rubric!r}"
    for heading, body in hero.items():
        assert "docs/hero.svg" not in body, f"tests/judged.md's {heading!r} still names docs/hero.svg"
    drawing = next(body for h, body in hero.items() if h.startswith("Hero drawing"))
    assert "assets/hero.svg" in drawing, "tests/judged.md's 'Hero drawing' does not name assets/hero.svg"
    motion = next(body for h, body in hero.items() if h.startswith("Hero in motion"))
    assert "assets/hero.svg" in motion, "tests/judged.md's 'Hero in motion' does not name assets/hero.svg"
    assert "hero-motion-mockup.svg" in motion, "tests/judged.md's 'Hero in motion' does not name its mockup"
    assert (REPO / "tests" / "fixtures" / "hero-motion-mockup.svg").is_file(), "tests/fixtures/hero-motion-mockup.svg is missing"
