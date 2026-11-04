"""The render's failures are the film's own errors (story #39: review round 1, F8).

``film.render._segment((html, first, last, file))`` renders frames ``first`` up to ``last`` of the
page and pipes them to ``ffmpeg`` on ``PATH``, encoding ``file``. Whatever stops the encode, the
run fails with ``film.render.RenderError``, which ``film``'s command line reports as
``film: ...``; a broken pipe is not let out past it.

- ``-k film_render_ffmpeg_exit``: an ffmpeg that exits at once (F8).
- ``-k film_poster``: ``render.cut`` also writes the poster still,
  ``declarative-data-platform-explainer.jpg`` beside the MP4, one frame of the cut taken 3 s into
  the lockup (story #49: AC13).
"""

from __future__ import annotations

import os
import stat
import subprocess

import pytest

from film import render, score, timeline, voice

POSTER = "declarative-data-platform-explainer.jpg"
# AC13: the poster is the lockup's title card, which is whole 3 s into the lockup.
INTO_LOCKUP = 3.0
SEEK = ("-ss",)
ONE_FRAME = ("-frames:v", "-vframes", "-frames")


def test_film_render_ffmpeg_exit_is_a_render_error(tmp_path, monkeypatch):
    """F8: an ffmpeg that exits before reading a frame makes the segment fail with RenderError,
    not a BrokenPipeError."""
    tools = tmp_path / "bin"
    tools.mkdir()
    ffmpeg = tools / "ffmpeg"
    ffmpeg.write_text("#!/bin/sh\nexec 0<&-\nexit 1\n", encoding="utf-8")
    ffmpeg.chmod(ffmpeg.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", f"{tools}{os.pathsep}{os.environ.get('PATH', '')}")

    with pytest.raises(render.RenderError):
        render._segment((render.page(), 0, 30, str(tmp_path / "part.mp4")))


class _Pool:
    """``multiprocessing``'s spawn pool, run in this process so the stubbed segment is used."""

    def __init__(self, workers):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def map(self, fn, jobs):
        return [fn(job) for job in jobs]


class _Context:
    def Pool(self, workers):
        return _Pool(workers)


def _seconds(value: str) -> float:
    """An ffmpeg time, as seconds or [[hh:]mm:]ss[.ms]."""
    total = 0.0
    for part in str(value).split(":"):
        total = total * 60 + float(part)
    return total


@pytest.fixture
def stubbed_cut(tmp_path, monkeypatch):
    """``render.cut`` with no Kokoro, no Chromium and no real ffmpeg: every ffmpeg run is recorded
    and writes an empty file at its last argument, the output."""
    calls: list[list[str]] = []

    def run(args, *rest, **kwargs):
        args = [str(a) for a in args]
        calls.append(args)
        if args and os.path.basename(args[0]) == "ffmpeg" and len(args) > 1:
            output = args[-1]
            if output not in ("-", "pipe:", "pipe:1") and not output.startswith("-"):
                os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
                open(output, "wb").close()
        text = kwargs.get("text") or kwargs.get("universal_newlines")
        return subprocess.CompletedProcess(args, 0, "" if text else b"", "" if text else b"")

    def check(args, *rest, **kwargs):
        return run(args, *rest, **kwargs).stdout

    def segment(job):
        _, _, _, file = job
        open(file, "wb").close()
        return file

    monkeypatch.setattr(render.shutil, "which", lambda tool: f"/usr/bin/{tool}")
    monkeypatch.setattr(voice, "synthesizer", lambda *args, **kwargs: lambda text: None)
    monkeypatch.setattr(voice, "place", lambda lines, synthesize, end: [])
    monkeypatch.setattr(voice, "track", lambda placed, duration, sr: [])
    monkeypatch.setattr(score, "wav", lambda samples, sr: b"")
    monkeypatch.setattr(score, "render", lambda duration, ducks: b"")
    monkeypatch.setattr(render, "page", lambda *args, **kwargs: "<!doctype html>")
    monkeypatch.setattr(render, "_segment", segment)
    monkeypatch.setattr(render.multiprocessing, "get_context", lambda method=None: _Context())
    monkeypatch.setattr(render.subprocess, "run", run)
    monkeypatch.setattr(render.subprocess, "check_call", lambda *a, **k: run(*a, **k).returncode)
    monkeypatch.setattr(render.subprocess, "check_output", check)
    out = tmp_path / "out"
    return out, calls


def _flag(args: list[str], names: tuple[str, ...]) -> str | None:
    for i, arg in enumerate(args[:-1]):
        if arg in names:
            return args[i + 1]
    return None


def test_film_poster_written_beside_the_cut(stubbed_cut):
    """AC13: ``render.cut`` writes the poster beside the MP4, extracting one frame of the cut at
    the lockup's start plus 3 s into ``declarative-data-platform-explainer.jpg``."""
    out, calls = stubbed_cut
    target = render.cut(out, workers=1)
    assert target == out / render.CUT, f"render.cut returned {target}, expected {out / render.CUT}"

    poster = out / POSTER
    lockup = next(b["start"] for b in timeline.beats() if b["chapter"] == "lockup")
    at = lockup + INTO_LOCKUP
    ffmpeg = [args for args in calls if args and os.path.basename(args[0]) == "ffmpeg"]
    writes = [args for args in ffmpeg if str(poster) in args]
    assert writes, (
        f"render.cut never asks ffmpeg to write {poster}; its ffmpeg runs write "
        f"{[args[-1] for args in ffmpeg]}"
    )
    assert len(writes) == 1, f"render.cut writes the poster in {len(writes)} ffmpeg runs, expected one"
    (args,) = writes
    inputs = [args[i + 1] for i, arg in enumerate(args[:-1]) if arg == "-i"]
    assert inputs == [str(out / render.CUT)], (
        f"the poster is taken from {inputs}, expected the cut {out / render.CUT}"
    )
    seek = _flag(args, SEEK)
    assert seek is not None, f"the poster's ffmpeg run seeks nowhere (no -ss): {args}"
    assert abs(_seconds(seek) - at) < 0.05, (
        f"the poster is taken at {seek}, expected {at:.2f} s (the lockup at {lockup:.2f} s plus {INTO_LOCKUP} s)"
    )
    frames = _flag(args, ONE_FRAME)
    assert frames == "1", f"the poster's ffmpeg run writes {frames!r} frames, expected exactly 1: {args}"
    assert args.index(str(poster)) > args.index(str(out / render.CUT)), (
        f"the poster's ffmpeg run reads the poster rather than writing it: {args}"
    )
    assert poster.is_file(), f"render.cut left no poster at {poster}"
    cut_written = max(i for i, a in enumerate(ffmpeg) if str(out / render.CUT) == a[-1])
    assert ffmpeg.index(args) > cut_written, "render.cut takes the poster before it has written the cut"
