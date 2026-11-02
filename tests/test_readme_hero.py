"""The README's hero artwork, `assets/hero.svg`, and the README's opening (story #37: AC1-AC7,
AC11's regions, EC1-EC3, EC5; story #38: AC3, AC4, AC10's README, EC5).

The look of the drawing and how GitHub shows it are judged, not run (#37's AC8-AC10, #38's AC8 and
AC9, `tests/judged.md`). These tests hold what a command can: the README opens with the image, the
first sentence changed and nothing below it, and the SVG is self-contained, carries both its fonts
and their licence, covers its text and stays small. Story #38 moved the file from `docs/` to
`assets/`, which the artwork generator owns; its motion is held by `test_hero_motion.py`.

- ``-k hero_readme``: #37's AC1, AC2, EC1; #38's AC3. ``-k hero_svg``: #37's AC3, AC4, AC7, EC5;
  #38's AC4, EC5. ``-k hero_fonts``: #37's AC5, AC6, EC2, EC3. ``-k hero_erd_untouched``: AC2's
  unchanged rest and AC11's regions, against ``HERO_BASE`` (a commit of ``main`` from before the
  story: 92a1fa2 for #37, 4a8b54c for #38, where only line 1 may differ); skipped when it is
  unset, since ``main`` moves on after the story merges.
- ``fontTools`` is imported where it is used, so a missing ``fonttools`` (or ``brotli``, for
  WOFF2) fails these tests rather than skipping them.
"""

from __future__ import annotations

import base64
import io
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

import pytest
from harness import REPO

import erd
from erd import LAYERS

README = REPO / "README.md"
HERO = REPO / "assets" / "hero.svg"
OLD_HERO = "docs/hero.svg"
LICENCE = "SIL OPEN FONT LICENSE Version 1.1"
ALT = "Declarative Data Platform: raw data, a handful of declarations, a star schema."
SVG = "http://www.w3.org/2000/svg"
XLINK = "http://www.w3.org/1999/xlink"
UNCHANGED_FROM = "A source is declared once"
FONTS = {"Spectral": "600", "Inter": "400"}


def readme() -> str:
    return README.read_text(encoding="utf-8")


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def hero() -> ET.Element:
    assert HERO.is_file(), "assets/hero.svg does not exist"
    return ET.parse(HERO).getroot()


# --------------------------------------------------------------------------- the README's opening

OPENING = re.compile(r"<(p|div)\b([^>]*)>(.*?)</\1\s*>", re.DOTALL | re.IGNORECASE)


class _Tags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[tuple[str, dict[str, str | None]]] = []
        self.data: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_startendtag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.data.append(data)


def parse_html(fragment: str) -> _Tags:
    parser = _Tags()
    parser.feed(fragment)
    parser.close()
    return parser


def opening_block() -> re.Match:
    text = readme()
    start = len(text) - len(text.lstrip())
    block = OPENING.match(text, start)
    assert block, f"README.md's first content is not a <p> or <div> block: {text[start:start + 80]!r}"
    return block


def test_hero_readme_opens_with_image():
    """AC1, EC1: the README's first non-blank content is one centred block holding one image:
    src assets/hero.svg (#38's AC3), width 100%, alt the [8] text, which reads as the opening line
    if the image cannot load."""
    block = opening_block()
    (outer,) = parse_html(f"<{block.group(1)}{block.group(2)}>").tags
    assert (outer[1].get("align") or "").lower() == "center", (
        f"README.md's opening block is not centred (align=\"center\"): <{block.group(1)}{block.group(2)}>"
    )
    inner = parse_html(block.group(3))
    images = [attrs for tag, attrs in inner.tags if tag == "img"]
    assert len(images) == 1, f"README.md's opening block holds {len(images)} <img> tags, expected one"
    others = [tag for tag, _ in inner.tags if tag != "img"]
    assert not others, f"README.md's opening block holds more than the image: {others}"
    stray = "".join(inner.data).strip()
    assert not stray, f"README.md's opening block holds text besides the image: {stray!r}"
    (img,) = images
    assert img.get("src") == "assets/hero.svg", f"the hero's src is {img.get('src')!r}, expected 'assets/hero.svg'"
    assert img.get("width") == "100%", f"the hero's width is {img.get('width')!r}, expected '100%'"
    assert img.get("alt") == ALT, f"the hero's alt is {img.get('alt')!r}, expected {ALT!r}"


