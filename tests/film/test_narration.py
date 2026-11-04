"""The narration names no field and no count (story #39: AC6); it speaks as Lewis, in British
English, and its cues stay in their beats (story #49: AC5, AC7, EC2).

The script is ``src/film/explainer/narration.json`` (``{"voice", "speed", "lang", "lines":
[{"text", "cue"}]}``). ``film.render`` reads it through ``film.timeline.narration()`` and hands
its voice, speed and lang to ``film.voice.synthesizer(models, voice, speed, lang)``, whose
``lang`` has no default. Kokoro is stubbed here, so no test needs its model files. The names are those [7]'s declarations hold: the contract's id, schema and
property names (logical and physical), the resource's file name, endpoint and conform name, and
the anchor's and its attributes' mnemonics and descriptors, with the mapping's columns. A name is
matched as a whole word, ignoring case, when it is 4 or more characters long.

- ``-k film_narration_generic``: AC6 (#39).
- ``-k film_narration_voice``: AC5 and EC2 (#49).
- ``-k film_narration_cues_in_beats``: AC7 (#49).
"""

from __future__ import annotations

import inspect
import json
import re
import sys
import types
from typing import ClassVar

import pytest
import yaml
from harness import REPO

from film import render, timeline, voice

NARRATION = REPO / "src" / "film" / "explainer" / "narration.json"
SOURCE = REPO / "sources" / "adventure_works" / "products.yaml"
CONTRACT = REPO / "contracts" / "adventure_works" / "products.yaml"
MODEL = REPO / "anchor" / "model.yaml"
MAPPING = REPO / "anchor" / "mappings" / "PR_Product.yaml"

# [1][2]: Lewis, a British male voice, at his natural speed.
VOICE = {"voice": "bm_lewis", "speed": 1.0, "lang": "en-gb"}
# [3]: the (chapter, beat) each line's cue sat in at base (origin/main before #49), in line order.
BASE_BEATS = [
    ("hook", "hook"),
    ("hook", "hook"),
    ("ingest", "close_up"),
    ("ingest", "close_up"),
    ("ingest", "zoom_out"),
    ("conform", "close_up"),
    ("conform", "close_up"),
    ("conform", "zoom_out"),
    ("integrate", "close_up"),
    ("integrate", "close_up"),
    ("integrate", "zoom_out"),
    ("serve", "close_up"),
    ("serve", "close_up"),
    ("serve", "zoom_out"),
    ("orchestration", "beat"),
    ("orchestration", "beat"),
]


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def declared_names() -> set[str]:
    names: set[str] = set()

    source = load(SOURCE)
    names |= {SOURCE.stem, f"{SOURCE.parent.name}__{SOURCE.stem}"}
    endpoint = (source or {}).get("endpoint") or {}
    if endpoint.get("path"):
        names.add(str(endpoint["path"]))

    contract = load(CONTRACT)
    names |= {str(contract[k]) for k in ("id", "name") if contract.get(k)}
    for table in contract.get("schema") or []:
        names |= {str(table[k]) for k in ("name", "physicalName") if table.get(k)}
        for prop in table.get("properties") or []:
            names |= {str(prop[k]) for k in ("name", "physicalName") if prop.get(k)}

    for anchor in load(MODEL)["schema"]["anchor"]:
        names |= {str(anchor["mnemonic"]), str(anchor["descriptor"])}
        for attribute in anchor.get("attribute") or []:
            names |= {
                str(attribute["mnemonic"]),
                str(attribute["descriptor"]),
                f"{anchor['mnemonic']}_{attribute['mnemonic']}_{anchor['descriptor']}_{attribute['descriptor']}",
            }

    mapping = load(MAPPING)
    names |= {str(mapping[k]) for k in ("anchor", "source", "changed_at") if mapping.get(k)}
    for attribute in mapping.get("attributes") or []:
        names |= {str(attribute[k]) for k in ("attribute", "column") if attribute.get(k)}

    return {name for name in names if len(name) >= 4}


def test_film_narration_generic():
    """AC6: no narration line holds a digit, or a field, resource or anchor name from [7]'s files."""
    lines = json.loads(NARRATION.read_text(encoding="utf-8"))["lines"]
    assert lines, f"{NARRATION.relative_to(REPO)} has no lines"
    names = declared_names()
    assert names, "found no names in the declarations"
    offending = []
    for number, line in enumerate(lines, 1):
        text = line["text"]
        if re.search(r"\d", text):
            offending.append(f"line {number} holds a digit: {text!r}")
        for name in sorted(names):
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text, re.IGNORECASE):
                offending.append(f"line {number} names {name!r}: {text!r}")
    assert not offending, "the narration names a count or a declared name:\n" + "\n".join(offending)


