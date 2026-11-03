"""The explainer's score, synthesized: the same arguments always give the same bytes.

Ported in spirit from daana-promo's `music.mjs` (pad, kick, hat, pluck arpeggio, bell, reverb),
vectorised with numpy: no per-sample filters, so a two-minute score renders in seconds. The
arrangement gains an instrument per layer, as the layers gain light in the design system.
"""

from __future__ import annotations

import io
import wave

import numpy as np

from film import timeline

SR = 48000
SEED = 1234
BED = 10 ** (-3 / 20)  # the whole score sits a little under the voice
DUCK = 10 ** (-18 / 20)  # and further down while a line is spoken
DUCK_LEAD, DUCK_RELEASE = 0.15, 0.4

CHORDS = {
    "Am9": [45, 52, 55, 60, 64, 71],
    "F9": [41, 48, 52, 57, 64, 67],
    "C9": [48, 55, 62, 64, 67, 72],
    "G6": [43, 50, 59, 64, 67, 71],
}
ROOTS = {"Am9": 33, "F9": 29, "C9": 36, "G6": 31}
ARPEGGIOS = {
    "Am9": [69, 72, 76, 79, 83, 79, 76, 72],
    "F9": [65, 69, 72, 76, 79, 76, 72, 69],
    "C9": [67, 72, 74, 76, 79, 76, 74, 72],
    "G6": [67, 71, 74, 76, 79, 76, 74, 71],
}
# A bell's partials: frequency ratio to (amplitude, decay in seconds).
BELL_PARTIALS = {1: (1, 1.3), 2: (0.45, 0.8), 3.01: (0.25, 0.5), 4.2: (0.12, 0.3)}
PROGRESSION = ["Am9", "F9", "C9", "G6"]
BAR = 2.0  # 120 BPM in 4/4: every chapter starts on a bar
CHORD_BARS = 2


def render(duration: float, cues: list[tuple[float, float]]) -> bytes:
    """The score as a 48 kHz stereo 16-bit WAV, ducked under each ``(start, end)`` cue."""
    rng = np.random.default_rng(SEED)
    n = int(round(duration * SR))
    t = np.arange(n) / SR
    dry = np.zeros((n, 2))
    send = np.zeros((n, 2))
    sections = _sections(duration)

    def level(name: str) -> np.ndarray:
        """1 inside the chapters where an instrument plays, eased in and out over a bar."""
        out = np.zeros(n)
        for start, end, instruments in sections:
            if name in instruments:
                out += np.clip((t - start) / BAR, 0, 1) * np.clip((end - t) / BAR + 1, 0, 1) * (t < end + BAR)
        return np.clip(out, 0, 1)

    pad = _pad(t, duration, rng)
    dry += pad * 1.6
    send += pad * 0.5

    beat = BAR / 4
    kicks = level("kick")
    for k in np.arange(0, duration, beat):
        _add(dry, *_kick(n, k), kicks[min(int(k * SR), n - 1)] * 0.3)
    hats = level("hat")
    for k in np.arange(beat / 2, duration, beat):
        _add(dry, *_hat(n, k, rng), hats[min(int(k * SR), n - 1)] * 0.5)
    plucks = level("pluck")
    for i, k in enumerate(np.arange(0, duration, beat / 2)):
        gain = plucks[min(int(k * SR), n - 1)]
        if gain > 0:
            note = ARPEGGIOS[_chord_at(k)][i % 8]
            at, p = _pluck(n, k, note, pan=-0.35 if i % 2 else 0.35)
            _add(dry, at, p, gain * 0.6)
            _add(send, at, p, gain * 0.42)
    basses = level("bass")
    for k in np.arange(0, duration, beat):
        gain = basses[min(int(k * SR), n - 1)]
        if gain > 0:
            _add(dry, *_bass(n, k, ROOTS[_chord_at(k)], beat * 0.9), gain * 0.5)
    for start, _end, _instruments in sections:
        at, b = _bell(n, start, 84)
        _add(dry, at, b, 0.7)
        _add(send, at, b, 0.9)

    mix = dry + _reverb(send, rng) * 0.5
    mix *= (BED * _ducking(t, cues))[:, None]
    return _master(mix, duration, rng)


def _sections(duration: float) -> list[tuple[float, float, set[str]]]:
    """The arrangement: each chapter adds an instrument as the data gains structure."""
    adds = {
        "hook": set(),
        "ingest": {"kick"},
        "conform": {"kick", "hat"},
        "integrate": {"kick", "hat", "pluck"},
        "serve": {"kick", "hat", "pluck", "bass"},
        "orchestration": {"kick", "hat", "pluck", "bass"},
        "lockup": set(),
    }
    spans: dict[str, list[float]] = {}
    for b in timeline.beats():
        span = spans.setdefault(b["chapter"], [b["start"], b["end"]])
        span[1] = b["end"]
    return [(start, min(end, duration), adds[name]) for name, (start, end) in spans.items() if start < duration]