def test_hero_readme_no_old_path():
    """#38's AC3: `docs/hero.svg` no longer exists, and no tracked file names it, except the
    test modules (which may name it to hold it absent) and the ADRs (which record history)."""
    assert not (REPO / OLD_HERO).exists(), f"{OLD_HERO} still exists; the hero lives at assets/hero.svg"
    tracked = subprocess.run(
        ["git", "ls-files", "-z"], cwd=REPO, capture_output=True, check=True
    ).stdout.decode("utf-8").split("\0")
    naming = []
    for name in filter(None, tracked):
        if name.startswith("docs/adr/") or (name.startswith("tests/") and name.endswith(".py")):
            continue
        path = REPO / name
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        lines = [f"{name}:{n}" for n, line in enumerate(text.splitlines(), 1) if OLD_HERO in line]
        naming.extend(lines)
    assert not naming, f"tracked files still name {OLD_HERO}:\n" + "\n".join(naming)


def test_hero_readme_first_paragraph():
    """AC2 (lasting part): no `# declarative-data-platform` heading; the first paragraph after the
    image starts "Declarations in, structure out." and its next sentence names the Unified Star
    Schema as the serve format."""
    headings = [line for line in readme().splitlines() if line.strip() == "# declarative-data-platform"]
    assert not headings, "README.md still has the line '# declarative-data-platform'"

    block = opening_block()
    rest = readme()[block.end() :].lstrip("\r\n \t")
    paragraph = " ".join(re.split(r"\n[ \t]*\n", rest, maxsplit=1)[0].split())
    lead = "Declarations in, structure out."
    assert paragraph.startswith(lead), f"the README's first paragraph does not start {lead!r}: {paragraph[:80]!r}"
    following = paragraph[len(lead) :].strip()
    sentence = re.split(r"(?<=[.!?])\s", following, maxsplit=1)[0]
    assert "Unified Star Schema" in sentence, (
        f"the sentence after {lead!r} does not name the Unified Star Schema: {sentence!r}"
    )
    assert "serv" in sentence.lower(), f"the sentence after {lead!r} does not name the serve format: {sentence!r}"


def test_hero_erd_untouched():
    """AC2 (unchanged rest), AC11 (regions): everything from "A source is declared once" onward is
    byte for byte the base's, and so are the three erd: regions."""
    base = os.environ.get("HERO_BASE")
    if not base:
        pytest.skip("HERO_BASE is unset: set it to main's commit from before the story (92a1fa2 for #37, 4a8b54c for #38)")
    # git would read a leading "-" as an option and a ":" or space as part of the path.
    assert re.fullmatch(r"[^\s:-][^\s:]*", base), f"HERO_BASE={base!r} is not a plain revision"
    before = subprocess.run(
        ["git", "show", f"{base}:README.md"], cwd=REPO, capture_output=True, check=True
    ).stdout.decode("utf-8")
    after = README.read_bytes().decode("utf-8")
    assert before.count(UNCHANGED_FROM) == 1, f"the base README holds {UNCHANGED_FROM!r} {before.count(UNCHANGED_FROM)} times"
    assert after.count(UNCHANGED_FROM) == 1, f"README.md holds {UNCHANGED_FROM!r} {after.count(UNCHANGED_FROM)} times"
    assert after[after.index(UNCHANGED_FROM) :] == before[before.index(UNCHANGED_FROM) :], (
        f"README.md differs from {base} after {UNCHANGED_FROM!r}"
    )
    for layer in LAYERS:
        assert erd.region(after, layer).text == erd.region(before, layer).text, (
            f"README.md's erd:{layer} region differs from {base}'s"
        )
    # A base that already opens with the hero (#38's 4a8b54c) may differ on line 1 only (AC10).
    if before.lstrip().startswith("<p align=\"center\"><img"):
        assert after.splitlines(keepends=True)[1:] == before.splitlines(keepends=True)[1:], (
            f"README.md differs from {base} below line 1"
        )


# --------------------------------------------------------------------------- the SVG's form

FIXED = re.compile(r"^\s*[\d.]+\s*(px|pt|pc|cm|mm|in|Q)?\s*$")


