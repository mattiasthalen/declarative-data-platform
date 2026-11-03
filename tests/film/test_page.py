"""What the explainer's page draws, checked in Chromium (story #39: AC4, EC2, [7]).

``film.render.page(root)`` is the composition as one HTML document, with the film's data read
from the declarations under ``root``. Once loaded, the page sets ``window.__ready`` and draws the
frame at ``t`` seconds on ``window.__seek(t)``; ``window.FILM`` is the data it draws from.
``film.timeline.beats()`` gives each beat's span. The zoom-out of a layer chapter is the page's
``.zoom`` box in that chapter's scene (``#<chapter>``), each tile a ``.ztile`` group holding its
shape, its attributes and its label.

The throwaway copies hold only the folders ``film.data.build`` reads.

- ``-k film_zoom_out_counts``: [7], every count on screen is true (review round 1, F4).
- ``-k film_zoom_out_scales``: EC2, drawn at 100 resources, contracts and anchors (F5).
- ``-k film_page_keeps_declaration_text``: a declaration holding the page's placeholders (F15).
- ``-k film_lines_meet_shapes_at_their_edges``: J39-1 point 4, the shapes match the hero's, whose
  lines run edge to edge (evidence defect: lines drawn from shape centres).
- ``-k film_shapes_build_in_modelling_order``: J39-1 point 4, an anchor model is built anchors,
  then attributes, then the tie, and a star entities, then the bridge, then the spokes (evidence
  defect: built in the wrong order).
"""

from __future__ import annotations

import contextlib
import itertools
import math
import re
import shutil
from pathlib import Path

import pytest
import yaml
from harness import REPO

from film import render, timeline

LAYERS = ("ingest", "conform", "integrate", "serve")
SOURCE = "sources/adventure_works/products.yaml"
MODEL = "anchor/model.yaml"
DECLARED = ("sources", "contracts", "anchor", "orchestrate")
# A drawn edge may touch another, or the box, by this much (sub-pixel rounding).
TOUCH = 0.5
MANY = 100


