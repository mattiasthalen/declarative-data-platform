"""The film's data, read from the declarations each time it renders.

Each layer chapter shows Products up close, read from its own declarations, then zooms out to
the whole model as tiles. The narration never names what these show (ADR-0035), so a declaration
can change without making the voice false.
"""

from __future__ import annotations

import math
from pathlib import Path

import yaml

CARD_LINES = 28
CARD_COLUMNS = 120
ELISION = "…"

SOURCE = "sources/adventure_works/products.yaml"
CONTRACT = "contracts/adventure_works/products.yaml"
MODEL = "anchor/model.yaml"
MAPPING = "anchor/mappings/PR_Product.yaml"
SCHEDULE = "orchestrate/prefect.yaml"
FEATURED_ANCHOR = "PR"


class DeclarationError(Exception):
    """A declaration the film shows is missing, or will not fit its card."""


def build(root: Path) -> dict:
    root = Path(root)
    model = _yaml(root, MODEL)
    anchors = model["schema"]["anchor"]
    return {
        "chapters": [
            {"name": "hook", "declaration": None, "close_up": [], "zoom_out": {"tiles": []}},
            {
                "name": "ingest",
                "declaration": SOURCE,
                "close_up": [close_up(root, SOURCE)],
                "zoom_out": {"tiles": [{"kind": "resource", "name": name} for name in resources(root)]},
            },
            {
                "name": "conform",
                "declaration": CONTRACT,
                "close_up": [close_up(root, CONTRACT)],
                "zoom_out": {"tiles": [{"kind": "contract", "name": name} for name in contracts(root)]},
            },
            {
                "name": "integrate",
                "declaration": MODEL,
                "close_up": [close_up(root, MODEL, start=_anchor_line(root, FEATURED_ANCHOR)), close_up(root, MAPPING)],
                "zoom_out": {"tiles": [_anchor_tile(anchor) for anchor in anchors]},
            },
            {
                "name": "serve",
                "declaration": MODEL,
                "close_up": [close_up(root, MODEL, start=_anchor_line(root, FEATURED_ANCHOR))],
                "zoom_out": {
                    "tiles": [{"kind": "dimension", "name": anchor["descriptor"].lower(), "featured": anchor["mnemonic"] == FEATURED_ANCHOR} for anchor in anchors]
                    + [{"kind": "bridge", "name": "_bridge"}]
                },
            },
            {
                "name": "orchestration",
                "declaration": SCHEDULE,
                "close_up": [close_up(root, SCHEDULE, start=_line_starting(root, SCHEDULE, "deployments:"))],
                "zoom_out": {"tiles": [{"kind": "source", "name": p.name} for p in _source_folders(root)] + [{"kind": "build", "name": "build"}]},
            },
            {"name": "lockup", "declaration": None, "close_up": [], "zoom_out": {"tiles": []}},
        ]
    }


def close_up(root: Path, path: str, start: int = 1) -> dict:
    """``path`` from line ``start`` (1-based), cut at the card with an elision when it runs longer."""
    lines = _text(root, path).splitlines()[start - 1 :]
    elided = len(lines) > CARD_LINES
    shown = lines[: CARD_LINES - 1] if elided else lines
    for number, line in enumerate(shown, start):
        if len(line) > CARD_COLUMNS:
            raise DeclarationError(
                f"{path}:{number}: line {number} is {len(line)} characters, wider than the film's card ({CARD_COLUMNS})"
            )
    return {"path": path, "start": start, "lines": shown + [ELISION] if elided else shown, "elided": elided}


def resources(root: Path) -> list[str]:
    """Every declared resource as `<source>__<resource>`; a file starting with `_` declares the source itself."""
    return sorted(
        f"{p.parent.name}__{p.stem}" for p in root.glob("sources/*/*.yaml") if not p.name.startswith("_")
    )


def contracts(root: Path) -> list[str]:
    return sorted(f"{p.parent.name}__{p.stem}" for p in root.glob("contracts/*/*.yaml"))


def tile_grid(n: int, width: float, height: float, largest: float | None = None) -> list[dict]:
    """``n`` square tiles in rows, centred in a ``width`` by ``height`` box, none overlapping;
    the more there are, the smaller they get, never above ``largest``."""
    if n <= 0:
        return []
    columns = max(1, math.ceil(math.sqrt(n * width / height)))
    rows = math.ceil(n / columns)
    cell = min(width / columns, height / rows)
    size = cell * 0.72 if largest is None else min(cell * 0.72, largest)
    gap = cell - size if largest is None else min(cell - size, size * 0.5)
    pitch = size + gap
    used_w = columns * pitch - gap
    used_h = rows * pitch - gap
    x0, y0 = (width - used_w) / 2, (height - used_h) / 2
    placed = []
    for i in range(n):
        row, column = divmod(i, columns)
        in_row = min(columns, n - row * columns)
        offset = (columns - in_row) * pitch / 2
        placed.append({"x": x0 + offset + column * pitch, "y": y0 + row * pitch, "w": size, "h": size})
    return placed


def _anchor_tile(anchor: dict) -> dict:
    return {
        "kind": "anchor",
        "name": f"{anchor['mnemonic']}_{anchor['descriptor']}",
        "attributes": len(anchor.get("attribute") or []),
        "featured": anchor["mnemonic"] == FEATURED_ANCHOR,
    }


def _anchor_line(root: Path, mnemonic: str) -> int:
    for number, line in enumerate(_text(root, MODEL).splitlines(), 1):
        if line.strip() == f"- mnemonic: {mnemonic}":
            return number
    raise DeclarationError(f"{MODEL}: no anchor with mnemonic {mnemonic}")


def _line_starting(root: Path, path: str, prefix: str) -> int:
    for number, line in enumerate(_text(root, path).splitlines(), 1):
        if line.startswith(prefix):
            return number
    raise DeclarationError(f"{path}: no line starts with {prefix!r}")


def _source_folders(root: Path) -> list[Path]:
    return sorted(p for p in (root / "sources").iterdir() if p.is_dir())


def _text(root: Path, path: str) -> str:
    file = root / path
    if not file.is_file():
        raise DeclarationError(f"{path}: the film shows this declaration, and it is missing")
    return file.read_text(encoding="utf-8")


def _yaml(root: Path, path: str) -> dict:
    return yaml.safe_load(_text(root, path))