def test_hero_svg_form():
    """AC3: the SVG parses; its root is <svg> with a viewBox and no fixed-unit width or height;
    its first child is <title> holding the [8] text."""
    root = hero()
    assert root.tag == f"{{{SVG}}}svg", f"assets/hero.svg's root is {root.tag!r}, expected an SVG <svg>"
    assert root.get("viewBox", "").split(), "assets/hero.svg's <svg> has no viewBox"
    for name in ("width", "height"):
        value = root.get(name)
        assert value is None or not FIXED.match(value), (
            f"assets/hero.svg's <svg> has a fixed {name}={value!r}; it must scale by its viewBox"
        )
    children = list(root)
    assert children, "assets/hero.svg's <svg> is empty"
    first = children[0]
    assert first.tag == f"{{{SVG}}}title", f"assets/hero.svg's first child is {first.tag!r}, expected <title>"
    assert (first.text or "").strip() == ALT, f"assets/hero.svg's <title> is {first.text!r}, expected {ALT!r}"


URL = re.compile(r"""url\(\s*(['"]?)(.*?)\1\s*\)""", re.DOTALL | re.IGNORECASE)
FORBIDDEN = {"script", "foreignObject", "image"}
ANIMATIONS = {"set", "animate"}
ANIMATED_VALUES = ("to", "from", "by", "values")


def local_reference(ref: str) -> bool:
    ref = ref.strip()
    return ref.startswith("#") or ref.lower().startswith("data:")


def styles(root: ET.Element) -> str:
    return "\n".join("".join(el.itertext()) for el in root.iter() if local(el.tag) == "style")


def test_hero_svg_fetches_nothing():
    """AC4, EC5: every href and url(...) is a #fragment or a data: URI, and so is every value a
    <set> or <animate> gives an href; no @import, no <?xml-stylesheet?>, no backslash escape in CSS
    or in any attribute but d (which could spell url); no <script>, <foreignObject>, <image> or on*
    attribute. The failure names the offending reference."""
    root = hero()
    offending: list[str] = []
    # ElementTree drops processing instructions, so the raw text is searched for this one.
    for stylesheet in re.finditer(r"<\?xml-stylesheet\b[^>]*>?", HERO.read_text(encoding="utf-8"), re.IGNORECASE):
        offending.append(f"processing instruction {stylesheet.group(0)[:80]}")
    for el in root.iter():
        tag = local(el.tag)
        if tag in FORBIDDEN:
            offending.append(f"<{tag}> element")
        if tag in ANIMATIONS and local(el.get("attributeName", "").strip()).endswith("href"):
            for name in (name for name in ANIMATED_VALUES if name in el.attrib):
                # SMIL splits only `values` on ";"; a data: URI in `to` keeps its ";base64".
                for value in el.get(name).split(";") if name == "values" else [el.get(name)]:
                    if not local_reference(value):
                        offending.append(f"<{tag}> {name}={value.strip()!r} for {el.get('attributeName')}")
        for name, value in el.attrib.items():
            attr = local(name)
            # A presentation attribute is parsed as CSS, where an escape could spell url.
            if attr != "d" and "\\" in value:
                offending.append(f"<{tag}> {attr} with a CSS escape: {value[:80]!r}")
            if attr.lower().startswith("on"):
                offending.append(f"<{tag}> event attribute {attr}={value!r}")
            if name in ("href", f"{{{XLINK}}}href") and not local_reference(value):
                offending.append(f"<{tag}> {attr}={value!r}")
            for url in URL.finditer(value):
                if not local_reference(url.group(2)):
                    offending.append(f"<{tag}> {attr} url({url.group(2)[:80]})")
    css = styles(root)
    for url in URL.finditer(css):
        if not local_reference(url.group(2)):
            offending.append(f"<style> url({url.group(2)[:80]})")
    for imported in re.finditer(r"@import[^;]*;?", css, re.IGNORECASE):
        offending.append(f"<style> {imported.group(0)[:80]}")
    for escape in re.finditer(r".{0,20}\\.{0,20}", css):
        offending.append(f"<style> CSS escape {escape.group(0)!r}")
    assert not offending, "assets/hero.svg fetches from outside:\n" + "\n".join(offending)


