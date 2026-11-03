"""The film draws the hero's stage layouts and keeps none of its own (story #39: AC13).

``film.stages`` re-exports ``RAW``, ``GRID``, ``ANCHOR`` and ``STAR`` from ``artwork``. No
module under ``src/film/`` holds a literal list or tuple of coordinates: two or more points,
each two or more numbers.

- ``-k film_uses_artwork_layouts``: AC13.
"""

from __future__ import annotations

import ast

import artwork
from harness import REPO

from film import stages

FILM = REPO / "src" / "film"
LAYOUTS = ("RAW", "GRID", "ANCHOR", "STAR")


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


def test_film_uses_artwork_layouts():
    """AC13: film.stages.RAW, GRID, ANCHOR and STAR are artwork's own objects, and no Python file
    under src/film/ writes out a coordinate list of its own."""
    for name in LAYOUTS:
        assert getattr(stages, name) is getattr(artwork, name), f"film.stages.{name} is not artwork.{name}"
    sources = sorted(FILM.rglob("*.py"))
    assert sources, "src/film/ holds no Python files"
    found = [f"{path.relative_to(REPO)}:{line}" for path in sources for line in coordinate_lists(path)]
    assert not found, "src/film/ defines coordinate lists of its own:\n" + "\n".join(found)
