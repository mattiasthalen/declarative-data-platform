"""The film's data, read from the declarations when it renders (story #39: AC3, AC4, AC5, EC1-EC3).

``film.data.build(root)`` reads the declarations under ``root`` and returns the film's data:
``chapters`` in timeline order, each ``{"name", "declaration", "close_up", "zoom_out"}``, where
``close_up`` is ``{"path", "lines", "elided"}`` for each file the chapter shows (one such dict, or
a list of them), ``path`` relative to ``root``, and ``zoom_out`` is ``{"tiles": [{"kind",
"name"}]}``. ``CARD_LINES`` and ``CARD_COLUMNS`` are module constants; a missing file or a line
wider than ``CARD_COLUMNS`` raises ``film.data.DeclarationError`` naming the path (and the line).
EC2 is checked on what the page draws, in ``test_page.py``.

The throwaway copies here are plain file copies of the repo: ``build`` runs in this process on
the copy's root, so no copy needs its own environment.

- ``-k film_reads_declarations``: AC3. ``-k film_zoom_out``: AC4 (and EC2, whose name it
  prefixes, in ``test_page.py``). ``-k film_overflow``: AC5.
  ``-k film_missing_declaration``: EC1. ``-k film_out_ignored``: EC3.
"""

from __future__ import annotations

import copy
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from harness import NOT_IN_A_CLONE, REPO

from film import data

LAYERS = ("ingest", "conform", "integrate", "serve")
SOURCE = "sources/adventure_works/products.yaml"
CONTRACT = "contracts/adventure_works/products.yaml"
MODEL = "anchor/model.yaml"
MAPPING = "anchor/mappings/PR_Product.yaml"
# [7]: the files the layer chapters' close-ups show, and no others.
CLOSE_UP_FILES = {SOURCE, CONTRACT, MODEL, MAPPING}
ELISION = "…"
_FILM_LOCAL = shutil.ignore_patterns(".models", "out")


def copy_repo(tmp_path: Path) -> Path:
    """A throwaway copy of the repo's files, as a fresh clone has them."""
    root = tmp_path / "repo"

    def ignore(folder, names):
        return set(NOT_IN_A_CLONE(folder, names)) | set(_FILM_LOCAL(folder, names))

    shutil.copytree(REPO, root, ignore=ignore, symlinks=True)
    return root


def chapters(film: dict) -> dict[str, dict]:
    found = {chapter["name"]: chapter for chapter in film["chapters"]}
    missing = [name for name in LAYERS if name not in found]
    assert not missing, f"the film's data has no chapter {missing}; chapters are {list(found)}"
    return found


def close_ups(chapter: dict) -> list[dict]:
    shown = chapter["close_up"]
    shown = [shown] if isinstance(shown, dict) else list(shown)
    assert shown, f"chapter {chapter['name']!r} has no close-up"
    return shown


def tiles(chapter: dict) -> list[dict]:
    return list(chapter["zoom_out"]["tiles"])


def visible(close_up: dict) -> list[str]:
    """The close-up's lines without its elision mark."""
    lines = list(close_up["lines"])
    if close_up["elided"]:
        assert lines and lines[-1].strip() == ELISION, (
            f"{close_up['path']}'s close-up is elided but does not end in {ELISION!r}: {lines[-1:]}"
        )
        lines = lines[:-1]
    return lines


def is_excerpt(shown: list[str], text: str) -> bool:
    """True when ``shown`` is a contiguous run of ``text``'s lines (indentation and blank lines aside)."""
    wanted = [line.strip() for line in shown if line.strip()]
    have = [line.strip() for line in text.splitlines() if line.strip()]
    if not wanted:
        return False
    return any(have[i : i + len(wanted)] == wanted for i in range(len(have) - len(wanted) + 1))


def without_message_root(error: Exception, root: Path) -> str:
    return str(error).replace(str(root.resolve()), "").replace(str(root), "")


# --------------------------------------------------------------------------- AC3


