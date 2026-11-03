"""The explainer's narration, synthesized locally with Kokoro-82M (ADR-0035).

The model files are fetched from kokoro-onnx's own release and refused unless their SHA-256 is
the one pinned here, so every render speaks with the same voice.
"""

from __future__ import annotations

import hashlib
import urllib.request
from pathlib import Path
from typing import Callable

import numpy as np

KOKORO_RATE = 24000
RELEASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
MODELS = {
    "kokoro-v1.0.onnx": "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5",
    "voices-v1.0.bin": "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d",
}
# The narrator leaves this much air before the next line's cue.
BREATH = 0.15


class ModelError(Exception):
    """A Kokoro file is missing, or is not the one pinned."""


class Overrun(Exception):
    """A narration line runs past the next line's cue."""


def verify(models: Path) -> None:
    for name, digest in MODELS.items():
        path = Path(models) / name
        if not path.is_file():
            raise ModelError(f"{name} is missing from {models}: run `uv run task film:models`")
        if _sha256(path) != digest:
            raise ModelError(f"{name} in {models} does not match its pinned SHA-256 {digest}")


def fetch(models: Path) -> None:
    """Download each Kokoro file that is missing or wrong, moving it in only once it verifies."""
    models = Path(models)
    models.mkdir(parents=True, exist_ok=True)
    for name, digest in MODELS.items():
        path = models / name
        if path.is_file() and _sha256(path) == digest:
            continue
        part = path.with_name(name + ".part")
        urllib.request.urlretrieve(f"{RELEASE}/{name}", part)
        if _sha256(part) != digest:
            part.unlink()
            raise ModelError(f"{name} downloaded from {RELEASE} does not match its pinned SHA-256 {digest}")
        part.replace(path)
    verify(models)


def synthesizer(models: Path, voice: str, speed: float) -> Callable[[str], np.ndarray]:
    """Kokoro speaking in ``voice``; each call returns one line as samples at KOKORO_RATE."""
    verify(models)
    from kokoro_onnx import Kokoro

    kokoro = Kokoro(str(Path(models) / "kokoro-v1.0.onnx"), str(Path(models) / "voices-v1.0.bin"))

    def synthesize(text: str) -> np.ndarray:
        samples, rate = kokoro.create(text, voice=voice, speed=speed, lang="en-us")
        if rate != KOKORO_RATE:
            raise ModelError(f"Kokoro returned {rate} Hz, expected {KOKORO_RATE}")
        return np.asarray(samples, dtype=np.float32)

    return synthesize


def place(lines: list[dict], synthesize: Callable[[str], np.ndarray], end: float) -> list[dict]:
    """Each line from its cue, or right after the line before; an Overrun when one would still be
    speaking at the next line's cue, or the last line at ``end``, where its caption ends."""
    placed = []
    previous_end = 0.0
    for number, line in enumerate(lines, 1):
        audio = synthesize(line["text"])
        start = max(line["cue"], previous_end)
        stop = start + len(audio) / KOKORO_RATE
        limit, what = (lines[number]["cue"], f"line {number + 1}'s cue") if number < len(lines) else (end, "the end of its caption")
        if stop + BREATH > limit:
            raise Overrun(f"line {number} ({line['text']!r}) runs to {stop:.2f} s, past {what} at {limit} s")
        placed.append({"text": line["text"], "cue": line["cue"], "start": start, "end": stop, "audio": audio})
        previous_end = stop
    return placed


def track(placed: list[dict], duration: float, rate: int) -> np.ndarray:
    """The placed lines as one mono track at ``rate``, ``duration`` seconds long."""
    out = np.zeros(int(round(duration * rate)), dtype=np.float64)
    for line in placed:
        audio = line["audio"].astype(np.float64)
        source = np.arange(len(audio)) / KOKORO_RATE
        target = np.arange(int(len(audio) * rate / KOKORO_RATE)) / rate
        resampled = np.interp(target, source, audio)
        at = int(round(line["start"] * rate))
        out[at : at + len(resampled)] += resampled[: max(0, len(out) - at)]
    return out


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as file:
        for chunk in iter(lambda: file.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()
