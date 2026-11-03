"""The explainer's score is deterministic and ducks under the narration (story #39: AC9), and
plays at 96 BPM with every chapter starting on a bar (story #49: AC3).

``film.score.render(duration, cues)`` returns the score as a 48 kHz stereo 16-bit WAV, ducked
inside each ``(start, end)`` cue. The loudness is compared away from the ducking's ramps and the
score's own fade in and out.

- ``-k film_score``: AC9 (#39), AC4 (#49).
- ``-k film_score_bars``: AC3 (#49). ``film.score.BAR`` is the length of one bar in seconds.
"""

from __future__ import annotations

import io
import math
import wave

from film import score, timeline

DURATION = 40.0
CUES = [(12.0, 20.0)]
# Inside the cue, and on both sides of it, a second clear of each edge.
INSIDE = (13.0, 19.0)
OUTSIDE = ((5.0, 11.0), (21.0, 27.0))
# [4]: 96 BPM in 4/4.
BPM = 96
TOLERANCE = 1e-9


def samples(wav: bytes):
    import numpy as np

    with wave.open(io.BytesIO(wav)) as reader:
        assert reader.getframerate() == 48000, f"the score is {reader.getframerate()} Hz, expected 48000"
        assert reader.getnchannels() == 2, f"the score has {reader.getnchannels()} channels, expected 2"
        assert reader.getsampwidth() == 2, f"the score is {8 * reader.getsampwidth()}-bit, expected 16"
        frames = reader.readframes(reader.getnframes())
    audio = np.frombuffer(frames, dtype="<i2").astype(np.float64).reshape(-1, 2)
    assert abs(len(audio) / 48000 - DURATION) < 0.5, f"the score lasts {len(audio) / 48000:.2f} s, expected {DURATION}"
    return audio


def rms(audio, start: float, end: float) -> float:
    import numpy as np

    window = audio[int(start * 48000) : int(end * 48000)]
    return float(np.sqrt(np.mean(window**2)))


def test_film_score():
    """AC9: two renders of the score are the same bytes; the RMS inside a cue is at least 6 dB
    below the RMS outside it."""
    first = score.render(DURATION, CUES)
    second = score.render(DURATION, CUES)
    assert isinstance(first, bytes) and first, "score.render returned no bytes"
    assert first == second, "two renders of the score differ"

    audio = samples(first)
    inside = rms(audio, *INSIDE)
    outside = min(rms(audio, *span) for span in OUTSIDE)
    assert outside > 0, "the score is silent outside the cue"
    ducked = 20 * math.log10(outside / inside) if inside > 0 else math.inf
    assert ducked >= 6, f"the score is ducked {ducked:.1f} dB under the cue, expected at least 6"


def test_film_score_bars():
    """AC3 (#49): the score's bar is 4 beats at 96 BPM, and every chapter's start in
    ``timeline.beats()`` is a whole number of bars."""
    expected = 4 * 60 / BPM
    assert abs(score.BAR - expected) <= TOLERANCE, f"score.BAR is {score.BAR} s, expected {expected} s (4/4 at {BPM} BPM)"

    starts: dict[str, float] = {}
    for beat in timeline.beats():
        starts.setdefault(beat["chapter"], beat["start"])
    assert starts, "timeline.beats() gave no chapters"
    off = []
    for chapter, start in starts.items():
        bars = start / score.BAR
        if abs(bars - round(bars)) * score.BAR > TOLERANCE:
            off.append(f"{chapter} starts at {start} s, {bars:.4f} bars of {score.BAR} s")
    assert not off, "chapters that do not start on a bar, expected a whole number of bars:\n" + "\n".join(off)
