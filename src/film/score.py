"""The explainer's score, synthesized: the same arguments always give the same bytes.

An 80s sci-fi score: a chorused saw pad, an octave-jumping saw bass through a resonant filter,
a pulse-wave arpeggio with a ping-pong echo, a dry kick on every beat and a dry snare on three.
The arrangement gains instruments as the data gains structure, as the layers gain light in the
design system.
"""

from __future__ import annotations

import io
import wave

import numpy as np
from scipy.signal import butter, lfilter, sosfilt

from film import timeline

SR = 48000
SEED = 1234
BPM = 96
BEAT = 60 / BPM
BAR = 4 * BEAT  # 2.5 s: every chapter starts on a bar
BED = 10 ** (-3 / 20)  # the whole score sits a little under the voice
DUCK = 10 ** (-18 / 20)  # and further down while a line is spoken
DUCK_LEAD, DUCK_RELEASE = 0.15, 0.4

# One chord a bar: Am, C/G, F, E.
CHORDS = [[57, 60, 64], [55, 60, 64], [53, 57, 60], [52, 56, 59]]
ROOTS = [33, 31, 29, 28]
ARPEGGIOS = [[69, 72, 76, 81], [67, 72, 76, 79], [65, 69, 72, 77], [64, 68, 71, 76]]
ARPEGGIO_ORDER = [0, 1, 2, 3, 2, 1, 0, 2]

ARRANGEMENT = {
    "hook": set(),
    "ingest": {"kick", "bass"},
    "conform": {"kick", "bass", "snare"},
    "integrate": {"kick", "bass", "snare", "arpeggio"},
    "serve": {"kick", "bass", "snare", "arpeggio"},
    "orchestration": {"kick", "bass", "snare", "arpeggio"},
    "lockup": set(),
}