def copy_declarations(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    for folder in DECLARED:
        shutil.copytree(REPO / folder, root / folder)
    return root


def zoom_time(chapter: str) -> float:
    """A moment in the chapter's zoom-out after every tile has grown in and before it fades."""
    (beat,) = [b for b in timeline.beats() if b["chapter"] == chapter and b["beat"] == "zoom_out"]
    return beat["end"] - 0.6


@contextlib.contextmanager
def opened(html: str):
    """The page in Chromium at 1920x1080, ready; yields (page, the page errors seen)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1920, "height": 1080}, device_scale_factor=1)
            errors: list[str] = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.set_content(html, wait_until="load")
            try:
                page.wait_for_function("window.__ready === true", timeout=30000)
            except Exception as error:  # noqa: BLE001 - reported with the page's own errors
                pytest.fail(f"the page never became ready: {errors or error}")
            assert not errors, f"the page raised: {errors}"
            yield page, errors
        finally:
            browser.close()


def declared_counts(root: Path) -> dict[str, int]:
    """chapter -> how many things the declarations hold that its zoom-out label counts."""
    model = yaml.safe_load((root / MODEL).read_text(encoding="utf-8"))
    anchors = len(model["schema"]["anchor"])
    return {
        "ingest": sum(1 for p in root.glob("sources/*/*.yaml") if not p.name.startswith("_")),
        "conform": sum(1 for _ in root.glob("contracts/*/*.yaml")),
        "integrate": anchors,
        # Serve draws one dimension per anchor, and the bridge, which is no dimension.
        "serve": anchors,
    }


# The word each zoom-out's label counts in, singular or plural.
COUNTED = {"ingest": "resources?", "conform": "contracts?", "integrate": "anchors?", "serve": "dimensions?"}


def test_film_zoom_out_counts_are_true():
    """[7], review F4: each zoom-out's label states the count the declarations hold. Serve's says
    "N dimensions and the bridge", N being the anchors in anchor/model.yaml: the bridge's tile is
    not a dimension."""
    expected = declared_counts(REPO)
    with opened(render.page(REPO)) as (page, errors):
        for chapter in LAYERS:
            page.evaluate("t => window.__seek(t)", zoom_time(chapter))
            assert not errors, f"the page raised at the {chapter} zoom-out: {errors}"
            text = page.inner_text("body")
            stated = [int(n) for n in re.findall(rf"(\d+)\s+{COUNTED[chapter]}\b", text, re.IGNORECASE)]
            assert stated, f"the {chapter} zoom-out shows no count of {COUNTED[chapter]}; the frame reads:\n{text}"
            assert set(stated) == {expected[chapter]}, (
                f"the {chapter} zoom-out says {stated} {COUNTED[chapter]}, the declarations hold "
                f"{expected[chapter]}; the frame reads:\n{text}"
            )


# --------------------------------------------------------------------------- EC2


def many(root: Path, n: int) -> None:
    """Make the copy hold ``n`` resources, ``n`` contracts and ``n`` anchors, with names and
    attribute counts like AdventureWorks's."""
    have = sum(1 for p in root.glob("sources/*/*.yaml") if not p.name.startswith("_"))
    for i in range(n - have):
        (root / "sources" / "adventure_works" / f"sales_table_{i:03d}.yaml").write_text(
            f"# Added by the film test.\nendpoint:\n  path: SalesTable{i:03d}\n", encoding="utf-8"
        )
    have = sum(1 for _ in root.glob("contracts/*/*.yaml"))
    for i in range(n - have):
        (root / "contracts" / "adventure_works" / f"sales_table_{i:03d}.yaml").write_text(
            "# Added by the film test.\n", encoding="utf-8"
        )
    path = root / MODEL
    model = yaml.safe_load(path.read_text(encoding="utf-8"))
    anchors = model["schema"]["anchor"]
    for i in range(n - len(anchors)):
        anchors.append(
            {
                "mnemonic": f"Z{i:02d}",
                "descriptor": f"SalesThing{i:02d}",
                "identity": "int",
                "attribute": [
                    {"mnemonic": f"A{k}", "descriptor": f"Value{k}", "dataRange": "varchar(20)", "timeRange": "timestamp"}
                    for k in range(1 + i % 5)
                ],
            }
        )
    path.write_text(yaml.safe_dump(model, sort_keys=False, width=100), encoding="utf-8")


def drawn(page, chapter: str) -> dict:
    """The zoom-out's box, its label and each tile group's extent, in page pixels."""
    return page.evaluate(
        """chapter => {
            const box = document.querySelector(`#${chapter} .zoom`);
            if (!box) return null;
            const r = (e) => { const b = e.getBoundingClientRect(); return [b.left, b.top, b.right, b.bottom]; };
            const label = box.querySelector('.label');
            return {
                box: r(box),
                label: label ? r(label) : null,
                tiles: [...box.querySelectorAll('.ztile')].map(r),
            };
        }""",
        chapter,
    )


def overlaps(a, b) -> bool:
    return a[0] < b[2] - TOUCH and b[0] < a[2] - TOUCH and a[1] < b[3] - TOUCH and b[1] < a[3] - TOUCH


def test_film_zoom_out_scales(tmp_path):
    """EC2, review F5: with 100 resources, 100 contracts and 100 anchors, every zoom-out draws one
    tile group per thing (shape, attributes and label), none overlapping another or the zoom-out's
    label, all inside the zoom-out's box; the tiles are smaller than at today's counts."""
    root = copy_declarations(tmp_path)
    few: dict[str, float] = {}
    with opened(render.page(root)) as (page, errors):
        for chapter in LAYERS:
            page.evaluate("t => window.__seek(t)", zoom_time(chapter))
            found = drawn(page, chapter)
            assert found and found["tiles"], f"the {chapter} zoom-out draws no tiles: {found}"
            few[chapter] = min((t[2] - t[0]) * (t[3] - t[1]) for t in found["tiles"])

    many(root, MANY)
    with opened(render.page(root)) as (page, errors):
        for chapter in LAYERS:
            page.evaluate("t => window.__seek(t)", zoom_time(chapter))
            assert not errors, f"the page raised at the {chapter} zoom-out: {errors}"
            found = drawn(page, chapter)
            assert found, f"the {chapter} scene has no zoom-out box"
            tiles = found["tiles"]
            assert len(tiles) >= MANY, f"the {chapter} zoom-out draws {len(tiles)} tiles for {MANY} declared"
            box = found["box"]
            outside = [t for t in tiles if t[0] < box[0] - TOUCH or t[1] < box[1] - TOUCH or t[2] > box[2] + TOUCH or t[3] > box[3] + TOUCH]
            assert not outside, (
                f"{len(outside)} of the {chapter} zoom-out's {len(tiles)} tiles leave its box {box}, "
                f"e.g. {outside[:3]}"
            )
            if found["label"]:
                over_label = [t for t in tiles if overlaps(t, found["label"])]
                assert not over_label, (
                    f"{len(over_label)} of the {chapter} zoom-out's tiles cover its label {found['label']}, e.g. {over_label[:3]}"
                )
            clashes = [(a, b) for a, b in itertools.combinations(tiles, 2) if overlaps(a, b)]
            assert not clashes, (
                f"the {chapter} zoom-out's tiles overlap at {MANY}: {len(clashes)} pairs, e.g. {clashes[:3]}"
            )
            smallest = min((t[2] - t[0]) * (t[3] - t[1]) for t in tiles)
            assert smallest < few[chapter], f"the {chapter} zoom-out's tiles did not shrink at {MANY}"


# --------------------------------------------------------------------------- F15


PLACEHOLDERS = "# A note that mentions /*SCRIPT*/, /*STYLE*/, /*FONTS*/ and /*FILM*/ verbatim."


def test_film_page_keeps_declaration_text(tmp_path):
    """Review F15: a declaration line holding the page's placeholders (/*SCRIPT*/, /*STYLE*/,
    /*FONTS*/) reaches the page's data verbatim, pulls nothing into it, and the page still draws."""
    root = copy_declarations(tmp_path)
    path = root / SOURCE
    lines = path.read_text(encoding="utf-8").splitlines()
    lines.insert(1, PLACEHOLDERS)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    html = render.page(root)
    with opened(html) as (page, errors):
        film = page.evaluate("() => window.FILM")
        (ingest,) = [c for c in film["chapters"] if c["name"] == "ingest"]
        shown = ingest["close_up"]
        shown = [shown] if isinstance(shown, dict) else shown
        (card,) = [s for s in shown if Path(s["path"]).as_posix() == SOURCE]
        assert PLACEHOLDERS in card["lines"], (
            f"the ingest close-up does not hold the line {PLACEHOLDERS!r} verbatim: {card['lines'][:4]}"
        )
        (close,) = [b for b in timeline.beats() if b["chapter"] == "ingest" and b["beat"] == "close_up"]
        page.evaluate("t => window.__seek(t)", (close["start"] + close["end"]) / 2)
        assert not errors, f"the page raised: {errors}"
    script = (render.EXPLAINER / "film.js").read_text(encoding="utf-8")
    assert html.count(script) == 1, f"film.js appears {html.count(script)} times in the page, expected once"


# --------------------------------------------------------------------------- J39-1 point 4

# A line's end may sit this far inside a shape, in page pixels: its stroke and floating point.
EDGE = 1.5

# Every side-shape and zoom-out SVG of the scene: its lines' ends and its shapes, in page pixels.
# A rect becomes its four corners (rounded corners taken as sharp), a polygon its points, a
# circle its centre and radius, each through the element's own transform.
GEOMETRY = """scene => [...document.querySelectorAll(`#${scene} .side svg, #${scene} .zoom svg`)].map(svg => {
    const at = (el, x, y) => { const p = new DOMPoint(x, y).matrixTransform(el.getScreenCTM()); return [p.x, p.y]; };
    const shapes = [...svg.querySelectorAll('rect, polygon, circle')].map(el => {
        const tag = el.tagName.toLowerCase();
        if (tag === 'circle') {
            const cx = el.cx.baseVal.value, cy = el.cy.baseVal.value, c = at(el, cx, cy);
            const e = at(el, cx + el.r.baseVal.value, cy);
            return {tag, centre: c, radius: Math.hypot(e[0] - c[0], e[1] - c[1])};
        }
        if (tag === 'rect') {
            const x = el.x.baseVal.value, y = el.y.baseVal.value, w = el.width.baseVal.value, h = el.height.baseVal.value;
            return {tag, points: [[x, y], [x + w, y], [x + w, y + h], [x, y + h]].map(p => at(el, ...p))};
        }
        return {tag, points: [...el.points].map(p => at(el, p.x, p.y))};
    });
    const ends = [...svg.querySelectorAll('line')].flatMap(l => [
        at(l, l.x1.baseVal.value, l.y1.baseVal.value), at(l, l.x2.baseVal.value, l.y2.baseVal.value)]);
    return {svg: svg.parentElement.className, shapes, ends};
})"""


def depth(point, shape) -> float:
    """How far inside the shape the point lies; negative outside."""
    if shape["tag"] == "circle":
        return shape["radius"] - math.dist(point, shape["centre"])
    x, y = point
    corners = shape["points"]
    inside, nearest = False, math.inf
    for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / ((dx * dx + dy * dy) or 1e-12)))
        nearest = min(nearest, math.dist(point, (ax + t * dx, ay + t * dy)))
    return nearest if inside else -nearest