def test_hero_svg_carries_licence():
    """#38's AC4: the fonts' licence travels with them: the OFL text, from its title line, is in
    the file."""
    assert HERO.is_file(), "assets/hero.svg does not exist"
    text = HERO.read_text(encoding="utf-8")
    assert LICENCE in text, f"assets/hero.svg does not carry the font licence ({LICENCE!r})"
    for clause in ("PERMISSION & CONDITIONS", "TERMINATION", "DISCLAIMER"):
        assert clause in text or clause.replace("&", "&amp;") in text, (
            f"assets/hero.svg's licence text lacks its {clause!r} section: the OFL must be carried whole"
        )


def test_hero_svg_size():
    """AC7: assets/hero.svg is under 60 KB."""
    assert HERO.is_file(), "assets/hero.svg does not exist"
    size = os.path.getsize(HERO)
    assert size < 60 * 1024, f"assets/hero.svg is {size} bytes, over 60 KB ({60 * 1024})"


# --------------------------------------------------------------------------- the SVG's fonts

FACE = re.compile(r"@font-face\s*\{(.*?)\}", re.DOTALL | re.IGNORECASE)
RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")


def declaration(body: str, prop: str) -> str | None:
    found = re.search(rf"(?:^|;)\s*{prop}\s*:\s*([^;]+)", body, re.IGNORECASE)
    return found.group(1).strip() if found else None


def first_family(value: str) -> str:
    return value.split(",")[0].strip().strip("'\"")


def embedded_fonts(root: ET.Element) -> dict[str, tuple[str, bytes]]:
    """family -> (weight, the decoded font bytes), from the <style>'s @font-face rules."""
    faces = FACE.findall(styles(root))
    fonts: dict[str, tuple[str, bytes]] = {}
    for body in faces:
        family = declaration(body, "font-family")
        assert family, f"an @font-face rule names no font-family: {body[:80]!r}"
        family = first_family(family)
        assert family not in fonts, f"assets/hero.svg has more than one @font-face for {family!r}"
        weight = (declaration(body, "font-weight") or "400").strip()
        src = URL.search(body)
        assert src, f"the @font-face for {family!r} has no src url(...)"
        uri = src.group(2).strip()
        data = re.match(r"data:([^;,]*)(;[^,]*)?,(.*)", uri, re.DOTALL)
        assert data and data.group(2) and "base64" in data.group(2), (
            f"the @font-face for {family!r} is not a base64 data: URI: {uri[:60]!r}"
        )
        fonts[family] = (weight, base64.b64decode(re.sub(r"\s+", "", data.group(3)), validate=True))
    return fonts


def open_font(family: str, data: bytes):
    from fontTools.ttLib import (
        TTFont,  # imported here so a missing fonttools fails, not skips
    )

    try:
        return TTFont(io.BytesIO(data))
    except Exception as error:
        raise AssertionError(f"the embedded {family} font does not open as a font: {error!r}") from error


def class_values(root: ET.Element, prop: str) -> dict[str, str]:
    """CSS class -> the value of `prop`, from simple `.class { prop: ... }` rules in <style>."""
    css = FACE.sub("", re.sub(r"/\*.*?\*/", "", styles(root), flags=re.DOTALL))
    values: dict[str, str] = {}
    for selectors, body in RULE.findall(css):
        value = declaration(body, prop)
        if not value:
            continue
        for selector in selectors.split(","):
            for name in re.findall(r"\.([\w-]+)", selector):
                values[name] = value
    return values


def own_value(el: ET.Element, prop: str, classes: dict[str, str]) -> str | None:
    """The element's own `prop`, by SVG's cascade: an inline style beats a class rule, which
    beats the presentation attribute."""
    style = declaration(el.get("style", ""), prop)
    if style:
        return style
    for name in reversed(el.get("class", "").split()):
        if name in classes:
            return classes[name]
    return el.get(prop) or None


WEIGHTS = {"normal": "400", "bold": "700"}
NOT_DRAWN = {"title", "desc", "metadata"}


