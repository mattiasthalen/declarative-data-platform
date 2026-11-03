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
"""

from __future__ import annotations

import contextlib
import itertools
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
