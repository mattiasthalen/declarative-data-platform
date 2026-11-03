"""Renders the explainer: its page in Chromium, seeked frame by frame, piped to ffmpeg, then the
score and the narration mixed under it.

The page is one self-contained document, fonts and data inlined, so a render fetches nothing.
"""

from __future__ import annotations

import base64
import json
import multiprocessing
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from film import data, score, stages, timeline, voice

HERE = Path(__file__).parent
EXPLAINER = HERE / "explainer"
ROOT = HERE.parent.parent
OUT = ROOT / "out" / "film"
MODELS = ROOT / ".models"
CUT = "declarative-data-platform-explainer.mp4"
FPS = 60
WIDTH, HEIGHT = 1920, 1080
# The zoom-out box: its label takes the top band, its tiles are laid out in the space below it, and
# what a tile draws under its square (its name) needs the rest.
ZOOM_BOX = {"width": 1680, "height": 604, "top": 34}
ZOOM_W, ZOOM_H, ZOOM_LARGEST = ZOOM_BOX["width"], 500, 120
# The chapters that end on a zoom-out of the whole model.
LAYERS = ("ingest", "conform", "integrate", "serve")
FONTS = {
    ("Inter", 400): "inter-400.woff2",
    ("Inter", 500): "inter-500.woff2",
    ("Spectral", 600): "spectral-600.woff2",
    ("JetBrains Mono", 400): "jetbrains-mono-400.woff2",
}
X264 = [
    "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
    "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-tune", "animation", "-g", str(FPS * 2),
    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709", "-color_range", "tv",
]


class RenderError(Exception):
    """The page failed to draw, or a tool the render needs failed."""


def page(root: Path = ROOT) -> str:
    """The composition with the film's data, read from the declarations under ``root``."""
    film = data.build(root)
    zoom = {
        chapter["name"]: data.tile_grid(len(chapter["zoom_out"]["tiles"]), ZOOM_W, ZOOM_H, largest=ZOOM_LARGEST)
        for chapter in film["chapters"]
        if chapter["name"] in LAYERS
    }
    payload = {
        "chapters": film["chapters"],
        "beats": timeline.beats(),
        "captions": timeline.captions(),
        "duration": timeline.duration(),
        "stages": stages.as_data(),
        "zoom": zoom,
        "zoom_box": ZOOM_BOX,
    }
    fonts = "\n".join(
        f"@font-face {{ font-family: '{family}'; font-weight: {weight}; font-style: normal; "
        f"src: url(data:font/woff2;base64,{base64.b64encode((EXPLAINER / 'fonts' / file).read_bytes()).decode()}) format('woff2'); }}"
        for (family, weight), file in FONTS.items()
    )
    parts = {
        "/*FONTS*/": fonts,
        "/*STYLE*/": (EXPLAINER / "film.css").read_text(encoding="utf-8"),
        "/*FILM*/": json.dumps(payload).replace("</", "<\\/"),
        "/*SCRIPT*/": (EXPLAINER / "film.js").read_text(encoding="utf-8"),
    }
    # One pass, so a marker inside a declaration the payload carries stays text.
    html = (EXPLAINER / "index.html").read_text(encoding="utf-8")
    return re.sub("|".join(re.escape(marker) for marker in parts), lambda m: parts[m.group(0)], html)


class _Page:
    """One Chromium page holding the composition, ready to seek."""

    def __init__(self, html: str):
        from playwright.sync_api import sync_playwright

        self._playwright = sync_playwright().start()
        self._browser = None
        self.errors: list[str] = []
        try:
            self._browser = self._playwright.chromium.launch(
                args=["--force-color-profile=srgb", "--font-render-hinting=none", "--disable-lcd-text"]
            )
            self.page = self._browser.new_page(viewport={"width": WIDTH, "height": HEIGHT}, device_scale_factor=1)
            self.page.on("pageerror", lambda error: self.errors.append(str(error)))
            self.page.set_content(html, wait_until="load")
            self.page.wait_for_function("window.__ready === true", timeout=30000)
        except Exception as error:
            self.close()
            raise RenderError(f"the explainer never became ready: {self.errors or error}") from error
        self._check()

    def shot(self, t: float) -> bytes:
        self.page.evaluate("t => window.__seek(t)", t)
        self._check()
        return self.page.screenshot(type="png")

    def _check(self) -> None:
        if self.errors:
            raise RenderError(f"the explainer's page raised: {self.errors[0]}")

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
        self._playwright.stop()


