"""Write the README's artwork into assets/: the hero, which plays once and rests on its still.

The still is drawn as plain shapes with the attributes it rests on; the motion is CSS keyframes
layered on top with ``animation-fill-mode: backwards``, so a reader that runs no animation, or
asks for reduced motion, sees the still. Nine tiles move through four stages, one page lighting
for each change: raw, a tidy grid (the contracts), Anchor notation (two anchors with their
attributes and a tie), and the star, where the tie becomes the bridge.
"""

from __future__ import annotations

import argparse
import base64
import math
from pathlib import Path

import ownership

GENERATOR = "artwork"
HERE = Path(__file__).parent
ASSETS = Path("assets")

TITLE = "Declarative Data Platform: raw data, a handful of declarations, a star schema."
SECONDS = 11
TILE = 22

INK = "#e9e9ed"
SURFACE = "#232532"
ACCENT = "#9184d9"
CLAIMED = "#3d3a64"
FRAME = f'fill="{SURFACE}" stroke="{INK}" stroke-opacity="0.35" stroke-width="1.2"'
LIT = f'fill="{CLAIMED}" stroke="{ACCENT}" stroke-opacity="1" stroke-width="1.4"'

RAW = [(330, 86), (360, 82), (388, 90), (334, 114), (363, 117), (392, 118), (326, 144), (358, 148), (390, 146)]
GRID = [(576 + 28 * (i % 3), 86 + 28 * (i // 3)) for i in range(9)]

# Stage three, centres: the two anchors, the tie between them, three attributes each.
LEFT, RIGHT, TIE = (568, 125), (662, 125), (615, 125)
ATTRIBUTES = {0: (548, 82), 2: (588, 82), 6: (568, 170), 3: (642, 82), 5: (682, 82), 8: (662, 170)}
ANCHORS = {4: LEFT, 7: RIGHT}
CENTRES = {**ATTRIBUTES, **ANCHORS, 1: TIE}
ANCHOR = [(CENTRES[i][0] - 11, CENTRES[i][1] - 11) for i in range(9)]

# Where each tile rests in the still: tile 1 (the tie) is the bridge at the centre, the rest
# the ring, as #37 drew it.
STAR = [(568.6, 78.6), (604, 114), (639.4, 78.6), (554, 114), (604, 64), (654, 114), (568.6, 149.4), (604, 164), (639.4, 149.4)]
BRIDGE = 1

SPOKES = [
    ((626, 125), (654, 125)), ((604, 125), (576, 125)), ((615, 136), (615, 164)), ((615, 114), (615, 86)),
    ((624.83, 134.83), (640.57, 150.57)), ((605.17, 134.83), (589.43, 150.57)),
    ((605.17, 115.17), (589.43, 99.43)), ((624.83, 115.17), (640.57, 99.43)),
]

# Percent of the run at which each stage is reached and left: tiles travel between them.
APPEAR, RAW_HELD, GRID_IN, GRID_OUT, ANCHOR_IN, ANCHOR_OUT, STAR_IN = 5, 7, 17, 26, 35, 44, 53


def num(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def keyframes(name: str, stops: list[tuple[float, str]]) -> str:
    return f"@keyframes {name} {{ " + " ".join(f"{num(at)}% {{ {style} }}" for at, style in stops) + " }"


def fades(points: list[tuple[float, float]], prop: str = "opacity") -> list[tuple[float, str]]:
    return [(at, f"{prop}: {num(value)}") for at, value in points]


def tile_stops(i: int) -> list[tuple[float, str]]:
    """Tile ``i``'s path as offsets from where it rests in the still."""
    sx, sy = STAR[i]

    def at(position: tuple[float, float], opacity: int = 1) -> str:
        return f"transform: translate({num(position[0] - sx)}px, {num(position[1] - sy)}px); opacity: {opacity}"

    return [
        (0, at(RAW[i], 0)), (APPEAR, at(RAW[i], 0)), (RAW_HELD, at(RAW[i])),
        (GRID_IN, at(GRID[i])), (GRID_OUT, at(GRID[i])),
        (ANCHOR_IN, at(ANCHOR[i])), (ANCHOR_OUT, at(ANCHOR[i])),
        (STAR_IN, at(STAR[i])), (100, at(STAR[i])),
    ]


def segment(a, b, from_edge: float, to_edge: float) -> str:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    ux, uy = dx / length, dy / length
    return (
        f'<line x1="{num(a[0] + ux * from_edge)}" y1="{num(a[1] + uy * from_edge)}" '
        f'x2="{num(b[0] - ux * to_edge)}" y2="{num(b[1] - uy * to_edge)}"/>'
    )


def square_edge(dx: float, dy: float) -> float:
    """How far a tile's edge is from its centre, in direction (dx, dy)."""
    return (TILE / 2) * math.hypot(dx, dy) / max(abs(dx), abs(dy))


def anchor_lines() -> str:
    lines = []
    for i, centre in ATTRIBUTES.items():
        anchor = LEFT if i in (0, 2, 6) else RIGHT
        lines.append(segment(anchor, centre, square_edge(centre[0] - anchor[0], centre[1] - anchor[1]), 9))
    lines += [segment(LEFT, TIE, 11, 11), segment(TIE, RIGHT, 11, 11)]
    return "".join(lines)


def tile(i: int) -> str:
    x, y = STAR[i]
    cx, cy = x + 11, y + 11
    square = f'<rect x="{num(x)}" y="{num(y)}" width="22" height="22" rx="4"/>'
    if i == BRIDGE:
        diamond = f'{num(cx)},{num(cy - 12)} {num(cx + 12)},{num(cy)} {num(cx)},{num(cy + 12)} {num(cx - 12)},{num(cy)}'
        return (
            f'<g class="t{i}">'
            f'<g class="square-out" opacity="0">{square}</g>'
            f'<polygon class="shape" opacity="0" points="{diamond}" stroke-linejoin="round"/>'
            f'<g class="bridge"><rect x="{num(x)}" y="{num(y)}" width="22" height="22" rx="4" {LIT}/>'
            f'<circle cx="{num(cx)}" cy="{num(cy)}" r="3.5" fill="{ACCENT}" stroke="none"/></g>'
            "</g>"
        )
    if i in ANCHORS:
        return (
            f'<g class="t{i}">{square}'
            f'<g class="anchor" opacity="0"><rect x="{num(x)}" y="{num(y)}" width="22" height="22" rx="4" {LIT}/>'
            f'<circle cx="{num(cx)}" cy="{num(cy)}" r="3.5" fill="{ACCENT}" stroke="none"/></g>'
            "</g>"
        )
    return (
        f'<g class="t{i}"><g class="square">{square}</g>'
        f'<g class="shape" opacity="0"><circle cx="{num(cx)}" cy="{num(cy)}" r="9"/>'
        f'<circle cx="{num(cx)}" cy="{num(cy)}" r="6" fill="none"/></g>'
        "</g>"
    )


def pages_style() -> list[str]:
    """Each page lights while the tiles take the shape it declares."""
    rules = []
    for name, rest, start, end in (("page-back", 0.2, 6, 20), ("page-middle", 0.28, 24, 38), ("page-front", 0.35, 42, 56)):
        rules.append(f".{name} {{ animation: {name} {SECONDS}s linear backwards; }}")
        rules.append(keyframes(name, fades([(0, rest), (start, rest), (start + 3, 0.7), (end, 0.7), (end + 4, rest), (100, rest)], "stroke-opacity")))
    return rules


def style() -> list[str]:
    animated = [f".t{i}" for i in range(9)]
    rules = []
    for i in range(9):
        rules.append(f".t{i} {{ animation: t{i} {SECONDS}s ease-in-out backwards; }}")
        rules.append(keyframes(f"t{i}", tile_stops(i)))
    timed = {
        "square": [(0, 1), (28, 1), (33, 0), (46, 0), (51, 1), (100, 1)],
        "square-out": [(0, 1), (28, 1), (33, 0), (100, 0)],
        "shape": [(0, 0), (28, 0), (33, 1), (46, 1), (51, 0), (100, 0)],
        "anchor": [(0, 0), (30, 0), (35, 1), (45, 1), (51, 0), (100, 0)],
        "anchor-lines": [(0, 0), (34, 0), (37, 1), (44, 1), (47, 0), (100, 0)],
        "bridge": [(0, 0), (46, 0), (53, 1), (100, 1)],
        "spokes": [(0, 0), (52, 0), (56, 1), (100, 1)],
        "glow": [(0, 0), (50, 0), (56, 1), (100, 1)],
    }
    for name, points in timed.items():
        rules.append(f".{name} {{ animation: {name} {SECONDS}s linear backwards; }}")
        rules.append(keyframes(name, fades(points)))
        animated.append(f".{name}")
    rules += pages_style()
    animated += [".page-back", ".page-middle", ".page-front"]
    rules.append("@media (prefers-reduced-motion: reduce) { " + ", ".join(animated) + " { animation: none; } }")
    return rules


def font(path: str) -> str:
    return base64.b64encode((HERE / "fonts" / path).read_bytes()).decode("ascii")


def hero() -> str:
    ring = "".join(tile(i) for i in range(9) if i != BRIDGE)
    spokes = "".join(f'<line x1="{num(a[0])}" y1="{num(a[1])}" x2="{num(b[0])}" y2="{num(b[1])}"/>' for a, b in SPOKES)
    raw = "".join(f'<rect x="{x}" y="{y}" width="22" height="22" rx="4"/>' for x, y in RAW)
    motion = "\n".join(f"    {rule}" for rule in style())
    licence = (HERE / "OFL.txt").read_text(encoding="utf-8")
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 760 240" role="img">
  <title>{TITLE}</title>
  <style>
    @font-face {{ font-family: "Spectral"; font-weight: 600; src: url(data:font/woff2;base64,{font("spectral-600.woff2")}) format("woff2"); }}
    @font-face {{ font-family: "Inter"; font-weight: 400; src: url(data:font/woff2;base64,{font("inter-400.woff2")}) format("woff2"); }}
    .wordmark {{ font-family: "Spectral", Georgia, serif; font-weight: 600; font-size: 22px; letter-spacing: 2.2px; fill: {INK}; }}
    .layers {{ font-family: "Inter", Arial, sans-serif; font-weight: 400; font-size: 12px; letter-spacing: 0.3px; fill: {INK}; fill-opacity: 0.55; }}
{motion}
  </style>
  <defs>
    <linearGradient id="night" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#1c1f30"/><stop offset="1" stop-color="#0e0f18"/></linearGradient>
    <radialGradient id="glow" cx="0.81" cy="0.52" r="0.35"><stop offset="0" stop-color="{ACCENT}" stop-opacity="0.18"/><stop offset="1" stop-color="{ACCENT}" stop-opacity="0"/></radialGradient>
    <g id="page"><path d="M444 92 h30 l14 14 v50 h-44 z" stroke-linejoin="round"/><path d="M474 92 v14 h14" fill="none" stroke-linejoin="round"/></g>
  </defs>
  <rect width="760" height="240" rx="14" fill="url(#night)"/>
  <rect class="glow" width="760" height="240" rx="14" fill="url(#glow)"/>
  <text class="wordmark" x="40" y="106">DECLARATIVE</text>
  <text class="wordmark" x="40" y="136">DATA PLATFORM</text>
  <text class="layers" x="40" y="162">ingest · conform · integrate · serve</text>
  <g {FRAME}>
    {raw}
  </g>
  <g transform="translate(21 0)" fill="{SURFACE}" stroke="{INK}" stroke-width="1.2">
    <use class="page-back" href="#page" transform="translate(7 -7)" stroke-opacity="0.2"/>
    <use class="page-middle" href="#page" stroke-opacity="0.28"/>
    <g transform="translate(-7 7)">
      <use class="page-front" href="#page" stroke-opacity="0.35"/>
      <g stroke-width="2.6" stroke-linecap="round">
        <g stroke-opacity="0.55"><line x1="452" y1="112" x2="462" y2="112"/><line x1="458" y1="122" x2="465" y2="122"/><line x1="458" y1="132" x2="464" y2="132"/><line x1="452" y1="142" x2="461" y2="142"/></g>
        <g stroke-opacity="0.28"><line x1="467" y1="112" x2="472" y2="112"/><line x1="470" y1="122" x2="481" y2="122"/><line x1="469" y1="132" x2="478" y2="132"/><line x1="466" y1="142" x2="474" y2="142"/></g>
      </g>
    </g>
  </g>
  <g class="anchor-lines" opacity="0" stroke="{INK}" stroke-opacity="0.35" stroke-width="1.2">
    {anchor_lines()}
  </g>
  <g class="spokes" stroke="{INK}" stroke-opacity="0.35" stroke-width="1.2">
    {spokes}
  </g>
  <g {FRAME}>
    {ring}
  </g>
  <g {FRAME}>
    {tile(BRIDGE)}
  </g>
  <g fill="{INK}">
    <circle cx="426" cy="125" r="2" fill-opacity="0.18"/>
    <circle cx="436" cy="125" r="2" fill-opacity="0.32"/>
    <circle cx="446" cy="125" r="2" fill-opacity="0.46"/>
    <circle cx="525" cy="125" r="2" fill-opacity="0.5"/>
    <circle cx="535" cy="125" r="2" fill-opacity="0.65"/>
    <circle cx="545" cy="125" r="2" fill-opacity="0.8"/>
  </g>
<metadata><![CDATA[
{licence}]]></metadata>
</svg>
"""


def generate(*, check: bool = False) -> int:
    return ownership.run(GENERATOR, "src/artwork/", {ASSETS: {"hero.svg": hero()}}, check=check)


def main() -> int:
    parser = argparse.ArgumentParser(prog=GENERATOR, description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["generate"])
    parser.add_argument("--check", action="store_true", help="write nothing; report drift and exit 1 if any")
    return generate(check=parser.parse_args().check)
