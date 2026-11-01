"""The root README's generated ERD regions: placement, drift, region-only writes, broken markers
(story #3: AC1, AC5-AC10, EC1-EC7, EC11, EC12).

The interface these tests assume (markers, region shape, report lines) is set out in ``erd.py``.
Every test but those reading the repo itself runs the generators as subprocesses in one shared
copy of the repo, without a dbt build; the copy's declarations, models and README are put back
before every test.
"""

from __future__ import annotations

import os
import re
import signal
import subprocess
from itertools import pairwise

import erd
import pytest
from erd import EDIT_MARK, LAYERS, README
from harness import REPO, require


@pytest.fixture(scope="module")
def shared(make_workspace, tmp_path_factory):
    ws = make_workspace("erd-readme")
    require(ws.generate())
    return erd.keep(ws, tmp_path_factory.mktemp("erd-readme-pristine"))


@pytest.fixture
def ws(shared):
    return erd.restore(*shared)


def committed() -> str:
    return (REPO / README).read_text(encoding="utf-8")


# --------------------------------------------------------------------------- AC1


def test_erd_committed():
    """AC1: under "The model", exactly one region each for conform, integrate and serve, in that
    order, each one fenced mermaid block starting erDiagram."""
    text = committed()
    heading = re.search(r"^(#+)[ \t]+The model[ \t]*$", text, re.MULTILINE)
    assert heading, "README.md has no heading \"The model\""
    level = len(heading.group(1))
    following = re.compile(rf"^#{{1,{level}}}[ \t]", re.MULTILINE)
    after = following.search(text, heading.end())
    section_end = after.start() if after else len(text)

    regions = [erd.region(text, layer) for layer in LAYERS]
    for layer, found in zip(LAYERS, regions, strict=True):
        assert heading.end() <= found.begin.start() and found.end.end() <= section_end, (
            f"the erd:{layer} region is not under \"The model\""
        )
        stripped = found.text.strip()
        assert stripped.startswith("```") and stripped.endswith("```"), (
            f"the erd:{layer} region holds more than its fenced mermaid block:\n{found.text}"
        )
        erd.diagram(found.text)
    for earlier, later in pairwise(regions):
        assert earlier.end.end() <= later.begin.start(), "regions out of order: conform, integrate, serve expected"


# --------------------------------------------------------------------------- AC10


STYLING = [
    (re.compile(r"^\s*classDef\b", re.MULTILINE), "classDef"),
    (re.compile(r"^\s*style\s", re.MULTILINE), "style"),
    (re.compile(r"^\s*class\s", re.MULTILINE), "class "),
    (re.compile(r":::"), ":::"),
    (re.compile(r"%%\{\s*init"), "%%{init"),
]


def test_erd_unstyled():
    """AC10: no diagram holds classDef, style, class or an %%{init directive."""
    text = committed()
    for layer in LAYERS:
        found = erd.region(text, layer).text
        for pattern, what in STYLING:
            assert not pattern.search(found), f"the erd:{layer} diagram holds {what}:\n{found}"


# --------------------------------------------------------------------------- EC11