def test_film_lines_meet_shapes_at_their_edges():
    """J39-1 point 4, evidence defect: the hero draws every line edge to edge, from one shape's
    boundary to the other's. At the end of each layer chapter's close-up and in its zoom-out, when
    the side shapes and the zoom-out's tiles are fully drawn, no end of a line in a side-shape or
    zoom-out SVG lies inside a rect, polygon or circle of that SVG; the lit, translucent fills
    would show the line running through the shape."""
    moments = []
    for beat in timeline.beats():
        if beat["chapter"] in LAYERS and beat["beat"] == "close_up":
            moments.append((beat["chapter"], "close-up end", beat["end"] - 0.3))
    moments += [(chapter, "zoom-out", zoom_time(chapter)) for chapter in LAYERS]
    with opened(render.page(REPO)) as (page, errors):
        lines_seen = 0
        for chapter, moment, t in moments:
            page.evaluate("t => window.__seek(t)", t)
            assert not errors, f"the page raised at the {chapter} {moment}: {errors}"
            svgs = page.evaluate(GEOMETRY, chapter)
            assert svgs, f"the {chapter} scene draws no side-shape or zoom-out SVG at its {moment}"
            for svg in svgs:
                lines_seen += len(svg["ends"]) // 2
                inside = [
                    (tuple(round(c, 1) for c in end), shape["tag"], round(depth(end, shape), 1))
                    for end in svg["ends"]
                    for shape in svg["shapes"]
                    if depth(end, shape) > EDGE
                ]
                assert not inside, (
                    f"at the {chapter} {moment} (t={t:.1f}s), {len(inside)} line ends in the "
                    f"'{svg['svg']}' SVG lie inside one of its shapes, not on its edge as the hero "
                    f"draws them (end, shape, px inside): {inside[:6]}"
                )
        assert lines_seen, "no side shape or zoom-out draws a line; the test checks nothing"