def stills(times: list[float], out: Path) -> list[Path]:
    """One PNG per time, in the order given."""
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    browser = _Page(page())
    try:
        written = []
        for i, t in enumerate(times):
            path = out / f"still-{i:02d}-{t:07.2f}.png"
            path.write_bytes(browser.shot(t))
            written.append(path)
        return written
    finally:
        browser.close()


def _segment(job: tuple[str, int, int, str]) -> str:
    """Frames ``first`` up to ``last`` of the page, encoded into ``file``: one worker's share."""
    html, first, last, file = job
    browser = _Page(html)
    ffmpeg = subprocess.Popen(
        ["ffmpeg", "-y", "-loglevel", "error", "-f", "image2pipe", "-framerate", str(FPS), "-c:v", "png", "-i", "-", *X264, file],
        stdin=subprocess.PIPE,
    )
    try:
        for frame in range(first, last):
            ffmpeg.stdin.write(browser.shot(frame / FPS))
    except BrokenPipeError:
        pass  # ffmpeg has exited: its return code below says why
    finally:
        browser.close()
        try:
            ffmpeg.stdin.close()
        except BrokenPipeError:
            pass
    if ffmpeg.wait() != 0:
        raise RenderError(f"ffmpeg failed encoding frames {first} to {last} (exit {ffmpeg.returncode})")
    return file


def cut(out: Path = OUT, workers: int | None = None) -> Path:
    """The narrated, captioned cut: video, then the score ducked under the voice, mixed to -16 LUFS."""
    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            raise RenderError(f"{tool} is not installed")
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    duration = timeline.duration()
    narration = timeline.narration()
    print("narration: synthesizing", flush=True)
    placed = voice.place(
        narration["lines"],
        voice.synthesizer(MODELS, narration["voice"], narration["speed"], narration["lang"]),
        end=timeline.captions()[-1]["end"],
    )
    for line in placed:
        print(f"  {line['start']:6.2f} to {line['end']:6.2f}  {line['text']}", flush=True)
    voice_wav = out / "voice.wav"
    voice_wav.write_bytes(score.wav(voice.track(placed, duration, score.SR), score.SR))
    music_wav = out / "music.wav"
    music_wav.write_bytes(score.render(duration, [(line["start"], line["end"]) for line in placed]))

    html = page()
    frames = int(round(duration * FPS))
    workers = workers or max(1, min(4, os.cpu_count() or 1))
    bounds = [round(frames * k / workers) for k in range(workers + 1)]
    with tempfile.TemporaryDirectory(dir=out) as scratch:
        jobs = [(html, bounds[k], bounds[k + 1], str(Path(scratch) / f"part-{k}.mp4")) for k in range(workers)]
        print(f"video: {frames} frames at {FPS} fps in {workers} workers", flush=True)
        with multiprocessing.get_context("spawn").Pool(workers) as pool:
            parts = pool.map(_segment, jobs)
        listing = Path(scratch) / "parts.txt"
        listing.write_text("".join(f"file '{part}'\n" for part in parts))
        video = Path(scratch) / "video.mp4"
        _ffmpeg("-f", "concat", "-safe", "0", "-i", str(listing), "-c", "copy", str(video))
        target = out / CUT
        _ffmpeg(
            "-i", str(video), "-i", str(music_wav), "-i", str(voice_wav),
            "-filter_complex", "[1:a][2:a]amix=inputs=2:duration=first:normalize=0,loudnorm=I=-16:TP=-1.5:LRA=11,aresample=48000[a]",
            "-map", "0:v", "-map", "[a]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
            "-t", f"{duration:.3f}", str(target),
        )
    print(f"written: {target.relative_to(ROOT) if target.is_relative_to(ROOT) else target}", flush=True)
    return target


def _ffmpeg(*args: str) -> None:
    proc = subprocess.run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *args], capture_output=True, text=True)
    if proc.returncode:
        raise RenderError(f"ffmpeg {' '.join(args[:4])} ... failed: {proc.stderr.strip()}")
