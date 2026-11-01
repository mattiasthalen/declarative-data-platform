"""Each layer's logical model as a Mermaid ``erDiagram``, for its owned region of the root README.

The diagrams set no colour, class or theme: GitHub's Mermaid may not support them in an
``erDiagram``, and one line it cannot parse breaks the whole diagram.
"""

from __future__ import annotations

import re
from pathlib import Path

README = Path("README.md")


def row(data_type: str, name: str, key: str | None = None, comment: str | None = None) -> str:
    """One attribute row. Mermaid rejects whitespace in a type, so ``decimal(10, 2)`` loses it."""
    parts = [re.sub(r"\s+", "", data_type), name]
    if key:
        parts.append(key)
    if comment:
        parts.append(f'"{comment}"')
    return " ".join(parts)


def diagram(entities: list[tuple[str, list[str]]], relationships: list[str] = ()) -> str:
    """The region's text: one fenced mermaid block, entities in the order given, then relationships."""
    lines = ["erDiagram"]
    for name, rows in entities:
        if rows:
            lines += [f"  {name} {{", *(f"    {r}" for r in rows), "  }"]
        else:
            lines.append(f"  {name}")
    lines += [f"  {r}" for r in relationships]
    return "\n```mermaid\n" + "\n".join(lines) + "\n```\n"


def region(layer: str, text: str) -> dict[Path, dict[str, str]]:
    """``text`` as ``layer``'s owned region of the README, in the shape ``ownership.run`` takes."""
    return {README: {f"erd:{layer}": text}}