def test_film_reads_declarations(tmp_path):
    """AC3: the layer chapters' close-ups show exactly [7]'s files, their lines are the files' text,
    and the integrate close-up of anchor/model.yaml is the PR anchor. In a throwaway copy, editing
    a value the conform close-up shows changes that close-up's text and nothing else in the data."""
    film = data.build(REPO)
    found = chapters(film)
    paths = set()
    for name in LAYERS:
        for shown in close_ups(found[name]):
            path = Path(shown["path"]).as_posix()
            paths.add(path)
            text = (REPO / path).read_text(encoding="utf-8")
            assert is_excerpt(visible(shown), text), (
                f"the {name} close-up of {path} is not the file's text:\n" + "\n".join(shown["lines"])
            )
            if path == MODEL:
                assert any(re.search(r"mnemonic:\s*PR\b", line) for line in visible(shown)), (
                    f"the {name} close-up of {MODEL} does not show the PR anchor"
                )
    assert paths == CLOSE_UP_FILES, (
        f"the close-ups show {sorted(paths)}, expected exactly {sorted(CLOSE_UP_FILES)}"
    )

    root = copy_repo(tmp_path)
    before = data.build(root)
    conform = close_ups(chapters(before)["conform"])
    (contract,) = [shown for shown in conform if Path(shown["path"]).as_posix() == CONTRACT]
    editable = re.compile(r"^\s*(?:-\s+)?(version|status|domain|description):\s+(?![>|])\S")
    target = next((line for line in visible(contract) if editable.match(line)), None)
    assert target is not None, "the conform close-up shows no editable value:\n" + "\n".join(contract["lines"])
    path = root / CONTRACT
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    index = next(i for i, line in enumerate(lines) if line.strip() == target.strip())
    key = lines[index].split(":", 1)[0]
    edited = "edited-by-the-film-test"
    lines[index] = f"{key}: {edited}\n"
    path.write_text("".join(lines), encoding="utf-8")

    after = data.build(root)
    shown_after = [
        s for s in close_ups(chapters(after)["conform"]) if Path(s["path"]).as_posix() == CONTRACT
    ]
    assert shown_after and any(edited in line for line in shown_after[0]["lines"]), (
        f"editing {CONTRACT} line {index + 1} did not change the conform close-up:\n"
        + "\n".join(shown_after[0]["lines"] if shown_after else [])
    )

    def blank_conform_close_up(film: dict) -> dict:
        film = copy.deepcopy(film)
        for chapter in film["chapters"]:
            if chapter["name"] == "conform":
                chapter["close_up"] = None
        return film

    assert blank_conform_close_up(after) == blank_conform_close_up(before), (
        f"editing a value in {CONTRACT} changed more of the film's data than the conform close-up"
    )


# --------------------------------------------------------------------------- AC4


def declared(root: Path) -> dict[str, list[tuple[str, ...]]]:
    """chapter -> one entry per thing its zoom-out draws, each the names a tile may carry for it."""
    resources = sorted(
        (p.stem,) for p in root.glob("sources/*/*.yaml") if not p.name.startswith("_")
    )
    contracts = sorted((p.stem,) for p in root.glob("contracts/*/*.yaml"))
    model = yaml.safe_load((root / MODEL).read_text(encoding="utf-8"))
    anchors = [(a["mnemonic"], a["descriptor"]) for a in model["schema"]["anchor"]]
    return {"ingest": resources, "conform": contracts, "integrate": anchors}


def test_film_zoom_out(tmp_path):
    """AC4: the ingest zoom-out has one tile per resource in sources/*/, conform one per contract in
    contracts/*/, integrate one per anchor in anchor/model.yaml. Adding a resource file in a
    throwaway copy adds one tile to the ingest zoom-out."""
    found = chapters(data.build(REPO))
    for name, names in declared(REPO).items():
        drawn = tiles(found[name])
        assert len(drawn) == len(names), (
            f"the {name} zoom-out draws {len(drawn)} tiles, expected {len(names)} (one per {names})"
        )
        for each in names:
            assert any(
                str(tile["name"]).lower() in {alias.lower() for alias in each}
                or any(alias.lower() in str(tile["name"]).lower() for alias in each if len(alias) > 2)
                for tile in drawn
            ), f"no tile of the {name} zoom-out names {each}: {drawn}"

    root = copy_repo(tmp_path)
    before = len(tiles(chapters(data.build(root))["ingest"]))
    (root / "sources" / "adventure_works" / "extra.yaml").write_text(
        "# Added by the film test.\nendpoint:\n  path: Extra\n", encoding="utf-8"
    )
    drawn = tiles(chapters(data.build(root))["ingest"])
    assert len(drawn) == before + 1, (
        f"adding sources/adventure_works/extra.yaml made the ingest zoom-out {len(drawn)} tiles, expected {before + 1}"
    )
    assert any("extra" in str(tile["name"]).lower() for tile in drawn), f"no ingest tile names extra: {drawn}"


