"""The hero's motion, `assets/hero.svg` (story #38: AC5, AC6, AC7, EC2, EC3, EC4).

The motion is CSS `@keyframes` in the SVG's own `<style>`, layered on a still drawn as plain
shapes ([5]). These tests read the file as a browser's cascade would, closely enough to hold:

- ``-k hero_motion_once`` (AC5, EC2): every animation runs once and the last one ends within
  15 s. A failure names the rule.
- ``-k hero_motion_reduced`` (AC6, EC3): under ``@media (prefers-reduced-motion: reduce)``,
  ``animation: none`` reaches every element that animates. A failure names the element and the
  rule that animates it.
- ``-k hero_motion_still`` (AC7, EC4): with every ``animation*`` declaration removed, the visible
  drawn shapes are #37's still, ``tests/fixtures/hero-still.svg`` (``docs/hero.svg`` at 4a8b54c
  without its ``@font-face`` rules and ``<metadata>``), compared as a multiset with numbers to
  0.01. Checked with motion allowed and with reduced motion requested.

What the still comparison reads:

- A drawn shape is a ``rect``, ``circle``, ``ellipse``, ``line``, ``polyline``, ``polygon``,
  ``path`` or ``text`` outside ``<defs>`` and the other never-drawn containers; a ``<use>`` is
  drawn as the shapes it references, so ids may change. Each shape is its geometry under the
  whole transform chain (a pure translation is folded into a rect's, circle's, line's or text's
  position), its fill and stroke with their opacities, width, caps and joins, its accumulated
  ``opacity``, and for text the characters and font. A ``url(#id)`` paint is compared by what
  the id holds.
- Values come from the cascade: presentation attributes, then ``<style>`` rules by specificity
  and order, then inline ``style``, ``!important`` above all. Rules in ``@media`` apply when the
  query is ``all``, ``screen`` or the ``prefers-reduced-motion`` value of the run; any other
  query is refused, since the still could not be read for it.
- A shape is hidden, and not compared, when its accumulated opacity is 0 (its own or an
  ancestor's, from an attribute or a style), when it or an ancestor has ``display: none``, or
  when its ``visibility`` is ``hidden``. A visible shape that is not one of the still's must
  exactly cover one (AC7: "hidden or exactly cover a still shape"); a still shape with no
  visible match is missing.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

import pytest
from harness import REPO

HERO = REPO / "assets" / "hero.svg"
STILL = REPO / "tests" / "fixtures" / "hero-still.svg"
XLINK = "http://www.w3.org/1999/xlink"
LONGEST = 15.0
TOLERANCE = 0.01
STILL_SHAPES = 52


def local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if isinstance(tag, str) else ""


def parse(path: Path) -> ET.Element:
    assert path.is_file(), f"{path.relative_to(REPO).as_posix()} does not exist"
    return ET.parse(path).getroot()


# --------------------------------------------------------------------------- CSS


@dataclass(frozen=True)
class Decl:
    prop: str
    value: str
    important: bool
    source: str  # the rule's selector text, or "style attribute", or "<prop> attribute"
    media: str | None = None


@dataclass
class Rule:
    selector_text: str
    decls: list[Decl]
    media: str | None
    order: int
    _selectors: list | None = None

    def selectors(self) -> list[tuple[list, tuple[int, int, int]]]:
        if self._selectors is None:
            self._selectors = [parse_selector(s) for s in split_top(self.selector_text, ",")]
        return self._selectors


def strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)


def split_top(text: str, sep: str) -> list[str]:
    """``text`` split at ``sep`` outside quotes and parentheses."""
    parts, depth, quote, start, i = [], 0, None, 0, 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\":
                i += 1
            elif c == quote:
                quote = None
        elif c in "\"'":
            quote = c
        elif c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        elif c == sep and depth == 0:
            parts.append(text[start:i])
            start = i + 1
        i += 1
    parts.append(text[start:])
    return [p.strip() for p in parts if p.strip()]


def top_blocks(css: str):
    """(prelude, body or None) for each statement or block at the top level of ``css``."""
    i, n = 0, len(css)
    while i < n:
        j, quote, depth = i, None, 0
        while j < n:
            c = css[j]
            if quote:
                if c == "\\":
                    j += 1
                elif c == quote:
                    quote = None
            elif c in "\"'":
                quote = c
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            elif depth == 0 and c in "{;":
                break
            j += 1
        prelude = css[i:j].strip()
        if j >= n:
            if prelude:
                yield prelude, None
            return
        if css[j] == ";":
            if prelude:
                yield prelude, None
            i = j + 1
            continue
        k, nest, quote = j, 0, None
        while k < n:
            c = css[k]
            if quote:
                if c == "\\":
                    k += 1
                elif c == quote:
                    quote = None
            elif c in "\"'":
                quote = c
            elif c == "{":
                nest += 1
            elif c == "}":
                nest -= 1
                if nest == 0:
                    break
            k += 1
        yield prelude, css[j + 1 : k]
        i = k + 1


def declarations(body: str, source: str, media: str | None = None) -> list[Decl]:
    out = []
    for item in split_top(body, ";"):
        if ":" not in item:
            continue
        prop, value = item.split(":", 1)
        value = value.strip()
        important = bool(re.search(r"!\s*important\s*$", value, re.IGNORECASE))
        value = re.sub(r"!\s*important\s*$", "", value, flags=re.IGNORECASE).strip()
        out.append(Decl(prop.strip().lower(), value, important, source, media))
    return out


@dataclass
class Sheet:
    rules: list[Rule] = field(default_factory=list)
    media: list[str] = field(default_factory=list)
    keyframes: list[str] = field(default_factory=list)


def read_sheet(css: str, sheet: Sheet, media: str | None = None) -> None:
    for prelude, body in top_blocks(strip_comments(css)):
        lower = prelude.lower()
        if body is None:
            continue
        if lower.startswith("@media"):
            query = " ".join(prelude[len("@media") :].split())
            sheet.media.append(query)
            read_sheet(body, sheet, query if media is None else f"{media} and {query}")
        elif re.match(r"@(-\w+-)?keyframes\b", lower):
            sheet.keyframes.append(prelude.split(None, 1)[1].strip() if " " in prelude else "")
        elif lower.startswith("@"):
            continue  # @font-face and the like draw nothing
        else:
            selector = " ".join(prelude.split())
            sheet.rules.append(Rule(selector, declarations(body, selector, media), media, len(sheet.rules)))


def stylesheet(root: ET.Element) -> Sheet:
    sheet = Sheet()
    for el in root.iter():
        if local(el.tag) == "style":
            read_sheet("".join(el.itertext()), sheet)
    return sheet


def media_applies(query: str | None, mode: str, strict: bool) -> bool:
    """Whether a rule under ``query`` applies when reduced motion is ``mode`` ("motion" or "reduced").

    A query on anything else applies when not ``strict``, so an animation under it is counted; the
    still comparison is ``strict`` and refuses it."""
    if query is None:
        return True
    applies = True
    for part in re.split(r"\s+and\s+", query.lower()):
        part = part.strip()
        if part in ("all", "screen", "only screen"):
            continue
        feature = re.fullmatch(r"\(\s*prefers-reduced-motion\s*(?::\s*([\w-]+)\s*)?\)", part)
        if feature:
            value = feature.group(1)
            if value == "reduce" or value is None:
                applies = applies and mode == "reduced"
            elif value == "no-preference":
                applies = applies and mode == "motion"
            else:
                raise AssertionError(f"@media {query}: unknown prefers-reduced-motion value {value!r}")
            continue
        if strict:
            raise AssertionError(f"@media {query}: the still cannot be read under this query")
    return applies


# --------------------------------------------------------------------------- selectors

COMPOUND = re.compile(
    r"(?P<tag>\*|[A-Za-z][\w-]*)?(?P<rest>(?:[.#][\w-]+|\[[^\]]*\]|:[\w-]+(?:\([^)]*\))?)*)"
)
PART = re.compile(r"[.#][\w-]+|\[[^\]]*\]|:[\w-]+(?:\([^)]*\))?")


def parse_selector(text: str) -> tuple[list, tuple[int, int, int]]:
    """[(combinator, compound)] left to right, and the specificity."""
    steps, i, combinator = [], 0, None
    text = text.strip()
    ids = classes = tags = 0
    while i < len(text):
        match = COMPOUND.match(text, i)
        if not match or match.end() == i:
            raise AssertionError(f"the selector {text!r} cannot be read (at {text[i:]!r})")
        compound = {"tag": match.group("tag"), "parts": PART.findall(match.group("rest"))}
        for part in compound["parts"]:
            if part.startswith("#"):
                ids += 1
            else:
                classes += 1
            if part.startswith(":"):
                name = part[1:].split("(", 1)[0]
                if name not in ("first-child", "last-child", "nth-child", "root", "nth-of-type"):
                    raise AssertionError(f"the selector {text!r} uses :{name}, which these tests cannot read")
        if compound["tag"] and compound["tag"] != "*":
            tags += 1
        steps.append((combinator, compound))
        i = match.end()
        gap = re.match(r"\s*([>+~])\s*|\s+", text[i:])
        if gap and i < len(text):
            combinator = gap.group(1) or " "
            i += gap.end()
    return steps, (ids, classes, tags)


@dataclass
class Tree:
    root: ET.Element
    parent: dict
    ids: dict

    @classmethod
    def of(cls, root: ET.Element) -> Tree:
        parent = {child: el for el in root.iter() for child in el}
        ids = {el.get("id"): el for el in root.iter() if el.get("id")}
        return cls(root, parent, ids)

    def siblings(self, el: ET.Element) -> list[ET.Element]:
        p = self.parent.get(el)
        return [el] if p is None else list(p)

    def describe(self, el: ET.Element) -> str:
        chain = []
        while el is not None:
            p = self.parent.get(el)
            tag = local(el.tag)
            if p is None:
                chain.append(tag)
            else:
                same = [s for s in p if local(s.tag) == tag]
                label = f"{tag}[{same.index(el) + 1}]" if len(same) > 1 else tag
                if el.get("id"):
                    label += f"#{el.get('id')}"
                if el.get("class"):
                    label += "." + ".".join(el.get("class").split())
                chain.append(label)
            el = p
        return " > ".join(reversed(chain))


def part_matches(part: str, el: ET.Element, tree: Tree) -> bool:
    if part.startswith("#"):
        return el.get("id") == part[1:]
    if part.startswith("."):
        return part[1:] in (el.get("class") or "").split()
    if part.startswith("["):
        inner = part[1:-1]
        found = re.fullmatch(r"\s*([\w:-]+)\s*(?:([~|^$*]?=)\s*(['\"]?)(.*?)\3)?\s*", inner)
        if not found:
            raise AssertionError(f"the attribute selector {part!r} cannot be read")
        name, op, _, want = found.groups()
        value = el.get(name)
        if value is None and name in ("href", "xlink:href"):
            value = el.get(f"{{{XLINK}}}href") or el.get("href")
        if op is None:
            return value is not None
        if value is None:
            return False
        return {
            "=": value == want,
            "~=": want in value.split(),
            "^=": value.startswith(want),
            "$=": value.endswith(want),
            "*=": want in value,
            "|=": value == want or value.startswith(want + "-"),
        }[op]
    name, _, arg = part[1:].partition("(")
    arg = arg.rstrip(")").strip()
    siblings = tree.siblings(el)
    if name == "root":
        return el is tree.root
    if name == "first-child":
        return siblings[0] is el
    if name == "last-child":
        return siblings[-1] is el
    if name in ("nth-child", "nth-of-type"):
        pool = siblings if name == "nth-child" else [s for s in siblings if s.tag == el.tag]
        if not re.fullmatch(r"\d+", arg):
            raise AssertionError(f"the selector :{name}({arg}) cannot be read; only a plain number can")
        return pool.index(el) + 1 == int(arg)
    raise AssertionError(f"the selector :{name} cannot be read")


def compound_matches(compound: dict, el: ET.Element, tree: Tree) -> bool:
    tag = compound["tag"]
    if tag and tag != "*" and tag != local(el.tag):
        return False
    return all(part_matches(part, el, tree) for part in compound["parts"])


def selector_matches(steps: list, el: ET.Element, tree: Tree) -> bool:
    def at(i: int, el: ET.Element) -> bool:
        _, compound = steps[i]
        if not compound_matches(compound, el, tree):
            return False
        if i == 0:
            return True
        link = steps[i][0]
        if link == ">":
            p = tree.parent.get(el)
            return p is not None and at(i - 1, p)
        if link == " ":
            p = tree.parent.get(el)
            while p is not None:
                if at(i - 1, p):
                    return True
                p = tree.parent.get(p)
            return False
        before = tree.siblings(el)[: tree.siblings(el).index(el)]
        if link == "+":
            return bool(before) and at(i - 1, before[-1])
        return any(at(i - 1, s) for s in before)

    return at(len(steps) - 1, el)


# --------------------------------------------------------------------------- the cascade

INHERITED = {
    "fill", "fill-opacity", "fill-rule", "stroke", "stroke-width", "stroke-opacity", "stroke-linecap",
    "stroke-linejoin", "stroke-dasharray", "stroke-dashoffset", "stroke-miterlimit", "font-family",
    "font-size", "font-weight", "font-style", "letter-spacing", "word-spacing", "text-anchor",
    "dominant-baseline", "visibility", "paint-order",
}
PRESENTATION = INHERITED | {
    "opacity", "display", "transform", "clip-path", "mask", "filter",
    "x", "y", "width", "height", "rx", "ry", "cx", "cy", "r", "d",
}
DEFAULTS = {
    "fill": "#000000", "fill-opacity": "1", "stroke": "none", "stroke-width": "1", "stroke-opacity": "1",
    "stroke-linecap": "butt", "stroke-linejoin": "miter", "stroke-dasharray": "none", "font-family": "",
    "font-size": "16", "font-weight": "400", "letter-spacing": "0", "text-anchor": "start",
    "visibility": "visible",
}


def is_animation(prop: str) -> bool:
    return re.sub(r"^-\w+-", "", prop).startswith("animation")


@dataclass
class Cascade:
    """The declared values of each element, for one reduced-motion mode."""

    tree: Tree
    sheet: Sheet
    mode: str
    strip_animation: bool
    _cache: dict = field(default_factory=dict)

    def declared(self, el: ET.Element) -> dict[str, tuple[str, Decl]]:
        key = id(el)
        if key in self._cache:
            return self._cache[key]
        ranked: list[tuple[tuple, Decl]] = []
        for name, value in el.attrib.items():
            prop = local(name)
            if prop in PRESENTATION:
                ranked.append(((0, 0, (0, 0, 0), 0, 0), Decl(prop, value.strip(), False, f"{prop} attribute")))
        for rule in self.sheet.rules:
            decls = [d for d in rule.decls if not (self.strip_animation and is_animation(d.prop))]
            if not decls or not media_applies(rule.media, self.mode, strict=self.strip_animation):
                continue
            best = None
            for steps, specificity in rule.selectors():
                if selector_matches(steps, el, self.tree) and (best is None or specificity > best):
                    best = specificity
            if best is None:
                continue
            for n, decl in enumerate(decls):
                ranked.append(((2 if decl.important else 1, 0, best, rule.order, n), decl))
        for n, decl in enumerate(declarations(el.get("style", ""), "style attribute")):
            if self.strip_animation and is_animation(decl.prop):
                continue
            ranked.append(((3 if decl.important else 1, 1, (0, 0, 0), 0, n), decl))
        ranked.sort(key=lambda pair: pair[0])
        out: dict[str, tuple[str, Decl]] = {}
        for _, decl in ranked:
            prop = re.sub(r"^-\w+-", "", decl.prop)
            if prop == "animation":
                for longhand, value in expand_animation(decl.value).items():
                    out[longhand] = (value, decl)
            else:
                out[prop] = (decl.value, decl)
        self._cache[key] = out
        return out


# --------------------------------------------------------------------------- animation values

TIME = re.compile(r"^([-+]?(?:\d+\.?\d*|\.\d+))(ms|s)$", re.IGNORECASE)
EASING = {"ease", "linear", "ease-in", "ease-out", "ease-in-out", "step-start", "step-end"}
OTHER_KEYWORDS = {
    "normal", "reverse", "alternate", "alternate-reverse", "forwards", "backwards", "both", "running", "paused",
}


def seconds(token: str) -> float | None:
    found = TIME.match(token.strip())
    if not found:
        return None
    value = float(found.group(1))
    return value / 1000 if found.group(2).lower() == "ms" else value


def expand_animation(value: str) -> dict[str, str]:
    """The `animation` shorthand as comma lists of name, duration, delay and iteration count."""
    names, durations, delays, counts = [], [], [], []
    for item in split_top(value, ","):
        tokens = split_top(item.replace("\t", " "), " ")
        if [t.lower() for t in tokens] == ["none"]:
            names.append("none")
            durations.append("0s")
            delays.append("0s")
            counts.append("1")
            continue
        times, name, count = [], None, "1"
        for token in tokens:
            lower = token.lower()
            if seconds(token) is not None:
                times.append(token)
            elif lower == "infinite" or re.fullmatch(r"[-+]?(?:\d+\.?\d*|\.\d+)", token):
                count = token
            elif lower in EASING or lower in OTHER_KEYWORDS or "(" in token or lower == "none" and name is not None:
                continue
            else:
                name = name or token
        names.append(name or "none")
        durations.append(times[0] if times else "0s")
        delays.append(times[1] if len(times) > 1 else "0s")
        counts.append(count)
    return {
        "animation-name": ", ".join(names),
        "animation-duration": ", ".join(durations),
        "animation-delay": ", ".join(delays),
        "animation-iteration-count": ", ".join(counts),
    }


def animations(declared: dict[str, tuple[str, Decl]]) -> list[tuple[str, float, float, str]]:
    """(name, delay, duration, iteration count) for each animation the element runs."""
    if "animation-name" not in declared:
        return []
    names = split_top(declared["animation-name"][0], ",")
    out = []
    for i, name in enumerate(names):
        if name.lower() == "none":
            continue

        def nth(prop: str, default: str, i: int = i) -> str:
            values = split_top(declared[prop][0], ",") if prop in declared else [default]
            return values[i % len(values)] if values else default

        duration = seconds(nth("animation-duration", "0s"))
        delay = seconds(nth("animation-delay", "0s"))
        out.append((name, delay or 0.0, duration or 0.0, nth("animation-iteration-count", "1")))
    return out


def raw_style(root: ET.Element) -> str:
    return "\n".join("".join(el.itertext()) for el in root.iter() if local(el.tag) == "style")


def hero_animations(root: ET.Element) -> tuple[Tree, Sheet, list[tuple[ET.Element, dict]]]:
    tree, sheet = Tree.of(root), stylesheet(root)
    cascade = Cascade(tree, sheet, "motion", strip_animation=False)
    animated = []
    for el in root.iter():
        declared = cascade.declared(el)
        if animations(declared):
            animated.append((el, declared))
    return tree, sheet, animated


# --------------------------------------------------------------------------- AC5, EC2


SMIL = {"animate", "animateTransform", "animateMotion", "animateColor", "set"}


def count_is_one(count: str) -> bool:
    try:
        return float(count) == 1.0
    except ValueError:
        return False


def test_hero_motion_once():
    """AC5, EC2: no `infinite` and no iteration count but 1, in any rule, inline style or SMIL
    element; the hero animates something; and the last animation ends (delay + duration times
    count) within 15 s. A failure names the rule."""
    root = parse(HERO)
    sheet = stylesheet(root)
    looping: list[str] = []
    for rule in sheet.rules:
        for decl in rule.decls:
            if not is_animation(decl.prop):
                continue
            if "infinite" in decl.value.lower():
                looping.append(f"{rule.selector_text} {{ {decl.prop}: {decl.value} }}")
                continue
            prop = re.sub(r"^-\w+-", "", decl.prop)
            if prop == "animation":
                counts = split_top(expand_animation(decl.value)["animation-iteration-count"], ",")
            elif prop == "animation-iteration-count":
                counts = split_top(decl.value, ",")
            else:
                continue
            for count in counts:
                if not count_is_one(count):
                    looping.append(f"{rule.selector_text} {{ {decl.prop}: {decl.value} }}")
                    break
    tree = Tree.of(root)
    for el in root.iter():
        for decl in declarations(el.get("style", ""), "style attribute"):
            if is_animation(decl.prop) and (
                "infinite" in decl.value.lower()
                or any(
                    not count_is_one(c)
                    for c in split_top(
                        expand_animation(decl.value)["animation-iteration-count"]
                        if re.sub(r"^-\w+-", "", decl.prop) == "animation"
                        else decl.value if decl.prop.endswith("iteration-count") else "1",
                        ",",
                    )
                )
            ):
                looping.append(f'{tree.describe(el)} style="{decl.prop}: {decl.value}"')
        if local(el.tag) in SMIL:
            repeat = el.get("repeatCount")
            if el.get("repeatDur") or (repeat is not None and not count_is_one(repeat)):
                looping.append(f"{tree.describe(el)} repeatCount={repeat!r} repeatDur={el.get('repeatDur')!r}")
    keyframes_infinite = re.findall(r"[^{};]*infinite[^{};]*", strip_comments(raw_style(root)), re.IGNORECASE)
    for found in keyframes_infinite:
        text = " ".join(found.split())
        if not any(text in entry for entry in looping):
            looping.append(f"<style> ... {text} ...")
    assert not looping, "assets/hero.svg has animations that run more than once:\n" + "\n".join(looping)

    _, _, animated = hero_animations(root)
    assert animated, "assets/hero.svg animates nothing: no element has a CSS animation"
    ends = []
    for el, declared in animated:
        for name, delay, duration, count in animations(declared):
            source = declared["animation-name"][1].source
            ends.append((delay + duration * float(count), f"{tree.describe(el)}: {name} (from {source})"))
    longest, which = max(ends)
    assert longest <= LONGEST, f"assets/hero.svg's last animation ends at {longest:g} s, after {LONGEST:g} s: {which}"


# --------------------------------------------------------------------------- AC6, EC3

REDUCED_QUERY = re.compile(r"\(\s*prefers-reduced-motion\s*:\s*reduce\s*\)", re.IGNORECASE)


def test_hero_motion_reduced():
    """AC6, EC3: the style holds `@media (prefers-reduced-motion: reduce)`, and in it a rule's
    `animation: none` is what every animated element ends with when reduced motion is
    requested. A failure names each element left moving and the rule that moves it."""
    root = parse(HERO)
    tree, sheet, animated = hero_animations(root)
    assert any(REDUCED_QUERY.search(q) for q in sheet.media), (
        f"assets/hero.svg's style has no @media (prefers-reduced-motion: reduce); its @media queries: {sheet.media}"
    )
    assert animated, "assets/hero.svg animates nothing: no element has a CSS animation"
    reduced = Cascade(tree, sheet, "reduced", strip_animation=False)
    moving: list[str] = []
    for el, before in animated:
        declared = reduced.declared(el)
        what = f"{tree.describe(el)} (animated by {before['animation-name'][1].source})"
        if animations(declared):
            moving.append(f"{what} still runs {declared['animation-name'][0]!r} from {declared['animation-name'][1].source}")
            continue
        _, decl = declared["animation-name"]
        stopped_by = re.sub(r"^-\w+-", "", decl.prop) == "animation" and decl.value.strip().lower() == "none"
        if not (stopped_by and decl.media and REDUCED_QUERY.search(decl.media)):
            moving.append(
                f"{what} is stopped by {decl.source} {{ {decl.prop}: {decl.value} }}, "
                "not by `animation: none` in the reduced-motion rule"
            )
    assert not moving, "the reduced-motion rule leaves elements of assets/hero.svg moving:\n" + "\n".join(moving)


# --------------------------------------------------------------------------- AC7, EC4: the still

NOT_DRAWN = {
    "defs", "symbol", "clipPath", "mask", "pattern", "marker", "linearGradient", "radialGradient", "filter",
    "style", "title", "desc", "metadata", "script", "font-face", "switch",
} | SMIL
DRAWN = {"rect", "circle", "ellipse", "line", "polyline", "polygon", "path", "text"}
NUMBER = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def multiply(m: tuple, n: tuple) -> tuple:
    a, b, c, d, e, f = m
    a2, b2, c2, d2, e2, f2 = n
    return (
        a * a2 + c * b2, b * a2 + d * b2,
        a * c2 + c * d2, b * c2 + d * d2,
        a * e2 + c * f2 + e, b * e2 + d * f2 + f,
    )


def angle(token: str) -> float:
    value = float(NUMBER.match(token).group(0))
    if token.endswith("rad"):
        return value
    if token.endswith("turn"):
        return value * 2 * math.pi
    return math.radians(value)


def transform_matrix(value: str | None) -> tuple:
    matrix = IDENTITY
    if not value or value.strip().lower() == "none":
        return matrix
    for name, args in re.findall(r"([\w-]+)\s*\(([^)]*)\)", value):
        raw = [a for a in re.split(r"[\s,]+", args.strip()) if a]
        nums = [float(NUMBER.match(a).group(0)) for a in raw]
        name = name.lower()
        if name == "matrix":
            step = tuple(nums)
        elif name == "translate":
            step = (1, 0, 0, 1, nums[0], nums[1] if len(nums) > 1 else 0)
        elif name == "translatex":
            step = (1, 0, 0, 1, nums[0], 0)
        elif name == "translatey":
            step = (1, 0, 0, 1, 0, nums[0])
        elif name == "scale":
            step = (nums[0], 0, 0, nums[1] if len(nums) > 1 else nums[0], 0, 0)
        elif name == "scalex":
            step = (nums[0], 0, 0, 1, 0, 0)
        elif name == "scaley":
            step = (1, 0, 0, nums[0], 0, 0)
        elif name == "rotate":
            t = angle(raw[0]) if raw[0][-1].isalpha() else math.radians(nums[0])
            rot = (math.cos(t), math.sin(t), -math.sin(t), math.cos(t), 0, 0)
            if len(nums) == 3:
                step = multiply(multiply((1, 0, 0, 1, nums[1], nums[2]), rot), (1, 0, 0, 1, -nums[1], -nums[2]))
            else:
                step = rot
        elif name == "skewx":
            step = (1, 0, math.tan(angle(raw[0]) if raw[0][-1].isalpha() else math.radians(nums[0])), 1, 0, 0)
        elif name == "skewy":
            step = (1, math.tan(angle(raw[0]) if raw[0][-1].isalpha() else math.radians(nums[0])), 0, 1, 0, 0)
        else:
            raise AssertionError(f"the transform {value!r} cannot be read ({name})")
        matrix = multiply(matrix, step)
    return matrix


def number(value: str | None, default: float = 0.0) -> float:
    if value is None:
        return default
    found = NUMBER.search(value)
    if not found:
        return default
    n = float(found.group(0))
    return n / 100 if value.strip().endswith("%") else n


COLOURS = {"white": "#ffffff", "black": "#000000", "transparent": "none", "none": "none"}


def paint(value: str, tree: Tree) -> str:
    value = value.strip()
    ref = re.match(r"url\(\s*['\"]?#([^'\")]+)['\"]?\s*\)", value)
    if ref:
        target = tree.ids.get(ref.group(1))
        return "url:" + (canonical(target, tree) if target is not None else f"missing #{ref.group(1)}")
    lower = value.lower()
    if lower in COLOURS:
        return COLOURS[lower]
    short = re.fullmatch(r"#([0-9a-f])([0-9a-f])([0-9a-f])", lower)
    if short:
        return "#" + "".join(ch * 2 for ch in short.groups())
    rgb = re.fullmatch(r"rgba?\(([^)]*)\)", lower)
    if rgb:
        parts = [p for p in re.split(r"[\s,/]+", rgb.group(1)) if p]
        channels = [round(number(p) * 255) if p.endswith("%") else round(float(p)) for p in parts[:3]]
        return "#" + "".join(f"{c:02x}" for c in channels)
    return lower


def canonical(el: ET.Element, tree: Tree, depth: int = 0) -> str:
    """What a referenced element (a gradient) holds, without its id."""
    attrs = []
    for name, value in sorted(el.attrib.items()):
        name = local(name)
        if name == "id":
            continue
        if name == "href" and value.startswith("#") and depth < 5 and value[1:] in tree.ids:
            value = canonical(tree.ids[value[1:]], tree, depth + 1)
        else:
            value = NUMBER.sub(lambda m: f"{float(m.group(0)):g}", value.strip().lower())
        attrs.append(f"{name}={value}")
    children = ",".join(canonical(child, tree, depth + 1) for child in el)
    return f"{local(el.tag)}[{' '.join(attrs)}]({children})"


def font_family(value: str) -> str:
    return ",".join(part.strip().strip("'\"").lower() for part in value.split(","))


def path_data(value: str) -> tuple:
    value = value.strip()
    inner = re.fullmatch(r"path\(\s*(['\"])(.*)\1\s*\)", value, re.DOTALL)
    if inner:
        value = inner.group(2)
    return tuple(
        float(tok) if tok[0] not in "MmZzLlHhVvCcSsQqTtAa" else tok
        for tok in re.findall(r"[MmZzLlHhVvCcSsQqTtAa]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?", value)
    )


@dataclass
class Shape:
    tag: str
    where: str
    values: dict

    def describe(self) -> str:
        def show(v):
            if isinstance(v, float):
                return f"{v:g}"
            if isinstance(v, tuple):
                return " ".join(show(x) for x in v)
            return str(v) if len(str(v)) < 60 else str(v)[:57] + "..."

        body = " ".join(f"{k}={show(v)}" for k, v in self.values.items())
        return f"<{self.tag} {body}> at {self.where}"


def close(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float):
        return abs(a - b) <= TOLERANCE + 1e-9
    if isinstance(a, tuple) and isinstance(b, tuple):
        return len(a) == len(b) and all(close(x, y) for x, y in zip(a, b))
    return a == b


def same(a: Shape, b: Shape) -> bool:
    return a.tag == b.tag and a.values.keys() == b.values.keys() and all(
        close(a.values[k], b.values[k]) for k in a.values
    )


GEOMETRY = {
    "rect": ("x", "y", "width", "height", "rx", "ry"),
    "circle": ("cx", "cy", "r"),
    "ellipse": ("cx", "cy", "rx", "ry"),
    "line": ("x1", "y1", "x2", "y2"),
    "text": ("x", "y"),
}
POSITIONS = {"rect": (("x", "y"),), "circle": (("cx", "cy"),), "ellipse": (("cx", "cy"),),
             "line": (("x1", "y1"), ("x2", "y2")), "text": (("x", "y"),)}


def shape_of(el: ET.Element, tag: str, style: dict[str, str], declared: dict, matrix: tuple,
             opacity: float, tree: Tree, where: str) -> Shape:
    values: dict = {}

    def geometry(prop: str) -> str | None:
        if tag in ("line", "text", "polyline", "polygon"):
            return el.get(prop)
        return declared[prop][0] if prop in declared else None

    if tag in GEOMETRY:
        for prop in GEOMETRY[tag]:
            values[prop] = number(geometry(prop))
        if tag in ("rect", "ellipse"):
            rx, ry = geometry("rx"), geometry("ry")
            values["rx"] = number(rx if rx not in (None, "auto") else ry)
            values["ry"] = number(ry if ry not in (None, "auto") else rx)
    elif tag == "path":
        values["d"] = path_data(geometry("d") or "")
    else:
        values["points"] = tuple(float(n) for n in NUMBER.findall(el.get("points", "")))

    a, b, c, d, e, f = matrix
    if tag in POSITIONS and close((a, b, c, d), (1.0, 0.0, 0.0, 1.0)):
        for x, y in POSITIONS[tag]:
            values[x] += e
            values[y] += f
    else:
        values["transform"] = tuple(float(v) for v in matrix)

    if tag == "text":
        hidden = {"title", "desc", "metadata"}

        def text(node: ET.Element) -> str:
            out = node.text or ""
            for child in node:
                if local(child.tag) not in hidden:
                    out += text(child)
                out += child.tail or ""
            return out

        values["text"] = " ".join(text(el).split())
        values["font-family"] = font_family(style["font-family"])
        values["font-size"] = number(style["font-size"], 16.0)
        weight = style["font-weight"].strip().lower()
        values["font-weight"] = {"normal": "400", "bold": "700"}.get(weight, weight)
        values["letter-spacing"] = 0.0 if style["letter-spacing"] == "normal" else number(style["letter-spacing"])
        values["text-anchor"] = style["text-anchor"]

    fill = paint(style["fill"], tree)
    if tag != "line":
        values["fill"] = fill
        if fill != "none":
            values["fill-opacity"] = number(style["fill-opacity"], 1.0)
    stroke = paint(style["stroke"], tree)
    values["stroke"] = stroke
    if stroke != "none":
        values["stroke-width"] = number(style["stroke-width"], 1.0)
        values["stroke-opacity"] = number(style["stroke-opacity"], 1.0)
        values["stroke-linecap"] = style["stroke-linecap"]
        values["stroke-linejoin"] = style["stroke-linejoin"]
        values["stroke-dasharray"] = style["stroke-dasharray"]
    values["opacity"] = opacity
    for prop in ("clip-path", "mask", "filter"):
        if prop in declared and declared[prop][0].strip().lower() != "none":
            values[prop] = paint(declared[prop][0], tree)
    return Shape(tag, where, values)


def drawn_shapes(path: Path, mode: str) -> list[Shape]:
    """The visible drawn shapes of the SVG at ``path``, every animation declaration removed."""
    root = parse(path)
    tree = Tree.of(root)
    cascade = Cascade(tree, stylesheet(root), mode, strip_animation=True)
    shapes: list[Shape] = []

    def walk(el: ET.Element, inherited: dict[str, str], matrix: tuple, opacity: float, where: str, depth: int):
        tag = local(el.tag)
        if tag in NOT_DRAWN or depth > 20:
            return
        declared = cascade.declared(el)
        if declared.get("display", ("",))[0].strip().lower() == "none":
            return
        style = dict(inherited)
        for prop in INHERITED:
            if prop in declared:
                value = declared[prop][0]
                if value.strip().lower() != "inherit":
                    style[prop] = value
        opacity *= max(0.0, min(1.0, number(declared["opacity"][0], 1.0))) if "opacity" in declared else 1.0
        matrix = multiply(matrix, transform_matrix(declared["transform"][0] if "transform" in declared else None))
        here = f"{where} > {tree.describe(el).rsplit(' > ', 1)[-1]}" if where else tree.describe(el)
        if tag == "use":
            href = el.get("href") or el.get(f"{{{XLINK}}}href") or ""
            target = tree.ids.get(href[1:]) if href.startswith("#") else None
            if target is not None:
                moved = multiply(matrix, (1, 0, 0, 1, number(el.get("x")), number(el.get("y"))))
                walk_target(target, style, moved, opacity, here, depth + 1)
            return
        if tag in DRAWN:
            if opacity > 0 and style["visibility"].strip().lower() not in ("hidden", "collapse"):
                shapes.append(shape_of(el, tag, style, declared, matrix, opacity, tree, here))
            if tag == "text":
                return
        for child in el:
            walk(child, style, matrix, opacity, here, depth + 1)

    def walk_target(target: ET.Element, style: dict, matrix: tuple, opacity: float, where: str, depth: int):
        # A <use> draws its target even when the target sits in <defs> or is a <symbol>.
        if local(target.tag) in ("symbol", "defs"):
            for child in target:
                walk(child, style, matrix, opacity, where, depth + 1)
        else:
            walk(target, style, matrix, opacity, where, depth)

    walk(root, dict(DEFAULTS), IDENTITY, 1.0, "", 0)
    return shapes


def compare(still: list[Shape], hero: list[Shape]) -> tuple[list[Shape], list[Shape]]:
    """(still shapes with no visible match, visible shapes that cover no still shape)."""
    unmatched = list(hero)
    missing = []
    for shape in still:
        match = next((i for i, other in enumerate(unmatched) if same(shape, other)), None)
        if match is None:
            missing.append(shape)
        else:
            unmatched.pop(match)
    extra = [shape for shape in unmatched if not any(same(shape, s) for s in still)]
    return missing, extra


def test_hero_motion_still_fixture_reads():
    """AC7: the fixture is #37's still as these tests read it: 52 visible shapes (2 backgrounds,
    3 texts, 9 raw tiles, 3 pages of 2 paths, 8 page lines, 8 spokes, 8 ring tiles, the centre
    tile and its dot, 6 trail dots), and it matches itself in both modes."""
    for mode in ("motion", "reduced"):
        shapes = drawn_shapes(STILL, mode)
        assert len(shapes) == STILL_SHAPES, (
            f"tests/fixtures/hero-still.svg reads as {len(shapes)} shapes, expected {STILL_SHAPES}:\n"
            + "\n".join(s.describe() for s in shapes)
        )
        assert compare(shapes, drawn_shapes(STILL, mode)) == ([], [])
    tags = sorted(s.tag for s in drawn_shapes(STILL, "motion"))
    assert tags.count("path") == 6 and tags.count("text") == 3 and tags.count("circle") == 7, tags


@pytest.mark.parametrize("mode", ["motion", "reduced"])
def test_hero_motion_still(mode):
    """AC7, EC4: with every animation declaration removed (and reduced motion off or on), each
    visible drawn shape of assets/hero.svg is one of the still's, with its geometry, fill, stroke
    and opacity to 0.01, and every still shape is drawn. The failure names each missing and each
    extra shape."""
    still = drawn_shapes(STILL, mode)
    hero = drawn_shapes(HERO, mode)
    missing, extra = compare(still, hero)
    lines = [f"missing: {s.describe()}" for s in missing] + [f"extra:   {s.describe()}" for s in extra]
    assert not lines, (
        f"with animation removed (reduced motion {'on' if mode == 'reduced' else 'off'}), assets/hero.svg "
        f"does not draw #37's still ({len(missing)} missing, {len(extra)} extra):\n" + "\n".join(lines)
    )
