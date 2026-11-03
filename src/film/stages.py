"""The hero's stage layouts, which the film draws its shapes from so the two never drift apart."""

from artwork import ANCHOR, ANCHORS, ATTRIBUTES, BRIDGE, GRID, RAW, SPOKES, STAR


def as_data() -> dict:
    """The layouts in the form the composition reads: hero coordinates, top-left corners of 22px tiles."""
    return {
        "raw": RAW,
        "grid": GRID,
        "anchor": ANCHOR,
        "star": STAR,
        "anchors": sorted(ANCHORS),
        "attributes": sorted(ATTRIBUTES),
        "tie": [i for i in range(len(ANCHOR)) if i not in ANCHORS and i not in ATTRIBUTES],
        "bridge": BRIDGE,
        "spokes": SPOKES,
    }
