"""The README links the explainer under the hero (story #39: AC12).

The line under the hero is the only link to the film: text "Watch the two-minute explainer, with
sound" (the link says the video has sound, [6]), target the asset's fixed download URL on the
`explainer` release ([5]). It may be Markdown or an HTML paragraph; no poster image.

- ``-k readme_explainer_link``: AC12.
"""

from __future__ import annotations

import re
from html import unescape

from harness import REPO

README = REPO / "README.md"
TEXT = "Watch the two-minute explainer, with sound"
URL = "https://github.com/mattiasthalen/declarative-data-platform/releases/download/explainer/declarative-data-platform-explainer.mp4"
MARKDOWN = re.compile(r"\[([^\]]+)\]\(\s*<?([^)\s>]+)>?\s*\)")
HTML = re.compile(r"<a\b[^>]*\bhref\s*=\s*[\"']([^\"']+)[\"'][^>]*>(.*?)</a\s*>", re.IGNORECASE | re.DOTALL)
TAG = re.compile(r"<[^>]+>")


def test_readme_explainer_link():
    """AC12: the first non-blank line after the hero is one link, reading exactly "Watch the
    two-minute explainer, with sound" and pointing at the asset's download URL, and nothing else;
    no other README line carries that text."""
    lines = README.read_text(encoding="utf-8").splitlines()
    content = [(i, line) for i, line in enumerate(lines) if line.strip()]
    assert content and 'src="assets/hero.svg"' in content[0][1], "README.md does not open with the hero"
    assert len(content) > 1, "README.md has nothing after the hero"
    line = content[1][1].strip()

    links = [(m.group(1), m.group(2)) for m in MARKDOWN.finditer(line)]
    links += [(m.group(2), m.group(1)) for m in HTML.finditer(line)]
    assert len(links) == 1, f"the line under the hero holds {len(links)} links, expected one: {line!r}"
    ((text, url),) = links
    assert " ".join(unescape(TAG.sub("", text)).split()) == TEXT, f"the link reads {text!r}, expected {TEXT!r}"
    assert unescape(url) == URL, f"the link points at {url!r}, expected {URL!r}"
    assert "<img" not in line.lower() and "![" not in line, f"the link line holds an image: {line!r}"

    shown = " ".join(unescape(TAG.sub("", MARKDOWN.sub(r"\1", line))).split())
    assert shown == TEXT, f"the line under the hero reads {shown!r}, expected only {TEXT!r}"
    others = [i + 1 for i, other in enumerate(lines) if TEXT in other and i != content[1][0]]
    assert not others, f"README.md carries the explainer link text again on lines {others}"