# --------------------------------------------------------------------------- J39-1 point 4, build order

# A shape counts as shown once its opacity, its ancestors' multiplied in, passes this.
SHOWN = 0.5
# How often the build is sampled, in seconds: once a frame at 30 fps.
FRAME = 1 / 30
# How near a shape's boundary a line's end lies when the line joins that shape, in page pixels.
JOINS = 3.0

# Each rect, polygon, circle and line under the selector: its geometry in page pixels (as
# GEOMETRY), its fill, the index of the zoom-out tile holding it (or -1), and how opaque it is.
SHAPES = """selector => [...document.querySelectorAll(selector)].flatMap(svg =>
    [...svg.querySelectorAll('rect, polygon, circle, line')]).map(el => {
    const at = (x, y) => { const p = new DOMPoint(x, y).matrixTransform(el.getScreenCTM()); return [p.x, p.y]; };
    const tag = el.tagName.toLowerCase();
    let opacity = el.getClientRects().length ? 1 : 0;
    for (let e = el; e && e.nodeType === 1; e = e.parentElement) {
        const style = getComputedStyle(e);
        if (style.display === 'none' || style.visibility === 'hidden') opacity = 0;
        opacity *= parseFloat(style.opacity);
    }
    const tiles = [...document.querySelectorAll('.ztile')];
    const shape = {tag, fill: el.getAttribute('fill'), opacity, tile: tiles.indexOf(el.closest('.ztile'))};
    if (tag === 'circle') {
        const cx = el.cx.baseVal.value, cy = el.cy.baseVal.value, c = at(cx, cy), e = at(cx + el.r.baseVal.value, cy);
        return {...shape, centre: c, radius: Math.hypot(e[0] - c[0], e[1] - c[1])};
    }
    if (tag === 'rect') {
        const x = el.x.baseVal.value, y = el.y.baseVal.value, w = el.width.baseVal.value, h = el.height.baseVal.value;
        return {...shape, points: [[x, y], [x + w, y], [x + w, y + h], [x, y + h]].map(p => at(...p))};
    }
    if (tag === 'line') {
        return {...shape, ends: [at(el.x1.baseVal.value, el.y1.baseVal.value), at(el.x2.baseVal.value, el.y2.baseVal.value)]};
    }
    return {...shape, points: [...el.points].map(p => at(p.x, p.y))};
})"""


