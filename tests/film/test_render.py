"""The render's failures are the film's own errors (story #39: review round 1, F8).

``film.render._segment((html, first, last, file))`` renders frames ``first`` up to ``last`` of the
page and pipes them to ``ffmpeg`` on ``PATH``, encoding ``file``. Whatever stops the encode, the
run fails with ``film.render.RenderError``, which ``film``'s command line reports as
``film: ...``; a broken pipe is not let out past it.

- ``-k film_render_ffmpeg_exit``: an ffmpeg that exits at once (F8).
"""

from __future__ import annotations

import os
import stat

import pytest

from film import render


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
