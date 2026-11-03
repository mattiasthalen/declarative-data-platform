"""The explainer film: rendered from the declarations, the hero's shapes, a score and a narrator.

    uv run film render              the cut, into out/film/
    uv run film stills 5 40 95      PNG stills at those seconds, into out/film/stills/
    uv run film models              fetch and verify the Kokoro files into .models/
"""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="film", description="Render the README's explainer film.")
    commands = parser.add_subparsers(dest="command", required=True)
    render_cmd = commands.add_parser("render", help="render the narrated, captioned cut")
    render_cmd.add_argument("--workers", type=int, default=None)
    stills_cmd = commands.add_parser("stills", help="render PNG stills at the given seconds")
    stills_cmd.add_argument("times", nargs="+", type=float)
    commands.add_parser("models", help="fetch and verify the Kokoro model files")
    args = parser.parse_args(argv)

    from film import render, voice

    try:
        if args.command == "render":
            render.cut(workers=args.workers)
        elif args.command == "stills":
            for path in render.stills(args.times, render.OUT / "stills"):
                print(path)
        else:
            voice.fetch(render.MODELS)
            print(f"verified: {', '.join(voice.MODELS)} in {render.MODELS}")
    except (render.RenderError, voice.ModelError, voice.Overrun) as error:
        print(f"film: {error}", file=sys.stderr)
        return 1
    return 0
