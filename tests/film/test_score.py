"""The explainer's score is deterministic and ducks under the narration (story #39: AC9), and
plays at 96 BPM with every chapter starting on a bar (story #49: AC3).

``film.score.render(duration, cues)`` returns the score as a 48 kHz stereo 16-bit WAV, ducked
inside each ``(start, end)`` cue. The loudness is compared away from the ducking's ramps and the
score's own fade in and out.

- ``-k film_score``: AC9 (#39), AC4 (#49): ducked at least 6 dB and at most 10 dB, and still ducked
  between cues less than 1.5 s apart.
- ``-k film_score_bed``: AC12 (#49): the score sits under the voice, peaking at most -15 dBFS.
- ``-k film_score_bars``: AC3 (#49). ``film.score.BAR`` is the length of one bar in seconds.
"""

from __future__ import annotations

import io
import math
import wave

from film import score, timeline

DURATION = 40.0
CUES = [(15.0, 21.0)]
# Inside the cue, and on both sides of it, clear of the ducking's ramps. All three lie in the ingest
# chapter (10 to 30 s), so a chapter whose score is quieter (the pad-only hook) cannot widen the gap.
INSIDE = (16.0, 20.0)
OUTSIDE = ((11.0, 13.5), (23.0, 28.0))
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
    """AC9 (#39), AC4 (#49): two renders of the score are the same bytes; the RMS inside a cue is
    at least 6 dB and at most 10 dB below the RMS on each side of it, in the same chapter."""
    first = score.render(DURATION, CUES)
    second = score.render(DURATION, CUES)
    assert isinstance(first, bytes) and first, "score.render returned no bytes"
    assert first == second, "two renders of the score differ"

    audio = samples(first)
    for span in OUTSIDE:
        ducked = level(audio, span, INSIDE)
        assert ducked >= 6, f"the score is ducked {ducked:.1f} dB under the cue against {span} s, expected at least 6"
        assert ducked <= 10, f"the score is ducked {ducked:.1f} dB under the cue against {span} s, expected at most 10"


def level(audio, louder: tuple[float, float], quieter: tuple[float, float]) -> float:
    """How many dB the RMS over ``louder`` is above the RMS over ``quieter``."""
    loud, quiet = rms(audio, *louder), rms(audio, *quieter)
    assert loud > 0 and quiet > 0, f"the score is silent over {louder if loud == 0 else quieter}"
    return 20 * math.log10(loud / quiet)


def test_film_score_bridges_short_gaps():
    """AC4 (#49): between cues 1.0 s apart the score stays ducked (the gap is within 3 dB of the
    ducked level); between cues 4 s apart it comes back up (at least 4 dB above the ducked level)."""
    short = samples(score.render(DURATION, [(12.0, 16.0), (17.0, 21.0)]))
    rise = level(short, (16.2, 16.8), (13.0, 15.0))
    assert abs(rise) <= 3, f"in a 1.0 s gap between cues the score is {rise:+.1f} dB from its ducked level, expected within 3 dB"

    long = samples(score.render(DURATION, [(12.0, 15.0), (19.0, 22.0)]))
    rise = level(long, (16.5, 17.5), (13.0, 14.5))
    assert rise >= 4, f"in a 4 s gap between cues the score is {rise:+.1f} dB from its ducked level, expected at least 4 dB above"


# AC12 (#49), in dBFS: the score's loudest sample; the most its RMS may be under a cue, which
# keeps the music at least 12 dB under Lewis, whose RMS while speaking measures about -22 to
# -23 dBFS; and the least its RMS beside a cue may be.
BED_PEAK = -15.0
BED_DUCKED_CEILING = -35.0
BED_FLOOR = -45.0


def test_film_score_bed():
    """AC12 (#49): the score peaks at or below -15 dBFS; its RMS under the cue is at most
    -35 dBFS, at least 12 dB under Lewis's voice (a peak limit alone admits a score driven
    harder, louder under the same peak); and its RMS beside the cue stays above -45 dBFS, so the
    music is still heard."""
    import numpy as np

    audio = samples(score.render(DURATION, CUES))
    peak = float(np.max(np.abs(audio))) / 32768
    assert peak > 0, "the score is silent"
    peak_db = 20 * math.log10(peak)
    assert peak_db <= BED_PEAK, f"the score peaks at {peak_db:.1f} dBFS, expected at most {BED_PEAK}"

    under = rms(audio, *INSIDE) / 32768
    under_db = 20 * math.log10(under) if under > 0 else -math.inf
    assert under_db <= BED_DUCKED_CEILING, (
        f"the score's RMS under the cue, over {INSIDE} s, is {under_db:.1f} dBFS, expected at most {BED_DUCKED_CEILING}"
    )

    beside = rms(audio, *OUTSIDE[1]) / 32768
    beside_db = 20 * math.log10(beside) if beside > 0 else -math.inf
    assert beside_db > BED_FLOOR, f"the score's RMS over {OUTSIDE[1]} s is {beside_db:.1f} dBFS, expected above {BED_FLOOR}"


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
