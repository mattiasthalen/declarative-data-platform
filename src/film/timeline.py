"""When each chapter and beat of the explainer plays, and when each caption shows."""

from __future__ import annotations

import json
from pathlib import Path

NARRATION = Path(__file__).parent / "explainer" / "narration.json"

# Seconds per beat: a 10 s hook, about 20 s per layer, 10 s of orchestration, an 8 s lockup.
CHAPTERS = [
    ("hook", [("hook", 10)]),
    ("ingest", [("close_up", 14), ("zoom_out", 6)]),
    ("conform", [("close_up", 14), ("zoom_out", 6)]),
    ("integrate", [("close_up", 14), ("zoom_out", 6)]),
    ("serve", [("close_up", 14), ("zoom_out", 6)]),
    ("orchestration", [("beat", 10)]),
    ("lockup", [("lockup", 8)]),
]


def beats() -> list[dict]:
    out, t = [], 0.0
    for chapter, parts in CHAPTERS:
        for beat, seconds in parts:
            out.append({"chapter": chapter, "beat": beat, "start": t, "end": t + seconds})
            t += seconds
    return out


def duration() -> float:
    return beats()[-1]["end"]


def narration() -> dict:
    return json.loads(NARRATION.read_text(encoding="utf-8"))


def captions() -> list[dict]:
    """Each narration line from its cue until the next line's cue; the last until the lockup."""
    lines = narration()["lines"]
    lockup = next(b["start"] for b in beats() if b["chapter"] == "lockup")
    ends = [line["cue"] for line in lines[1:]] + [lockup]
    return [{"text": line["text"], "start": line["cue"], "end": end} for line, end in zip(lines, ends)]