def _chord_at(t: float) -> str:
    return PROGRESSION[int(t // (BAR * CHORD_BARS)) % len(PROGRESSION)]


def _mtof(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _pan(p: float) -> np.ndarray:
    return np.array([np.cos((p + 1) * np.pi / 4), np.sin((p + 1) * np.pi / 4)])


def _pad(t: np.ndarray, duration: float, rng) -> np.ndarray:
    """Detuned, softened saws per chord, crossfading at each change."""
    out = np.zeros((len(t), 2))
    length = BAR * CHORD_BARS
    for i, start in enumerate(np.arange(0, duration, length)):
        name = _chord_at(start)
        a, b = int(start * SR), min(len(t), int((start + length + 1.6) * SR))
        seg = t[a:b] - start
        env = np.clip(seg / (1.6 if i == 0 else 0.5), 0, 1) * np.clip(1 - (seg - length) / 1.6, 0, 1)
        env = env * env
        for v, m in enumerate(CHORDS[name]):
            for d, cents in enumerate((-8, 8)):
                f = _mtof(m) * 2 ** (cents / 1200)
                phase = rng.random() * 2 * np.pi
                wave_ = sum(np.sin(2 * np.pi * f * h * seg + phase * h) / h * 0.7 ** (h - 1) for h in range(1, 5))
                out[a:b] += np.outer(wave_ * env * 0.035 / np.sqrt(len(CHORDS[name])), _pan((d * 2 - 1) * 0.5 + (0.12 if v % 2 else -0.12)))
    return out


def _add(bus: np.ndarray, at: int, sound: np.ndarray, gain: float) -> None:
    if gain:
        bus[at : at + len(sound)] += sound * gain


def _hit(n: int, at: float, seconds: float) -> tuple[int, int, np.ndarray]:
    a = int(at * SR)
    b = min(n, a + int(seconds * SR))
    return a, b, np.arange(b - a) / SR


def _kick(n: int, at: float):
    a, b, x = _hit(n, at, 0.5)
    f = 46 + 110 * np.exp(-x / 0.028)
    phase = 2 * np.pi * np.cumsum(f) / SR
    s = np.sin(phase) * np.exp(-x / 0.2)
    return a, np.repeat(s[:, None], 2, axis=1)


def _hat(n: int, at: float, rng):
    a, b, x = _hit(n, at, 0.07)
    noise = rng.standard_normal(len(x) + 1)
    s = np.diff(noise) * 0.5 * np.exp(-x / 0.022) * 0.12
    return a, np.outer(s, _pan(0.25))


def _pluck(n: int, at: float, m: int, pan: float):
    a, b, x = _hit(n, at, 0.4)
    f = _mtof(m)
    s = (np.sin(2 * np.pi * f * x) + 0.3 * np.sin(4 * np.pi * f * x) * np.exp(-x / 0.04)) * np.exp(-x / 0.11)
    s *= np.clip(x / 0.002, 0, 1) * 0.06
    return a, np.outer(s, _pan(pan))


def _bass(n: int, at: float, m: int, seconds: float):
    a, b, x = _hit(n, at, seconds + 0.08)
    f = _mtof(m)
    env = np.clip(x / 0.004, 0, 1) * np.exp(-x / (seconds * 0.9)) * np.clip(1 - (x - seconds) / 0.08, 0, 1)
    s = (np.sin(2 * np.pi * f * x) * 0.8 + 0.25 * np.sin(4 * np.pi * f * x)) * env * 0.2
    return a, np.repeat(s[:, None], 2, axis=1)


def _bell(n: int, at: float, m: int):
    a, b, x = _hit(n, at, 2.4)
    f = _mtof(m)
    s = sum(np.sin(2 * np.pi * f * h * x) * amp * np.exp(-x / d) for h, (amp, d) in BELL_PARTIALS.items())
    s *= np.clip(x / 0.003, 0, 1) * 0.05
    return a, np.outer(s, _pan(0.3))


def _reverb(send: np.ndarray, rng) -> np.ndarray:
    """A 2.5 s tail of decaying noise, a different one per side, convolved through the FFT."""
    length = int(2.5 * SR)
    x = np.arange(length) / SR
    out = np.zeros_like(send)
    size = 1 << int(np.ceil(np.log2(len(send) + length)))
    for c in range(2):
        tail = rng.standard_normal(length) * np.exp(-x / 0.55) * 0.012
        tail[: int(0.02 * SR)] = 0
        wet = np.fft.irfft(np.fft.rfft(send[:, c], size) * np.fft.rfft(tail, size), size)
        out[:, c] = wet[: len(send)]
    return out


def _ducking(t: np.ndarray, cues: list[tuple[float, float]]) -> np.ndarray:
    """1 away from speech, DUCK while a line is spoken, with short ramps either side."""
    depth = np.zeros_like(t)
    for start, end in cues:
        rise = np.clip((t - (start - DUCK_LEAD)) / DUCK_LEAD, 0, 1)
        fall = np.clip(((end + DUCK_RELEASE) - t) / DUCK_RELEASE, 0, 1)
        depth = np.maximum(depth, np.minimum(rise, fall))
    return 1 - depth * (1 - DUCK)


def _master(mix: np.ndarray, duration: float, rng) -> bytes:
    n = len(mix)
    t = np.arange(n) / SR
    fade = np.clip(t / 0.25, 0, 1) * np.clip((duration - t) / 1.6, 0, 1)
    mix = np.tanh(mix * fade[:, None] * 1.1) / 1.1
    peak = float(np.max(np.abs(mix))) or 1.0
    mix *= 10 ** (-1 / 20) / peak
    dither = (rng.random(mix.shape) - rng.random(mix.shape)) / 32768
    pcm = np.clip(np.round((mix + dither) * 32767), -32768, 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(2)
        writer.setsampwidth(2)
        writer.setframerate(SR)
        writer.writeframes(pcm.tobytes())
    return buffer.getvalue()
