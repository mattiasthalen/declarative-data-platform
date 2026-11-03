"""The explainer's timeline and its captions (story #39: AC2, AC7).

``film.timeline.beats()`` gives ``{"chapter", "beat", "start", "end"}`` in seconds, in play order;
the beats are ``hook``, ``close_up``, ``zoom_out``, ``beat`` and ``lockup``.
``film.timeline.captions()`` gives ``{"text", "start", "end"}``, one per line of
``src/film/explainer/narration.json`` (``{"voice", "speed", "lines": [{"text", "cue"}]}``).

- ``-k film_timeline``: AC2. ``-k film_captions``: AC7.
"""

from __future__ import annotations

import itertools
import json

import pytest
from harness import REPO

from film import timeline

ORDER = ("hook", "ingest", "conform", "integrate", "serve", "orchestration", "lockup")
LAYERS = ("ingest", "conform", "integrate", "serve")
# [4]: about 2 minutes, each chapter within ±3 s.
LENGTHS = {"hook": 10, "ingest": 20, "conform": 20, "integrate": 20, "serve": 20, "orchestration": 10, "lockup": 8}
SLACK = 3
NARRATION = REPO / "src" / "film" / "explainer" / "narration.json"
EPSILON = 1e-6


def by_chapter(beats: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for beat in beats:
        out.setdefault(beat["chapter"], []).append(beat)
    return out


def test_film_timeline():
    """AC2: hook, ingest, conform, integrate, serve, orchestration, lockup, in that order, played
    back to back from 0; each layer chapter is a close-up then a zoom-out; each chapter's length
    is [4]'s within ±3 s (hook 10, each layer 20, orchestration 10, lockup 8)."""
    beats = timeline.beats()
    assert beats, "the timeline has no beats"
    order = [chapter for chapter, _ in itertools.groupby(b["chapter"] for b in beats)]
    assert tuple(order) == ORDER, f"the chapters play in the order {order}, expected {list(ORDER)}"

    assert beats[0]["start"] == pytest.approx(0, abs=EPSILON), f"the film starts at {beats[0]['start']}, not 0"
    for before, after in zip(beats, beats[1:]):
        assert after["start"] == pytest.approx(before["end"], abs=1e-3), (
            f"{after['chapter']}/{after['beat']} starts at {after['start']}, not where "
            f"{before['chapter']}/{before['beat']} ends ({before['end']})"
        )
    for beat in beats:
        assert beat["end"] > beat["start"], f"{beat['chapter']}/{beat['beat']} has no length: {beat}"

    chapters = by_chapter(beats)
    assert [b["beat"] for b in chapters["hook"]] == ["hook"], f"the hook's beats are {chapters['hook']}"
    assert [b["beat"] for b in chapters["orchestration"]] == ["beat"], (
        f"orchestration's beats are {chapters['orchestration']}"
    )
    assert [b["beat"] for b in chapters["lockup"]] == ["lockup"], f"the lockup's beats are {chapters['lockup']}"
    for layer in LAYERS:
        names = [b["beat"] for b in chapters[layer]]
        assert names == ["close_up", "zoom_out"], f"the {layer} chapter's beats are {names}, expected close_up, zoom_out"

    for chapter, expected in LENGTHS.items():
        length = chapters[chapter][-1]["end"] - chapters[chapter][0]["start"]
        assert abs(length - expected) <= SLACK, (
            f"the {chapter} chapter lasts {length:.2f} s, expected {expected} s ± {SLACK}"
        )


def test_film_captions():
    """AC7: one caption per narration line, in order, with its text; each shows from its line's cue
    until the next line's cue, and the last until the lockup starts."""
    narration = json.loads(NARRATION.read_text(encoding="utf-8"))
    lines = narration["lines"]
    assert lines, f"{NARRATION.relative_to(REPO)} has no lines"
    cues = [line["cue"] for line in lines]
    assert cues == sorted(cues) and len(set(cues)) == len(cues), f"the narration's cues are not increasing: {cues}"

    captions = timeline.captions()
    assert [c["text"] for c in captions] == [line["text"] for line in lines], (
        "the captions are not the narration's lines, in order"
    )
    (lockup,) = [b for b in timeline.beats() if b["chapter"] == "lockup"]
    ends = cues[1:] + [lockup["start"]]
    for caption, cue, end in zip(captions, cues, ends):
        assert caption["start"] == pytest.approx(cue, abs=1e-3), (
            f"the caption {caption['text']!r} starts at {caption['start']}, not its cue {cue}"
        )
        assert caption["end"] == pytest.approx(end, abs=1e-3), (
            f"the caption {caption['text']!r} ends at {caption['end']}, expected {end}"
        )
        assert caption["end"] > caption["start"], f"the caption {caption['text']!r} is never shown"
