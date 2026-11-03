"""The rendered cut's format (story #39: AC1).

The cut is ``out/film/declarative-data-platform-explainer.mp4``, which ``uv run task film``
writes. The spec's check renders first (``uv run task film && uv run pytest -k
film_cut_format``); when the cut is not there, this test renders it with that task. It needs the
Kokoro files in ``.models/`` (``task film:models``) and ffmpeg, and skips, saying which is missing,
without them, as in CI's test job (EC4).

- ``-k film_cut_format``: AC1.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from fractions import Fraction

import pytest
from harness import REPO, tail

CUT = REPO / "out" / "film" / "declarative-data-platform-explainer.mp4"
MODELS = REPO / ".models"


def test_film_cut_format():
    """AC1: the cut is 1920x1080 at 60 fps, H.264 video and AAC audio, lasting 100 to 140 s."""
    if not MODELS.is_dir() or not any(MODELS.iterdir()):
        pytest.skip(".models/ holds no Kokoro files: run `uv run task film:models` to render the cut")
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            pytest.skip(f"{tool} is not installed: the cut cannot be rendered or probed")

    if not CUT.is_file():
        proc = subprocess.run(
            ["uv", "run", "task", "film"], cwd=REPO, capture_output=True, text=True, timeout=3600
        )
        assert proc.returncode == 0, f"`uv run task film` exited {proc.returncode}:\n{tail(proc.stdout + proc.stderr)}"
    assert CUT.is_file(), f"{CUT.relative_to(REPO)} was not written"

    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(CUT)],
        capture_output=True, text=True, check=True,
    )
    found = json.loads(probe.stdout)
    video = [s for s in found["streams"] if s["codec_type"] == "video"]
    audio = [s for s in found["streams"] if s["codec_type"] == "audio"]
    assert len(video) == 1, f"the cut has {len(video)} video streams"
    assert len(audio) == 1, f"the cut has {len(audio)} audio streams"
    (video,), (audio,) = video, audio
    assert video["codec_name"] == "h264", f"the video is {video['codec_name']}, expected h264"
    assert (video["width"], video["height"]) == (1920, 1080), f"the video is {video['width']}x{video['height']}"
    rate = Fraction(video["avg_frame_rate"])
    assert abs(float(rate) - 60) < 0.01, f"the video runs at {float(rate):.3f} fps, expected 60"
    assert audio["codec_name"] == "aac", f"the audio is {audio['codec_name']}, expected aac"
    duration = float(found["format"]["duration"])
    assert 100 <= duration <= 140, f"the cut lasts {duration:.1f} s, expected 100 to 140"
