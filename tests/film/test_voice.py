"""The narration's guards: the Kokoro files' checksums, and no line running past the next cue
(story #39: AC10).

``film.voice.verify(models)`` raises ``film.voice.ModelError`` for a missing file or a checksum
mismatch, before anything loads them. ``film.voice.place(lines, synthesize, end=...)`` places each
narration line (``{"text", "cue"}``) at its cue and raises ``film.voice.Overrun``, naming the
line, when one runs past the next cue, or the last past ``end`` (the lockup's start, where the
last caption ends); ``synthesize(text)`` returns a numpy array at 24 kHz.
Every test here stubs the synthesizer and none needs the Kokoro files (EC4).

- ``-k film_voice_guards``: AC10.
- ``-k film_voice_question``: AC11 (#49). ``film.voice.synthesizer(models, voice, speed, lang)``
  returns a callable that speaks a question inside a line (text up to and including a ``?`` with
  more after it) apart from the rest, with 0.6 s of silence between; Kokoro is stubbed.
"""

from __future__ import annotations

import re
import sys
import types
from typing import ClassVar

import pytest

from film import voice

RATE = 24000
# Where the last of LINES must have finished: the lockup's start.
END = 15.0
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
    placed = voice.place(LINES, stub({}), end=END)
    assert len(placed) == len(LINES), f"place placed {len(placed)} of {len(LINES)} lines"

    long = LINES[1]["text"]
    with pytest.raises(voice.Overrun) as raised:
        voice.place(LINES, stub({long: 6.5}), end=END)
    assert long in str(raised.value) or re.search(r"\bline\s*2\b", str(raised.value), re.IGNORECASE), (
        f"the Overrun does not name the line that runs over: {raised.value}"
    )


def test_film_voice_guards_last_line():
    """AC10, review F7: the last line is held to the lockup's start (``end``) as every other line
    is held to the next cue; place raises Overrun, naming it, when it runs past."""
    last = LINES[-1]["text"]
    placed = voice.place(LINES, stub({last: 3.0}), end=END)
    assert len(placed) == len(LINES), f"place placed {len(placed)} of {len(LINES)} lines"

    with pytest.raises(voice.Overrun) as raised:
        voice.place(LINES, stub({last: 6.5}), end=END)
    assert last in str(raised.value) or re.search(rf"\bline\s*{len(LINES)}\b", str(raised.value), re.IGNORECASE), (
        f"the Overrun does not name the last line, which runs past the lockup: {raised.value}"
    )


def test_film_voice_guards(tmp_path):
    """AC10: verify refuses missing and mismatched Kokoro files; place raises Overrun on a stubbed
    synthesizer whose line runs past the next cue."""
    verify_refuses_bad_models(tmp_path)
    place_refuses_an_overrun()


class SpokenKokoro:
    """Stands in for ``kokoro_onnx.Kokoro``: records each text ``create`` is given and returns
    ``len(text) * 0.01`` s of ones at 24 kHz."""

    texts: ClassVar[list[str]] = []

    def __init__(self, model, voices, *args, **kwargs):
        pass

    def create(self, text, voice=None, speed=1.0, lang="en-us", **kwargs):
        import numpy as np

        SpokenKokoro.texts.append(text)
        return np.ones(round(len(text) * 0.01 * RATE), dtype=np.float32), RATE


@pytest.fixture
def spoken(monkeypatch, tmp_path):
    """The synthesizer over a stubbed Kokoro and a stubbed ``voice.verify``: no model files."""
    SpokenKokoro.texts = []
    module = types.ModuleType("kokoro_onnx")
    module.Kokoro = SpokenKokoro
    monkeypatch.setitem(sys.modules, "kokoro_onnx", module)
    monkeypatch.setattr(voice, "verify", lambda models: None)
    return voice.synthesizer(tmp_path, "bm_lewis", 1.0, "en-gb")


def spoken_length(text: str) -> int:
    return round(len(text) * 0.01 * RATE)


QUESTION_PAUSE = round(0.6 * RATE)


def test_film_voice_question_pauses(spoken):
    """AC11 (#49): a question inside a line is spoken apart from the rest, with 0.6 s of silence
    between them."""
    import numpy as np

    question, rest = "Why?", "A contract is a promise."
    audio = np.asarray(spoken(f"{question} {rest}"))
    assert SpokenKokoro.texts == [question, rest], f"Kokoro's create was given {SpokenKokoro.texts}, expected {[question, rest]}"

    asked, answered = spoken_length(question), spoken_length(rest)
    expected = asked + QUESTION_PAUSE + answered
    assert abs(len(audio) - expected) <= 1, f"the line is {len(audio)} samples, expected {expected} (the two parts and 0.6 s)"
    pause = audio[asked : asked + QUESTION_PAUSE]
    assert not np.any(pause), f"{np.count_nonzero(pause)} samples in the 0.6 s after the question are not silent"
    assert np.all(audio[:asked] == 1), "the question's audio does not open the line"
    assert np.all(audio[asked + QUESTION_PAUSE : asked + QUESTION_PAUSE + answered - 1] == 1), "the rest's audio does not follow the pause"


def test_film_voice_question_none(spoken):
    """AC11 (#49): a line with no question is spoken in one call and returned as it was spoken."""
    import numpy as np

    line = "Ingest is where data arrives."
    audio = np.asarray(spoken(line))
    assert SpokenKokoro.texts == [line], f"Kokoro's create was given {SpokenKokoro.texts}, expected {[line]}"
    assert len(audio) == spoken_length(line), f"the line is {len(audio)} samples, expected {spoken_length(line)}"
    assert np.all(audio == 1), "the line's audio is not what Kokoro returned"


def test_film_voice_question_at_end(spoken):
    """AC11 (#49): a line that ends on its question is spoken in one call, with no silence added."""
    import numpy as np

    line = "Where does the data go?"
    audio = np.asarray(spoken(line))
    assert SpokenKokoro.texts == [line], f"Kokoro's create was given {SpokenKokoro.texts}, expected {[line]}"
    assert len(audio) == spoken_length(line), f"the line is {len(audio)} samples, expected {spoken_length(line)}, no added silence"