def test_erd_gitattributes():
    """EC11: .gitattributes marks README.md -text, so no checkout turns it into CRLF."""
    shown = subprocess.run(
        ["git", "check-attr", "text", README], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.strip()
    assert shown == f"{README}: text: unset", shown


# --------------------------------------------------------------------------- AC5, AC6


def test_erd_stale_model(ws):
    """AC5: an attribute added to model.yaml without a regenerate: integrate and serve --check exit 1
    with `changed README.md` and a diff showing the new row; task check fails."""
    name, column = erd.add_weight_attribute(ws)
    for layer, row in (("integrate", name), ("serve", column)):
        step = erd.check(ws, layer)
        assert step.returncode == 1, step.shown()
        assert ("changed", README) in erd.statuses(step), step.shown()
        diff = erd.added(erd.entry(step, README))
        assert any(row in line for line in diff), f"{layer}: the README diff does not add {row}:\n{step.shown()}"
    assert erd.task(ws, "check").returncode != 0, "task check passed with a stale README"


def test_erd_stale_contract(ws):
    """AC6: a contract added without a regenerate: conform --check exits 1 naming README.md."""
    erd.add_contract(ws, "customers")
    step = erd.check(ws, "conform")
    assert step.returncode == 1, step.shown()
    assert ("changed", README) in erd.statuses(step), step.shown()


# --------------------------------------------------------------------------- AC7


def _change_for(ws, layer: str) -> str:
    """Change ``layer``'s declarations so its diagram must change; returns a name the new diagram shows."""
    if layer == "conform":
        return erd.add_contract(ws, "customers")
    name, column = erd.add_weight_attribute(ws)
    return name if layer == "integrate" else column


@pytest.mark.parametrize("layer", LAYERS)
def test_erd_region_only(ws, layer):
    """AC7: generate rewrites only the text between its own markers: every byte before its begin
    marker and after its end marker, the other layers' regions included, is unchanged."""
    shown = _change_for(ws, layer)
    before = erd.readme(ws)
    old = erd.region(before, layer)
    erd.ok(erd.generate(ws, layer))
    after = erd.readme(ws)
    new = erd.region(after, layer)
    assert shown in new.text and shown not in old.text, f"the erd:{layer} region was not regenerated:\n{new.text}"
    assert after[: new.begin.start()] == before[: old.begin.start()], f"{layer} changed the README before its region"
    assert after[new.end.end() :] == before[old.end.end() :], f"{layer} changed the README after its region"


# --------------------------------------------------------------------------- AC8


@pytest.mark.parametrize("layer", LAYERS)
def test_erd_hand_edit_inside_region(ws, layer):
    """AC8: a hand edit inside a region is drift: --check exits 1 naming README.md; generate restores it."""
    path = ws.root / README
    pristine = path.read_bytes()
    text = pristine.decode("utf-8")
    inside = erd.region(text, layer)
    path.write_text(text[: inside.begin.end()] + f"\n{EDIT_MARK}" + text[inside.begin.end() :], encoding="utf-8")
    step = erd.check(ws, layer)
    assert step.returncode == 1, step.shown()
    assert ("changed", README) in erd.statuses(step), step.shown()
    erd.ok(erd.generate(ws, layer))
    assert path.read_bytes() == pristine, f"{layer} generate did not restore its region"


def test_erd_hand_edit_outside_regions(ws):
    """AC8: a hand edit outside every region is not drift: every --check exits 0, and generate keeps it."""
    path = ws.root / README
    edited = f"<!-- {EDIT_MARK} -->\n" + path.read_text(encoding="utf-8") + f"\n{EDIT_MARK}\n"
    path.write_text(edited, encoding="utf-8")
    for layer in LAYERS:
        erd.region(edited, layer)
    for layer in LAYERS:
        step = erd.check(ws, layer)
        assert step.returncode == 0, step.shown()
    for layer in LAYERS:
        erd.ok(erd.generate(ws, layer))
        assert path.read_text(encoding="utf-8") == edited, f"{layer} generate changed the README outside its region"


# --------------------------------------------------------------------------- AC9


def test_erd_idempotent(ws):
    """AC9: task generate twice leaves the README byte for byte as after the first run."""
    erd.add_contract(ws, "customers")
    erd.add_weight_attribute(ws)
    path = ws.root / README
    before = path.read_bytes()
    erd.ok(erd.task(ws, "generate"))
    first = path.read_bytes()
    for layer in LAYERS:
        erd.region(first.decode("utf-8"), layer)
    assert first != before, "task generate did not regenerate the README's regions after the declarations changed"
    erd.ok(erd.task(ws, "generate"))
    assert path.read_bytes() == first, "a second task generate changed the README"


# --------------------------------------------------------------------------- EC12


@pytest.mark.parametrize("layer", LAYERS)
def test_erd_crlf(ws, layer):
    """EC12: a README with CRLF line endings: --check reports `changed README.md`; generate writes LF
    inside its region and leaves every byte outside it as it was."""
    path = ws.root / README
    pristine = path.read_bytes().decode("utf-8")
    crlf = pristine.replace("\n", "\r\n")
    path.write_bytes(crlf.encode("utf-8"))
    step = erd.check(ws, layer)
    assert step.returncode == 1, step.shown()
    assert ("changed", README) in erd.statuses(step), step.shown()

    erd.ok(erd.generate(ws, layer))
    after = path.read_bytes().decode("utf-8")
    old, new = erd.region(crlf, layer), erd.region(after, layer)
    assert after[: new.begin.start()] == crlf[: old.begin.start()], f"{layer} changed the README before its region"
    assert after[new.end.end() :] == crlf[old.end.end() :], f"{layer} changed the README after its region"
    assert "\r" not in new.text, f"{layer} wrote a carriage return inside its region: {new.text!r}"
    assert new.text == erd.region(pristine, layer).text, f"{layer} wrote a different region from the LF README's"


# --------------------------------------------------------------------------- EC1-EC7


def _remove(text: str, match: re.Match) -> str:
    return text[: match.start()] + text[match.end() :]


def _break(text: str, case: str, layer: str) -> str:
    begin, end = erd.markers(text, layer, "begin"), erd.markers(text, layer, "end")
    assert len(begin) == 1 and len(end) == 1, f"the committed README has no well-formed erd:{layer} region"
    begin, end = begin[0], end[0]
    if case == "begin_missing":
        return _remove(text, begin)
    if case == "end_missing":
        return _remove(text, end)
    if case == "begin_twice":
        return text[: begin.start()] + begin.group(0) + "\n" + text[begin.start() :]
    if case == "end_before_begin":
        return text[: begin.start()] + end.group(0) + text[begin.end() : end.start()] + begin.group(0) + text[end.end() :]
    if case == "contains_other":
        other = erd.region(text, contained(layer))
        moved = text[other.begin.start() : other.end.end()]
        rest = text[: other.begin.start()] + text[other.end.end() :]
        host = erd.region(rest, layer)
        return rest[: host.begin.end()] + "\n" + moved + "\n" + rest[host.begin.end() :]
    raise AssertionError(case)


def contained(layer: str) -> str:
    """The layer whose region EC6 moves into ``layer``'s: the next one, cyclically."""
    return LAYERS[(LAYERS.index(layer) + 1) % len(LAYERS)]


def _problem(case: str, layer: str) -> re.Pattern:
    """The stderr line [S4] fixes for ``case``: `README.md: <marker> <problem>`."""
    line = {
        "readme_missing": r"README\.md\b",
        "begin_missing": rf"README\.md:\s.*\berd:{layer}\s+begin\b.*\bmissing\b",
        "end_missing": rf"README\.md:\s.*\berd:{layer}\s+end\b.*\bmissing\b",
        "begin_twice": rf"README\.md:\s.*\berd:{layer}\s+begin\b.*\bappears 2 times\b",
        "end_before_begin": rf"README\.md:\s.*\berd:{layer}\b.*\bends before it begins\b",
        "contains_other": rf"README\.md:\s.*\berd:({layer}|{contained(layer)})\b",
    }[case]
    return re.compile(line)


CASES = ["readme_missing", "begin_missing", "end_missing", "begin_twice", "end_before_begin", "contains_other"]


@pytest.mark.parametrize("layer", LAYERS)
@pytest.mark.parametrize("case", CASES)
def test_erd_broken(ws, case, layer):
    """EC1-EC7: a missing README (EC1), a begin or end marker missing (EC2, EC3), a begin marker twice
    (EC4), an end before its begin (EC5), a region holding another layer's region (EC6): generate and
    --check both exit 2 with `README.md: <marker> <problem>` on stderr and write nothing, a planted
    stale model file included; task check reports the layer `fail` and still checks the others
    (EC7); the layers the break does not touch still generate."""
    path = ws.root / README
    if case == "readme_missing":
        path.unlink()
        untouched = []
    else:
        path.write_text(_break(path.read_text(encoding="utf-8"), case, layer), encoding="utf-8")
        skip = {layer, contained(layer)} if case == "contains_other" else {layer}
        untouched = [other for other in LAYERS if other not in skip]

    stale = erd.owned_files(ws, layer)[0]
    stale.write_text(stale.read_text(encoding="utf-8") + f"\n-- {EDIT_MARK}\n", encoding="utf-8")
    planted = stale.read_bytes()
    before = ws.tree()
    problem = _problem(case, layer)

    for step in (erd.generate(ws, layer), erd.check(ws, layer)):
        assert step.returncode == 2, step.shown()
        assert "Traceback" not in step.output, step.shown()
        assert any(problem.search(line) for line in step.stderr.splitlines()), (
            f"no stderr line matching {problem.pattern!r}:\n{step.shown()}"
        )
        assert stale.read_bytes() == planted, f"{' '.join(step.args)} rewrote the planted stale model"
        assert ws.tree() == before, f"{' '.join(step.args)} wrote to the tree"

    checked = erd.task(ws, "check")
    assert checked.returncode != 0, checked.shown()
    verdicts = erd.verdicts(checked)
    assert verdicts.get(layer) == "fail", f"task check did not report {layer} fail: {verdicts}\n{checked.shown()}"
    for other in untouched:
        assert verdicts.get(other) == "pass", f"task check did not check {other} past the broken {layer}: {verdicts}"
    assert ws.tree() == before, "task check wrote to the tree"

    for other in untouched:
        erd.ok(erd.generate(ws, other))


# --------------------------------------------------------------------------- review round 1: R1-R3


@pytest.mark.parametrize("layer", LAYERS)
def test_erd_broken_not_utf8(ws, layer):
    """R1: a README that is not valid UTF-8: generate and --check exit 2, not 1 as for drift, with no
    traceback and a `README.md: ... not UTF-8` line on stderr, and write nothing."""
    path = ws.root / README
    path.write_bytes(path.read_bytes() + b"\xff\xfe junk\n")
    before = ws.tree()
    problem = re.compile(r"README\.md:.*not UTF-8")
    for step in (erd.generate(ws, layer), erd.check(ws, layer)):
        assert step.returncode == 2, step.shown()
        assert "Traceback" not in step.output, step.shown()
        assert any(problem.search(line) for line in step.stderr.splitlines()), (
            f"no stderr line matching {problem.pattern!r}:\n{step.shown()}"
        )
        assert ws.tree() == before, f"{' '.join(step.args)} wrote to the tree"


UNCLOSED_SECONDS = 20


def test_erd_unclosed_comment_is_fast(ws):
    """R2: an unclosed HTML comment of ~46 KB of marker-like text after the real regions is not a
    marker: every layer's --check finishes within 20 seconds, exits 0 and reports no drift."""
    path = ws.root / README
    path.write_text(path.read_text(encoding="utf-8") + "<!-- erd:conform begin " * 2000, encoding="utf-8")
    for layer in LAYERS:
        args = ("uv", "run", layer, "generate", "--check")
        # uv starts the generator as a child: on a timeout, kill the whole group, not uv alone.
        proc = subprocess.Popen(
            args, cwd=ws.root, env=ws.env(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=UNCLOSED_SECONDS)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
            pytest.fail(f"{layer} generate --check took more than {UNCLOSED_SECONDS}s on an unclosed comment")
        step = erd.Run(args, proc.returncode, stdout, stderr)
        erd.ok(step)
        assert not erd.statuses(step), f"{layer} reported drift for an unclosed comment:\n{step.shown()}"


def test_erd_broken_symlink(ws, tmp_path):
    """R3: README.md a symbolic link to a file outside the workspace: generate exits 2 with a
    `README.md: ... symbolic link` line on stderr and leaves the file outside byte-identical, though
    the declarations changed so the region would change."""
    path = ws.root / README
    outside = tmp_path / README
    outside.write_bytes(path.read_bytes())
    pristine = outside.read_bytes()
    path.unlink()
    path.symlink_to(outside)
    erd.add_weight_attribute(ws)
    problem = re.compile(r"README\.md:.*symbolic link")
    try:
        step = erd.generate(ws, "integrate")
        assert outside.read_bytes() == pristine, f"generate rewrote the file outside the repo:\n{step.shown()}"
        assert step.returncode == 2, step.shown()
        assert "Traceback" not in step.output, step.shown()
        assert any(problem.search(line) for line in step.stderr.splitlines()), (
            f"no stderr line matching {problem.pattern!r}:\n{step.shown()}"
        )
    finally:
        if path.is_symlink():
            path.unlink()