# --------------------------------------------------------------------------- AC5


def test_film_overflow(tmp_path):
    """AC5: a file longer than CARD_LINES is cut at the card, elided, its last line the elision
    mark; a file that fits is shown whole. A line wider than CARD_COLUMNS raises DeclarationError
    naming the file and the line."""
    root = copy_repo(tmp_path)
    contract = root / CONTRACT
    extra = "".join(
        f"      - name: padding_{i}\n        physicalName: Padding{i}\n        logicalType: string\n"
        for i in range(data.CARD_LINES)
    )
    contract.write_text(contract.read_text(encoding="utf-8") + extra, encoding="utf-8")
    assert len(contract.read_text(encoding="utf-8").splitlines()) > data.CARD_LINES

    found = chapters(data.build(root))
    (shown,) = [s for s in close_ups(found["conform"]) if Path(s["path"]).as_posix() == CONTRACT]
    assert shown["elided"] is True, f"{CONTRACT} is longer than the card but its close-up is not elided"
    lines = list(shown["lines"])
    assert data.CARD_LINES - 1 <= len(lines) <= data.CARD_LINES, (
        f"the elided close-up has {len(lines)} lines; the card holds {data.CARD_LINES}"
    )
    assert lines[-1].strip() == ELISION, f"the elided close-up ends {lines[-1]!r}, not {ELISION!r}"
    assert is_excerpt(lines[:-1], contract.read_text(encoding="utf-8")), "the elided close-up is not the file's text"

    (source,) = [s for s in close_ups(found["ingest"]) if Path(s["path"]).as_posix() == SOURCE]
    text = (root / SOURCE).read_text(encoding="utf-8")
    if len(text.splitlines()) < data.CARD_LINES:
        assert source["elided"] is False, f"{SOURCE} fits the card but its close-up is elided"
        assert all(line.strip() != ELISION for line in source["lines"]), f"{SOURCE}'s close-up shows an elision"

    wide = root / SOURCE
    lines = text.splitlines()
    number = next(i for i, line in enumerate(lines, 1) if line.strip().startswith("path:"))
    lines[number - 1] = "  path: " + "P" * (data.CARD_COLUMNS + 10)
    wide.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(data.DeclarationError) as raised:
        data.build(root)
    message = without_message_root(raised.value, root)
    assert SOURCE in message, f"the DeclarationError does not name {SOURCE}: {raised.value}"
    assert re.search(rf"(line\s*|:){number}\b", message), (
        f"the DeclarationError does not name line {number}: {raised.value}"
    )


# --------------------------------------------------------------------------- EC1


def test_film_missing_declaration(tmp_path):
    """EC1: with contracts/adventure_works/products.yaml deleted, build raises DeclarationError
    naming that path."""
    root = copy_repo(tmp_path)
    (root / CONTRACT).unlink()
    with pytest.raises(data.DeclarationError) as raised:
        data.build(root)
    assert CONTRACT in without_message_root(raised.value, root), (
        f"the DeclarationError does not name {CONTRACT}: {raised.value}"
    )


# --------------------------------------------------------------------------- EC3


def test_film_out_ignored():
    """EC3: git ignores out/ (where `task film` renders) and .models/ (where the Kokoro files go)."""
    paths = ["out/film/x.mp4", ".models/x"]
    proc = subprocess.run(["git", "check-ignore", *paths], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, f"git does not ignore {paths}: {proc.stdout}{proc.stderr}"
    ignored = set(proc.stdout.split())
    assert ignored == set(paths), f"git ignores {sorted(ignored)} of {paths}"