def text_runs(root: ET.Element) -> list[tuple[str, str | None, str | None]]:
    """(characters, the font-family that draws them, their font-weight) for every run of text in
    a <text>, from every descendant but <title>, <desc> and <metadata>, with both inherited down
    from ancestors and overridden by descendants."""
    families = class_values(root, "font-family")
    weights = class_values(root, "font-weight")
    runs: list[tuple[str, str | None, str | None]] = []

    def walk(el: ET.Element, family: str | None, weight: str | None, inside_text: bool) -> None:
        own = own_value(el, "font-family", families)
        family = first_family(own) if own else family
        own = own_value(el, "font-weight", weights)
        weight = WEIGHTS.get(own.strip().lower(), own.strip()) if own else weight
        inside = inside_text or local(el.tag) == "text"
        if inside and el.text:
            runs.append((el.text, family, weight))
        for child in el:
            if not (inside and local(child.tag) in NOT_DRAWN):
                walk(child, family, weight, inside)
            if inside and child.tail:
                runs.append((child.tail, family, weight))

    walk(root, None, None, False)
    return runs


def text_elements(root: ET.Element) -> list[ET.Element]:
    return [el for el in root.iter() if local(el.tag) == "text"]


def test_hero_fonts_embedded():
    """AC5: two @font-face rules, Spectral 600 and Inter 400, each a data: URI that decodes to a
    valid font; the wordmark's <text> uses Spectral and the layer line's uses Inter."""
    root = hero()
    fonts = embedded_fonts(root)
    assert sorted(fonts) == sorted(FONTS), f"assets/hero.svg embeds {sorted(fonts)}, expected exactly {sorted(FONTS)}"
    for family, weight in FONTS.items():
        assert fonts[family][0] == weight, f"the @font-face for {family} has weight {fonts[family][0]}, expected {weight}"
        font = open_font(family, fonts[family][1])
        assert font.flavor == "woff2", f"the embedded {family} font is {font.flavor or 'not compressed'}, expected woff2"
        assert "OS/2" in font and str(font["OS/2"].usWeightClass) == weight, (
            f"the embedded {family} font has weight class "
            f"{font['OS/2'].usWeightClass if 'OS/2' in font else None}, expected {weight}"
        )

    runs = text_runs(root)
    for chars, family, weight in runs:
        if family in fonts and weight is not None:
            assert weight == fonts[family][0], (
                f"the text {' '.join(chars.split())!r} is set in {family} at weight {weight}, but the embedded "
                f"{family} is weight {fonts[family][0]}: the browser would fake it"
            )
    words = " ".join(" ".join(chars.split()) for chars, _, _ in runs)
    for phrase in ("DECLARATIVE", "DATA PLATFORM"):
        assert phrase in words.upper(), f"assets/hero.svg's text does not hold the wordmark {phrase!r}"
    for chars, family, _ in runs:
        normal = " ".join(chars.split())
        if re.search(r"DECLARATIVE|DATA|PLATFORM", normal, re.IGNORECASE) and "·" not in normal:
            assert family == "Spectral", f"the wordmark text {normal!r} is set in {family!r}, expected Spectral"
    layer_lines = [
        el for el in text_elements(root)
        if all(w in " ".join("".join(el.itertext()).split()) for w in ("ingest", "conform", "integrate", "serve"))
    ]
    assert layer_lines, "assets/hero.svg has no <text> holding the layer line 'ingest · conform · integrate · serve'"
    for el in layer_lines:
        line = " ".join("".join(el.itertext()).split())
        assert line == "ingest · conform · integrate · serve", f"the layer line reads {line!r}"
    layer_runs = [
        (chars, family) for chars, family, _ in runs
        if re.search(r"ingest|conform|integrate|serve|·", chars)
    ]
    for chars, family in layer_runs:
        assert family == "Inter", f"the layer line text {chars.strip()!r} is set in {family!r}, expected Inter"


def test_hero_fonts_cover_text():
    """AC6, EC2, EC3: every character (spaces excepted) of every <text> is in the cmap of the
    embedded font that draws it; the failure names the character and the font. The middle dot is
    checked like any other."""
    root = hero()
    fonts = embedded_fonts(root)
    cmaps = {family: set(open_font(family, data).getBestCmap() or {}) for family, (_, data) in fonts.items()}
    missing: list[str] = []
    for chars, family, _ in text_runs(root):
        for char in chars:
            if char.isspace():
                continue
            if family not in cmaps:
                missing.append(f"{char!r} (U+{ord(char):04X}) is set in {family!r}, which assets/hero.svg does not embed")
            elif ord(char) not in cmaps[family]:
                missing.append(f"{char!r} (U+{ord(char):04X}) is not in the embedded {family} font")
    assert not missing, "assets/hero.svg's text falls outside its fonts:\n" + "\n".join(sorted(set(missing)))