class FakeKokoro:
    """Stands in for ``kokoro_onnx.Kokoro``: records each ``create`` call and returns 0.1 s of
    silence at 24 kHz."""

    calls: ClassVar[list[dict]] = []

    def __init__(self, model, voices, *args, **kwargs):
        pass

    def create(self, text, voice=None, speed=1.0, lang="en-us", **kwargs):
        import numpy as np

        FakeKokoro.calls.append({"text": text, "voice": voice, "speed": speed, "lang": lang})
        return np.zeros(2400, dtype=np.float32), 24000


@pytest.fixture
def kokoro(monkeypatch):
    """Kokoro stubbed in ``sys.modules`` and ``voice.verify`` stubbed, so no model files are read."""
    FakeKokoro.calls = []
    module = types.ModuleType("kokoro_onnx")
    module.Kokoro = FakeKokoro
    monkeypatch.setitem(sys.modules, "kokoro_onnx", module)
    monkeypatch.setattr(voice, "verify", lambda models: None)
    return FakeKokoro


def test_film_narration_voice():
    """AC5: narration.json declares voice ``bm_lewis``, speed 1.0 and lang ``en-gb``."""
    narration = json.loads(NARRATION.read_text(encoding="utf-8"))
    found = {key: narration.get(key, "<missing>") for key in VOICE}
    assert found == VOICE, f"{NARRATION.relative_to(REPO)} declares {found}, expected {VOICE}"


@pytest.mark.parametrize("lang", ["en-gb", "pt-br"])
def test_film_narration_voice_lang_reaches_kokoro(kokoro, tmp_path, lang):
    """AC5: the synthesizer speaks with the lang it is given, not a hard-coded one."""
    synthesize = voice.synthesizer(tmp_path, "bm_lewis", 1.0, lang)
    synthesize("Declarations in. Structure out.")
    assert kokoro.calls, "the synthesizer never called Kokoro's create"
    langs = [call["lang"] for call in kokoro.calls]
    assert langs == [lang], f"Kokoro's create was called with lang {langs}, expected [{lang!r}]"


def test_film_narration_voice_lang_has_no_default():
    """EC2: ``voice.synthesizer`` takes ``lang`` and gives it no default, so a narration without
    one cannot fall back to American English."""
    parameters = inspect.signature(voice.synthesizer).parameters
    assert "lang" in parameters, f"voice.synthesizer takes {list(parameters)}, expected a lang parameter"
    default = parameters["lang"].default
    assert default is inspect.Parameter.empty, f"voice.synthesizer's lang defaults to {default!r}, expected no default"


def test_film_narration_voice_missing_lang_fails(kokoro, tmp_path, monkeypatch):
    """EC2: ``render.cut`` given a narration with no ``lang`` fails before synthesis, naming
    ``lang``: it builds no synthesizer and Kokoro speaks no line."""
    narration = json.loads(NARRATION.read_text(encoding="utf-8"))
    narration.pop("lang", None)
    monkeypatch.setattr(timeline, "narration", lambda: narration)
    monkeypatch.setattr(render.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    built = []

    def synthesizer(*args, **kwargs):
        built.append((args, kwargs))
        raise AssertionError(f"render built a synthesizer with no lang: {args} {kwargs}")

    monkeypatch.setattr(voice, "synthesizer", synthesizer)

    with pytest.raises((KeyError, TypeError, ValueError)) as raised:
        render.cut(tmp_path)
    assert "lang" in str(raised.value), f"the render's failure does not name lang: {raised.value!r}"
    assert not built, f"render built {len(built)} synthesizers with no lang, expected none"
    assert not kokoro.calls, f"Kokoro synthesized {len(kokoro.calls)} lines with no lang, expected none"


def test_film_narration_cues_in_beats():
    """AC7: each line's cue lies in the same beat (chapter and beat name) as it did at base."""
    lines = timeline.narration()["lines"]
    assert len(lines) == len(BASE_BEATS), f"the narration has {len(lines)} lines, expected {len(BASE_BEATS)}"
    beats = timeline.beats()
    moved = []
    for number, (line, expected) in enumerate(zip(lines, BASE_BEATS), 1):
        found = [(b["chapter"], b["beat"]) for b in beats if b["start"] <= line["cue"] < b["end"]]
        if found != [expected]:
            moved.append(f"line {number}'s cue {line['cue']} s is in {found or 'no beat'}, expected {expected}")
    assert not moved, "cues that left their beat:\n" + "\n".join(moved)
