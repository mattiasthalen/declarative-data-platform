"""The film draws the hero's stage layouts and keeps none of its own (story #39: AC13).

``film.stages.as_data()`` is the layouts in the form the composition reads; its ``raw``, ``grid``,
``anchor`` and ``star`` are ``artwork.RAW``, ``GRID``, ``ANCHOR`` and ``STAR`` (the same objects,
or equal points). No module under ``src/film/`` holds a literal list or tuple of coordinates: two
or more points, each two or more numbers. The composition's script, ``src/film/explainer/film.js``,
holds no copy of a hero layout: no two points of one of artwork's layouts written out as numbers.

- ``-k film_uses_artwork_layouts``: AC13 (and review round 1, F20 and F21).
"""

from __future__ import annotations

import ast
import re

import artwork
from harness import REPO

from film import stages

FILM = REPO / "src" / "film"
SCRIPT = FILM / "explainer" / "film.js"
LAYOUTS = {"raw": "RAW", "grid": "GRID", "anchor": "ANCHOR", "star": "STAR"}


def is_number(node: ast.AST) -> bool:
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        node = node.operand
    return isinstance(node, ast.Constant) and type(node.value) in (int, float)


def is_point(node: ast.AST) -> bool:
    return isinstance(node, (ast.Tuple, ast.List)) and len(node.elts) >= 2 and all(map(is_number, node.elts))


def coordinate_lists(path) -> list[int]:
    """Line numbers of each literal list or tuple of points in ``path``."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)) and len(node.elts) >= 2 and all(map(is_point, node.elts))
    ]


NUMBER = r"-?\d+(?:\.\d+)?"
FLAT = re.compile(rf"\[\s*({NUMBER}(?:\s*,\s*{NUMBER})+)\s*,?\s*\]")
OBJECT = re.compile(rf"\{{\s*x\s*:\s*({NUMBER})\s*,\s*y\s*:\s*({NUMBER})\s*\}}")


def written_points(script: str) -> list[tuple[int, tuple[float, float]]]:
    """(line, point) for every pair of numbers ``script`` writes out as a point: ``[x, y]``,
    ``{x: .., y: ..}``, or each pair of a flat list of numbers ``[x0, y0, x1, y1, ...]``."""
    found = []
    for match in FLAT.finditer(script):
        numbers = [float(n) for n in re.split(r"\s*,\s*", match.group(1))]
        line = script.count("\n", 0, match.start()) + 1
        found += [(line, (numbers[k], numbers[k + 1])) for k in range(0, len(numbers) - 1, 2)]
    for match in OBJECT.finditer(script):
        found.append((script.count("\n", 0, match.start()) + 1, (float(match.group(1)), float(match.group(2)))))
    return found


def hero_copies(script: str) -> list[str]:
    """Each artwork layout two or more of whose points ``script`` writes out, with the lines."""
    points = written_points(script)
    copies = []
    for name in LAYOUTS.values():
        hero = {(float(x), float(y)) for x, y in getattr(artwork, name)}
        lines = sorted({line for line, point in points if point in hero})
        hits = {point for _, point in points if point in hero}
        if len(hits) >= 2:
            copies.append(f"artwork.{name} at line(s) {lines}")
    return copies


def as_points(layout) -> list[tuple[float, ...]]:
    return [tuple(float(v) for v in point) for point in layout]


def test_film_uses_artwork_layouts():
    """AC13: film.stages.as_data()'s raw, grid, anchor and star are artwork's own layouts; no
    Python file under src/film/ writes out a coordinate list of its own, and film.js writes out no
    hero layout's points."""
    shown = stages.as_data()
    for key, name in LAYOUTS.items():
        assert key in shown, f"film.stages.as_data() has no {key!r}: {sorted(shown)}"
        hero = getattr(artwork, name)
        assert shown[key] is hero or as_points(shown[key]) == as_points(hero), (
            f"film.stages.as_data()[{key!r}] is not artwork.{name}: {shown[key]}"
        )

    sources = sorted(FILM.rglob("*.py"))
    assert sources, "src/film/ holds no Python files"
    found = [f"{path.relative_to(REPO)}:{line}" for path in sources for line in coordinate_lists(path)]
    assert not found, "src/film/ defines coordinate lists of its own:\n" + "\n".join(found)

    # The scan finds a hero layout copied into a script, nested, flat or as objects.
    raw, star = as_points(artwork.RAW), as_points(artwork.STAR)
    planted = (
        "const RAW = [" + ", ".join(f"[{x:g}, {y:g}]" for x, y in raw) + "];\n"
        + "const STAR = [" + ", ".join(f"{x:g},{y:g}" for x, y in star) + "];\n"
        + "const G = [" + ", ".join(f"{{ x: {x:g}, y: {y:g} }}" for x, y in as_points(artwork.GRID)) + "];\n"
    )
    assert len(hero_copies(planted)) == 3, f"the scan misses a planted copy: {hero_copies(planted)}"

    copies = hero_copies(SCRIPT.read_text(encoding="utf-8"))
    assert not copies, f"{SCRIPT.relative_to(REPO)} writes out the hero's layouts:\n" + "\n".join(copies)