def render(duration: float, cues: list[tuple[float, float]]) -> bytes:
    """The score as a 48 kHz stereo 16-bit WAV, ducked under each ``(start, end)`` cue."""
    rng = np.random.default_rng(SEED)
    n = int(round(duration * SR))
    t = np.arange(n) / SR
    dry = np.zeros((n, 2))
    send = np.zeros((n, 2))
    playing = _arrangement(duration)

    pad = _chorus(_pad(n, duration))
    dry += pad
    send += pad * 0.6

    for k in np.arange(0, duration, BAR / 16):
        bar = int(k // BAR)
        if "bass" in playing(k):
            note = ROOTS[bar % 4] + (12 if round(k / (BAR / 16)) % 2 else 0)
            opened = min(1.0, (k - _first(playing, "bass", duration)) / (4 * BAR))
            _add(dry, k, _bass(note, BAR / 16 * 0.9, 1200 + 1200 * opened), 1.0)

    arpeggio = np.zeros((n, 2))
    for i, k in enumerate(np.arange(0, duration, BEAT / 2)):
        if "arpeggio" in playing(k):
            note = ARPEGGIOS[int(k // BAR) % 4][ARPEGGIO_ORDER[i % 8]]
            _add(arpeggio, k, _pan(_arpeggio_note(note, BEAT / 2 * 0.9), 0.4 if i % 2 else -0.4), 0.075)
    echo = np.zeros_like(arpeggio)
    delay = int(BEAT * 0.75 * SR)
    echo[delay:] = arpeggio[:-delay, ::-1] * 0.35
    dry += arpeggio + echo
    send += arpeggio * 0.4

    kick, snare = _kick(rng), _snare(rng)
    for k in np.arange(0, duration, BEAT):
        if "kick" in playing(k):
            _add(dry, k, _pan(kick, 0), 0.95)
        if "snare" in playing(k) and round(k / BEAT) % 4 == 2:
            _add(dry, k, _pan(snare, 0), 0.4)

    mix = dry + _reverb(send, rng)
    mix *= (BED * _ducking(t, cues))[:, None]
    return _master(mix, duration, rng)


def _arrangement(duration: float):
    """What plays at a time, by the chapter it falls in."""
    spans: dict[str, list[float]] = {}
    for b in timeline.beats():
        span = spans.setdefault(b["chapter"], [b["start"], b["end"]])
        span[1] = b["end"]
    chapters = [(start, end, ARRANGEMENT[name]) for name, (start, end) in spans.items() if start < duration]

    def playing(at: float) -> set[str]:
        return next((instruments for start, end, instruments in chapters if start <= at < end), set())

    return playing


def _first(playing, instrument: str, duration: float) -> float:
    return next((float(k) for k in np.arange(0, duration, BAR) if instrument in playing(k)), 0.0)


def _mtof(m: float) -> float:
    return 440.0 * 2 ** ((m - 69) / 12)


def _pan(mono: np.ndarray, p: float) -> np.ndarray:
    return np.outer(mono, [np.cos((p + 1) * np.pi / 4), np.sin((p + 1) * np.pi / 4)])


def _add(bus: np.ndarray, at: float, sound: np.ndarray, gain: float) -> None:
    a = int(round(at * SR))
    if a < len(bus):
        sound = sound[: len(bus) - a]
        bus[a : a + len(sound)] += gain * (sound if sound.ndim == 2 else _pan(sound, 0))


def _saw(f: float, x: np.ndarray) -> np.ndarray:
    return 2 * ((f * x) % 1.0) - 1


def _lowpass(signal: np.ndarray, cutoff: float) -> np.ndarray:
    return sosfilt(butter(2, min(cutoff, SR / 2 - 100), "low", fs=SR, output="sos"), signal)


def _highpass(signal: np.ndarray, cutoff: float) -> np.ndarray:
    return sosfilt(butter(2, cutoff, "high", fs=SR, output="sos"), signal)


def _resonant(signal: np.ndarray, start: float, end: float, q: float, tau: float, steps: int) -> np.ndarray:
    """A resonant lowpass whose cutoff falls from ``start`` to ``end`` Hz with time constant ``tau``,
    stepped in blocks with the filter's state carried across."""
    out = np.zeros_like(signal)
    state = np.zeros(2)
    edges = np.linspace(0, len(signal), steps + 1).astype(int)
    for a, b in zip(edges[:-1], edges[1:]):
        cutoff = end + (start - end) * np.exp(-a / SR / tau)
        w = 2 * np.pi * min(cutoff, SR * 0.45) / SR
        alpha, cos = np.sin(w) / (2 * q), np.cos(w)
        num = np.array([(1 - cos) / 2, 1 - cos, (1 - cos) / 2])
        den = np.array([1 + alpha, -2 * cos, 1 - alpha])
        out[a:b], state = lfilter(num / den[0], den / den[0], signal[a:b], zi=state)
    return out


def _pad(n: int, duration: float) -> np.ndarray:
    """Detuned saws a chord a bar, swelling in on the first and overlapping into the next; the
    lockup rests on Am so the film ends resolved."""
    out = np.zeros(n)
    lockup = next(b["start"] for b in timeline.beats() if b["chapter"] == "lockup")
    for i, start in enumerate(np.arange(0, duration, BAR)):
        chord = CHORDS[0 if start >= lockup else i % 4]
        notes = chord + [chord[0] + 12]
        length = BAR + 0.6
        x = np.arange(int(length * SR)) / SR
        tone = sum(_saw(_mtof(m) * d, x) for m in notes for d in (0.997, 1.003)) / len(notes)
        envelope = np.clip(x / (1.2 if i == 0 else 0.6), 0, 1) * np.clip((length - x) / 0.4, 0, 1)
        a = int(round(start * SR))
        chunk = (_lowpass(tone * envelope, 1100) * 0.25)[: n - a]
        out[a : a + len(chunk)] += chunk
    return out


def _chorus(mono: np.ndarray) -> np.ndarray:
    """Two slowly modulated delays, one per side, around the dry signal."""
    index = np.arange(len(mono))
    sides = []
    for phase in (0, np.pi):
        delay = (0.007 + 0.004 * (0.5 + 0.5 * np.sin(2 * np.pi * 0.3 * index / SR + phase))) * SR
        sides.append(0.6 * mono + 0.5 * np.interp(index - delay, index, mono, left=0))
    return np.stack(sides, axis=1)


def _bass(note: int, seconds: float, cutoff: float) -> np.ndarray:
    x = np.arange(int(seconds * SR)) / SR
    f = _mtof(note)
    tone = _saw(f, x) + 0.6 * _saw(f * 1.004, x)
    envelope = np.clip(x / 0.002, 0, 1) * np.clip((seconds - x) / 0.01, 0, 1)
    return _resonant(tone * envelope, cutoff, 220, q=6, tau=0.07, steps=24) * 0.35


def _arpeggio_note(note: int, seconds: float) -> np.ndarray:
    x = np.arange(int(seconds * SR)) / SR
    tone = np.where((_mtof(note) * x) % 1.0 < 0.25, 1.0, -1.0)
    tone *= np.clip((seconds - x) / 0.004, 0, 1)
    return _resonant(tone, 3600, 800, q=3, tau=0.06, steps=8)


def _kick(rng) -> np.ndarray:
    """Firm and dry: a falling sine with a click on top, 300 ms."""
    x = np.arange(int(0.3 * SR)) / SR
    f = 52 + 160 * np.exp(-x / 0.018)
    body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-x / 0.11)
    click = _highpass(rng.standard_normal(len(x)), 3000) * np.exp(-x / 0.002) * 0.4
    return np.tanh((body + click) * 1.8)


def _snare(rng) -> np.ndarray:
    """Short and dry, 120 ms, with no room on it."""
    x = np.arange(int(0.12 * SR)) / SR
    body = np.sin(2 * np.pi * 200 * x) * np.exp(-x / 0.02)
    noise = _highpass(rng.standard_normal(len(x)), 1800) * np.exp(-x / 0.03)
    return body * 0.5 + noise * 0.45


def _reverb(send: np.ndarray, rng) -> np.ndarray:
    """A 3 s tail of decaying noise, a different one per side, convolved through the FFT."""
    length = int(3.0 * SR)
    x = np.arange(length) / SR
    out = np.zeros_like(send)
    size = 1 << int(np.ceil(np.log2(len(send) + length)))
    for c in range(2):
        tail = rng.standard_normal(length) * np.exp(-x / 0.8) * 0.01
        tail[: int(0.015 * SR)] = 0
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
    fade = np.clip(t / 0.25, 0, 1) * np.clip((duration - t) / 2.5, 0, 1)
    # The arpeggio's narrow pulse carries DC; the highpass takes it out before the saturation.
    mix = np.stack([_highpass(_lowpass(mix[:, c], 11000), 20) for c in range(2)], axis=1)
    mix = np.tanh(mix * fade[:, None] * 1.1) / 1.1
    peak = float(np.max(np.abs(mix))) or 1.0
    mix *= 10 ** (-1 / 20) / peak
    dither = (rng.random(mix.shape) - rng.random(mix.shape)) / 32768
    return wav(mix + dither, SR)


def wav(samples: np.ndarray, rate: int) -> bytes:
    """16-bit PCM WAV of ``samples`` in -1..1: one column per channel, or a flat array for mono."""
    pcm = np.clip(np.round(samples * 32767), -32768, 32767).astype("<i2")
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as writer:
        writer.setnchannels(1 if samples.ndim == 1 else samples.shape[1])
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(pcm.tobytes())
    return buffer.getvalue()