def build(page, selector: str, start: float, end: float) -> list[dict]:
    """Each shape under the selector as drawn at ``end``, with ``first``: the first sampled time,
    from ``start`` a frame at a time, at which it is shown (None if never)."""
    shapes, first = None, []
    steps = int((end - start) / FRAME)
    for i in range(steps + 1):
        t = start + i * FRAME
        page.evaluate("t => window.__seek(t)", t)
        seen = page.evaluate(SHAPES, selector)
        if first == []:
            first = [None] * len(seen)
        assert len(seen) == len(first), f"'{selector}' draws {len(seen)} shapes at t={t:.2f}s, {len(first)} before"
        for k, shape in enumerate(seen):
            if first[k] is None and shape["opacity"] > SHOWN:
                first[k] = t
        shapes = seen
    for shape, t in zip(shapes, first):
        shape["first"] = t
    return shapes


def joins(point, shape) -> bool:
    return abs(depth(point, shape)) <= JOINS


def concentric(a: dict, b: dict) -> bool:
    return a is not b and math.dist(a["centre"], b["centre"]) < 0.5 and abs(a["radius"] - b["radius"]) > 0.5


def anchor_model(shapes: list[dict]) -> dict[str, list[dict]]:
    """The anchor model's shapes by role, read from their kind and geometry: a rect is an anchor,
    a circle drawn with a smaller one inside it an attribute (the outer one), the polygon the tie;
    a line with an end on the tie is the tie's, a line with an end on an attribute that attribute's."""
    circles = [s for s in shapes if s["tag"] == "circle"]
    anchors = [s for s in shapes if s["tag"] == "rect"]
    attributes = [c for c in circles if any(concentric(c, o) and o["radius"] < c["radius"] for o in circles)]
    ties = [s for s in shapes if s["tag"] == "polygon"]
    tie_lines, attribute_lines = [], []
    for line in (s for s in shapes if s["tag"] == "line"):
        if any(joins(end, tie) for end in line["ends"] for tie in ties):
            tie_lines.append(line)
        else:
            line["attribute"] = next(
                (a for a in attributes for end in line["ends"] if joins(end, a)), None
            )
            attribute_lines.append(line)
    return {"anchors": anchors, "attributes": attributes, "ties": ties,
            "tie lines": tie_lines, "attribute lines": attribute_lines}


def firsts(shapes: list[dict]) -> list[float]:
    return sorted(s["first"] for s in shapes)


def right_side(chapter: str) -> str:
    return f"#{chapter} .side.right svg"


def beat(chapter: str, name: str) -> dict:
    (found,) = [b for b in timeline.beats() if b["chapter"] == chapter and b["beat"] == name]
    return found


