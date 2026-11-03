"""The composition draws in Chromium (story #39: AC8).

``film.render.stills(times, out)`` renders the explainer at each time and writes one PNG per time
into ``out``, raising on any page error. It runs in Playwright's Chromium, which CI's test job
installs; no voice is needed.

- ``-k film_stills``: AC8.
"""

from __future__ import annotations

import struct
from pathlib import Path

from film import render, timeline

PNG = b"\x89PNG\r\n\x1a\n"


def size(path: Path) -> tuple[int, int]:
    head = path.read_bytes()[:24]
    assert head[:8] == PNG and head[12:16] == b"IHDR", f"{path.name} is not a PNG"
    return struct.unpack(">II", head[16:24])


def test_film_stills(tmp_path):
    """AC8: a still at the middle of every chapter is drawn without a page error, one 1920x1080 PNG each."""
    spans: dict[str, list[float]] = {}
    for beat in timeline.beats():
        span = spans.setdefault(beat["chapter"], [beat["start"], beat["end"]])
        span[0], span[1] = min(span[0], beat["start"]), max(span[1], beat["end"])
    times = [(start + end) / 2 for start, end in spans.values()]
    assert len(times) == 7, f"expected seven chapters, found {list(spans)}"

    written = render.stills(times, tmp_path)
    assert len(written) == len(times), f"stills wrote {len(written)} files for {len(times)} times"
    assert len({Path(p) for p in written}) == len(times), f"stills wrote the same file twice: {written}"
    for chapter, path in zip(spans, written):
        path = Path(path)
        assert path.is_file(), f"the {chapter} still {path} was not written"
        assert size(path) == (1920, 1080), f"the {chapter} still is {size(path)}, expected 1920x1080"
