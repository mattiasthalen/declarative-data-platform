"""The narration's guards: the Kokoro files' checksums, and no line running past the next cue
(story #39: AC10).

``film.voice.verify(models)`` raises ``film.voice.ModelError`` for a missing file or a checksum
mismatch, before anything loads them. ``film.voice.place(lines, synthesize)`` places each
narration line (``{"text", "cue"}``) at its cue and raises ``film.voice.Overrun``, naming the
line, when one runs past the next cue; ``synthesize(text)`` returns a numpy array at 24 kHz.
Every test here stubs the synthesizer and none needs the Kokoro files (EC4).

- ``-k film_voice_guards``: AC10.
"""

from __future__ import annotations

import re

import pytest

from film import voice

RATE = 24000
LINES = [
    {"text": "Pipelines are written by hand.", "cue": 0.0},
    {"text": "Ingest lands what a source declares.", "cue": 5.0},
    {"text": "Conform holds it to its contract.", "cue": 10.0},
]
MODEL_FILE = re.compile(r"[\w.-]+\.(?:onnx|bin|npz|json|npy)\b")


def stub(seconds: dict[str, float]):
    """A synthesizer that returns silence lasting ``seconds[text]`` (1 s for any other line)."""
    import numpy as np

    def synthesize(text: str):
        return np.zeros(int(RATE * seconds.get(text, 1.0)), dtype=np.float32)

    return synthesize


def verify_refuses_bad_models(tmp_path) -> None:
    """AC10: verify refuses a folder missing the Kokoro files, naming one, and refuses files whose
    SHA-256 is not the pinned one."""
    models = tmp_path / "models"
    models.mkdir()
    with pytest.raises(voice.ModelError) as raised:
        voice.verify(models)

    # Create, with the wrong bytes, every file the refusals name, until none is missing.
    created: set[str] = set()
    for _ in range(10):
        named = set(MODEL_FILE.findall(str(raised.value))) - created
        if not named:
            break
        for name in named:
            (models / name).write_bytes(b"not the Kokoro model")
            created.add(name)
        with pytest.raises(voice.ModelError) as raised:
            voice.verify(models)
    assert created, f"verify's refusal of an empty folder names no model file: {raised.value}"
    assert all((models / name).is_file() for name in created)
    # Every file named is now present, so this refusal is the checksum's.
    assert set(MODEL_FILE.findall(str(raised.value))) <= created, raised.value
    assert MODEL_FILE.search(str(raised.value)), f"verify's checksum refusal names no file: {raised.value}"


def place_refuses_an_overrun() -> None:
    """AC10: place accepts lines that end before the next cue, and raises Overrun, naming the line,
    when the synthesized audio of one runs past the next line's cue."""
    placed = voice.place(LINES, stub({}))
    assert len(placed) == len(LINES), f"place placed {len(placed)} of {len(LINES)} lines"

    long = LINES[1]["text"]
    with pytest.raises(voice.Overrun) as raised:
        voice.place(LINES, stub({long: 6.5}))
    assert long in str(raised.value) or re.search(r"\bline\s*2\b", str(raised.value), re.IGNORECASE), (
        f"the Overrun does not name the line that runs over: {raised.value}"
    )


def test_film_voice_guards(tmp_path):
    """AC10: verify refuses missing and mismatched Kokoro files; place raises Overrun on a stubbed
    synthesizer whose line runs past the next cue."""
    verify_refuses_bad_models(tmp_path)
    place_refuses_an_overrun()