def test_film_shapes_build_in_modelling_order_anchor_model():
    """J39-1 point 4, evidence defect: an anchor model is built anchors first, then described,
    then related. Sampled a frame at a time through the integrate close-up, a shape counting as
    shown once more than half opaque, its right side shape, the anchor model, shows every anchor
    before any attribute, each attribute no later than its line to its anchor, every attribute and
    attribute line before the tie, and the tie before its lines to the anchors."""
    with opened(render.page(REPO)) as (page, errors):
        close = beat("integrate", "close_up")
        shapes = build(page, right_side("integrate"), close["start"], close["end"])
        assert not errors, f"the page raised in the integrate close-up: {errors}"
        never = [(s["tag"], s["fill"]) for s in shapes if s["first"] is None]
        assert not never, f"shapes of the anchor model never show in the integrate close-up: {never}"
        roles = anchor_model(shapes)
        for role in ("anchors", "attributes", "ties", "tie lines", "attribute lines"):
            assert roles[role], f"the integrate close-up's anchor model draws no {role}: {[s['tag'] for s in shapes]}"
        assert not [s for s in roles["attribute lines"] if s["attribute"] is None], (
            "a line of the anchor model joins neither the tie nor an attribute"
        )
        when = {role: firsts(found) for role, found in roles.items() if role != "attribute lines"}
        when["attribute lines"] = firsts(roles["attribute lines"])
        order = f"first shown (s) by role: {when}"
        assert max(when["anchors"]) < min(when["attributes"]), (
            f"an attribute of the anchor model shows before an anchor; the anchors come first. {order}"
        )
        early = [(line["first"], line["attribute"]["first"]) for line in roles["attribute lines"]
                 if line["first"] < line["attribute"]["first"]]
        assert not early, f"attribute lines show before their attributes (line, attribute): {early}. {order}"
        assert max(when["attributes"] + when["attribute lines"]) < min(when["ties"]), (
            f"the tie shows before the anchors are described by their attributes. {order}"
        )
        assert max(when["ties"]) < min(when["tie lines"]), (
            f"a line to the tie shows before the tie. {order}"
        )


def test_film_shapes_build_in_modelling_order_star():
    """J39-1 point 4, evidence defect: a star is built entities first, then the bridge, then the
    spokes joining them. Sampled a frame at a time through the serve close-up, its right side
    shape, the star, shows every entity (rect) before the bridge (polygon), and the bridge before
    any spoke (line)."""
    with opened(render.page(REPO)) as (page, errors):
        close = beat("serve", "close_up")
        shapes = build(page, right_side("serve"), close["start"], close["end"])
        assert not errors, f"the page raised in the serve close-up: {errors}"
        never = [(s["tag"], s["fill"]) for s in shapes if s["first"] is None]
        assert not never, f"shapes of the star never show in the serve close-up: {never}"
        entities = [s for s in shapes if s["tag"] == "rect"]
        bridges = [s for s in shapes if s["tag"] == "polygon"]
        spokes = [s for s in shapes if s["tag"] == "line"]
        assert entities and bridges and spokes, f"the serve close-up's star lacks a role: {[s['tag'] for s in shapes]}"
        order = (f"first shown (s): entities {firsts(entities)}, bridge {firsts(bridges)}, "
                 f"spokes {firsts(spokes)}")
        assert max(firsts(entities)) < min(firsts(bridges)), f"the bridge shows before every entity has. {order}"
        assert max(firsts(bridges)) < min(firsts(spokes)), f"a spoke shows before the bridge. {order}"


def test_film_shapes_build_in_modelling_order_zoom_out():
    """J39-1 point 4, evidence defect: an anchor is drawn before it is described. Sampled a frame
    at a time through the integrate zoom-out, each tile's attribute circles (those centred outside
    its square) show after the square."""
    with opened(render.page(REPO)) as (page, errors):
        zoom = beat("integrate", "zoom_out")
        shapes = build(page, "#integrate .zoom svg", zoom["start"], zoom["end"])
        assert not errors, f"the page raised in the integrate zoom-out: {errors}"
        tiles = sorted({s["tile"] for s in shapes if s["tile"] >= 0})
        assert tiles, "the integrate zoom-out draws no tiles"
        checked = 0
        for tile in tiles:
            mine = [s for s in shapes if s["tile"] == tile]
            (square,) = [s for s in mine if s["tag"] == "rect"]
            circles = [s for s in mine if s["tag"] == "circle" and depth(s["centre"], square) < 0]
            assert square["first"] is not None, f"the integrate zoom-out's anchor {tile} never shows"
            for circle in circles:
                checked += 1
                assert circle["first"] is not None and circle["first"] > square["first"], (
                    f"an attribute circle of the integrate zoom-out's anchor {tile} shows at "
                    f"{circle['first']}s, its square at {square['first']:.2f}s: the attributes come after"
                )
        assert checked, "no anchor in the integrate zoom-out has an attribute circle; the test checks nothing"
