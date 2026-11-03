"""Helpers for story #3's tests: the README's generated ERD regions (spec story-3, AC1-AC13, EC1-EC12).

The tests hold the build to these interfaces, which the spec fixes or implies:

- **Markers.** Each layer owns one region of the root ``README.md``, between a begin and an end
  marker. A marker is an HTML comment (``<!-- ... -->``) that holds the region's name and its
  side: ``erd:conform begin`` ... ``erd:conform end``, likewise ``erd:integrate`` and
  ``erd:serve``. The rest of the comment's text (naming ``uv run <layer> generate``, say) is the
  build's to choose; the tests find a marker by that loose pattern alone, and treat the region
  as the text strictly between the begin comment and the end comment.
- **The region.** One fenced ```` ```mermaid ```` block whose first line is ``erDiagram``.
  An entity with rows is ``<name> {``, one row per line as ``<type> <name> [PK|FK] ["comment"]``,
  then ``}``; an entity with no rows is its name on a line of its own; a relationship is
  ``<a> }o--|| <b> : "<label>"`` on one line.
- **Writing.** ``uv run <layer> generate`` rewrites only its region; ``--check`` reports the
  README as ``changed README.md`` with a diff under it, exit 1, as for any generated file.
- **Broken markers** ([6], [S3], [S4]): exit 2 for ``generate`` and ``--check`` alike, nothing
  written, and a line on stderr ``README.md: <marker> <problem>``: the marker named by its
  region name and side (``erd:integrate begin``), the problem ``missing``, ``appears N times``
  or ``ends before it begins``.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml
from harness import CONTRACT_PATH, Workspace

LAYERS = ("conform", "integrate", "serve")
README = "README.md"
RESTORED = ("models", "contracts", "anchor", README)
EDIT_MARK = "hand edit 7f3a9c"
STATUS = re.compile(r"^(changed|missing|stale)\s+(\S+)")

# The seven attributes of PR_Product in model order: (Roenbaeck name, dataRange, serve column).
PR_ATTRIBUTES = [
    ("PR_NUM_Product_ProductNumber", "varchar(25)", "product__product_number"),
    ("PR_NAM_Product_Name", "varchar(50)", "product__name"),
    ("PR_LIN_Product_ProductLine", "varchar(2)", "product__product_line"),
    ("PR_COL_Product_Color", "varchar(15)", "product__color"),
    ("PR_SST_Product_SellStart", "date", "product__sell_start"),
    ("PR_SEN_Product_SellEnd", "date", "product__sell_end"),
    ("PR_DIS_Product_Discontinued", "date", "product__discontinued"),
]


# --------------------------------------------------------------------------- markers and regions


def marker_pattern(layer: str, side: str) -> re.Pattern:
    """An HTML comment naming ``erd:<layer> <side>``, however the rest of the comment reads."""
    inside = r"(?:(?!-->).)*?"
    return re.compile(rf"<!--{inside}\berd:{layer}\s+{side}\b{inside}-->", re.DOTALL)


def markers(text: str, layer: str, side: str) -> list[re.Match]:
    return list(marker_pattern(layer, side).finditer(text))


@dataclass(frozen=True)
class Region:
    begin: re.Match
    end: re.Match
    text: str  # strictly between the begin comment and the end comment


def region(text: str, layer: str) -> Region:
    """``layer``'s one well-formed region of ``text``; fails the test when there is none."""
    begins, ends = markers(text, layer, "begin"), markers(text, layer, "end")
    assert len(begins) == 1, f"README.md has {len(begins)} erd:{layer} begin markers, expected exactly one"
    assert len(ends) == 1, f"README.md has {len(ends)} erd:{layer} end markers, expected exactly one"
    begin, end = begins[0], ends[0]
    assert begin.end() <= end.start(), f"README.md's erd:{layer} region ends before it begins"
    return Region(begin, end, text[begin.end() : end.start()])


def readme(ws: Workspace) -> str:
    return (ws.root / README).read_text(encoding="utf-8")


def mermaid(region_text: str) -> list[str]:
    """The lines of the region's one fenced mermaid block, without its fences."""
    fences = re.findall(r"^[ \t]*```[ \t]*mermaid[ \t]*\n(.*?)^[ \t]*```[ \t]*$", region_text, re.DOTALL | re.MULTILINE)
    assert len(fences) == 1, f"the region holds {len(fences)} fenced mermaid blocks, expected one:\n{region_text}"
    return fences[0].splitlines()


ROW = re.compile(r'^(\S+)\s+(\S+)(?:\s+((?:PK|FK|UK)(?:\s*,\s*(?:PK|FK|UK))*))?(?:\s+"([^"]*)")?$')
RELATIONSHIP = re.compile(r"^(\S+)\s+([|}o][|o]?(?:--|\.\.)[|o]?[|{o])\s+(\S+)\s*:\s*(.+)$")


@dataclass
class Diagram:
    entities: dict[str, list[tuple[str, str, str | None, str | None]] | None]  # name -> rows; None when bare
    relationships: list[str]  # whitespace collapsed to single spaces
    lines: list[str]

    def rows(self, entity: str) -> list[tuple[str, str, str | None, str | None]]:
        assert entity in self.entities, f"the diagram has no entity {entity}: {list(self.entities)}"
        rows = self.entities[entity]
        assert rows is not None, f"{entity} is a bare entity with no rows"
        return rows

    def columns(self, entity: str) -> list[str]:
        return [name for _, name, _, _ in self.rows(entity)]


def diagram(region_text: str) -> Diagram:
    """Parse the region's erDiagram into entities (in order), their rows, and relationships."""
    lines = mermaid(region_text)
    body = [line.strip() for line in lines if line.strip() and not line.strip().startswith("%%")]
    assert body and body[0] == "erDiagram", f"the mermaid block does not start with erDiagram:\n{region_text}"
    entities: dict = {}
    relationships: list[str] = []
    current = None
    for line in body[1:]:
        if current is not None:
            if line == "}":
                current = None
                continue
            row = ROW.match(line)
            assert row, f"not an erDiagram row in {current}: {line!r}"
            keys = re.sub(r"\s+", "", row.group(3)) if row.group(3) else None
            entities[current].append((row.group(1), row.group(2), keys, row.group(4)))
            continue
        if opened := re.match(r"^(\S+)\s*\{$", line):
            current = opened.group(1)
            assert current not in entities, f"entity {current} appears twice"
            entities[current] = []
        elif re.match(r"^(\S+)\s*\{\s*\}$", line):
            name = line.split("{")[0].strip()
            entities[name] = []
        elif RELATIONSHIP.match(line):
            relationships.append(re.sub(r"\s+", " ", line))
        elif re.match(r"^[A-Za-z_][A-Za-z0-9_-]*$", line):
            assert line not in entities, f"entity {line} appears twice"
            entities[line] = None
        else:
            raise AssertionError(f"not an erDiagram line: {line!r}")
    assert current is None, f"entity {current} is never closed"
    return Diagram(entities, relationships, lines)


def layer_diagram(ws: Workspace, layer: str) -> Diagram:
    return diagram(region(readme(ws), layer).text)


# --------------------------------------------------------------------------- running


@dataclass
class Run:
    args: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout + self.stderr

    def shown(self) -> str:
        return f"`{' '.join(self.args)}` exited {self.returncode}\nstdout:\n{self.stdout[-3000:]}\nstderr:\n{self.stderr[-3000:]}"


def run(ws: Workspace, *args: str) -> Run:
    """Run a command in the workspace, keeping stdout and stderr apart."""
    proc = subprocess.run(args, cwd=ws.root, env=ws.env(), capture_output=True, text=True, timeout=600, check=False)
    return Run(args, proc.returncode, proc.stdout, proc.stderr)


def generate(ws: Workspace, layer: str) -> Run:
    return run(ws, "uv", "run", layer, "generate")


def check(ws: Workspace, layer: str) -> Run:
    return run(ws, "uv", "run", layer, "generate", "--check")


def task(ws: Workspace, name: str) -> Run:
    return run(ws, "uv", "run", "task", name)


def ok(step: Run) -> Run:
    assert step.returncode == 0, step.shown()
    assert "Traceback" not in step.output, step.shown()
    return step


def statuses(step: Run) -> set[tuple[str, str]]:
    found = set()
    for line in step.stdout.splitlines():
        if match := STATUS.match(line):
            path = match.group(2).rstrip(":,;")
            found.add((match.group(1), path.removeprefix("./")))
    return found


def entry(step: Run, path: str) -> list[str]:
    """The stdout lines under ``path``'s status line, up to the next status line or the summary."""
    lines = step.stdout.splitlines()
    start = next(
        (i for i, line in enumerate(lines) if (m := STATUS.match(line)) and m.group(2).removeprefix("./") == path),
        None,
    )
    assert start is not None, f"no status line for {path}:\n{step.shown()}"
    out = []
    for line in lines[start + 1 :]:
        if STATUS.match(line) or "task generate" in line:
            break
        out.append(line)
    return out


def added(lines: list[str]) -> list[str]:
    return [line for line in lines if line.startswith("+") and not line.startswith("+++")]


def verdicts(step: Run) -> dict[str, str]:
    """layer -> 'pass' or 'fail', read off `task check`'s one line per layer."""
    found = {}
    for line in step.output.splitlines():
        match = re.match(rf"^\s*({'|'.join(LAYERS)})\b.*?\b(pass|fail)\w*\b", line, re.IGNORECASE)
        if match:
            found[match.group(1)] = match.group(2).lower()
    return found


# --------------------------------------------------------------------------- the workspace


def keep(ws: Workspace, pristine: Path) -> tuple[Workspace, Path]:
    """Copy what the tests change, so ``restore`` can put it back before every test."""
    for name in RESTORED:
        source = ws.root / name
        if source.is_dir():
            shutil.copytree(source, pristine / name, symlinks=True)
        else:
            shutil.copy2(source, pristine / name)
    return ws, pristine


def restore(ws: Workspace, pristine: Path) -> Workspace:
    for name in RESTORED:
        target = ws.root / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
        source = pristine / name
        if source.is_dir():
            shutil.copytree(source, target, symlinks=True)
        else:
            shutil.copy2(source, target)
    ws.steps.clear()
    return ws


def owned_files(ws: Workspace, layer: str) -> list[Path]:
    """The .sql files in the package folders whose README carries ``layer``'s generator marker."""
    heading = f"# Generated by `uv run {layer} generate`"
    files = sorted(
        sql
        for marker in (ws.root / "models").glob("*/*/README.md")
        if marker.read_text(encoding="utf-8").splitlines()[:1] == [heading]
        for sql in marker.parent.glob("*.sql")
    )
    assert files, f"no generated .sql file of {layer} under models/"
    return files


# --------------------------------------------------------------------------- declarations


def edit_yaml(path: Path, change) -> None:
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    change(document)
    path.write_text(yaml.safe_dump(document, sort_keys=False, allow_unicode=True), encoding="utf-8")


def add_contract(ws: Workspace, stem: str, *, primary_key: bool = True) -> str:
    """A copy of the Products contract as ``contracts/adventure_works/<stem>.yaml``; returns its object name."""
    name = f"adventure_works__{stem}"
    contract = yaml.safe_load((ws.root / CONTRACT_PATH).read_text(encoding="utf-8"))
    contract["id"] = contract["name"] = name
    contract["schema"][0]["name"] = contract["schema"][0]["physicalName"] = name
    if not primary_key:
        for prop in contract["schema"][0]["properties"]:
            prop.pop("primaryKey", None)
    target = ws.root / "contracts" / "adventure_works" / f"{stem}.yaml"
    target.write_text(yaml.safe_dump(contract, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return name


def model_path(ws: Workspace) -> Path:
    return ws.root / "anchor" / "model.yaml"


def add_weight_attribute(ws: Workspace) -> tuple[str, str]:
    """Add PR_WGT_Product_Weight (double) to the model and its mapping; returns (integrate name, serve column)."""

    def change(model):
        next(a for a in model["schema"]["anchor"] if a["mnemonic"] == "PR")["attribute"].append(
            {
                "mnemonic": "WGT",
                "descriptor": "Weight",
                "dataRange": "double",
                "timeRange": "timestamp",
                "description": "The product's weight.",
            }
        )

    edit_yaml(model_path(ws), change)
    edit_yaml(
        ws.root / "anchor" / "mappings" / "PR_Product.yaml",
        lambda mapping: mapping["attributes"].append({"attribute": "WGT", "column": "weight"}),
    )
    return "PR_WGT_Product_Weight", "product__weight"


def add_vendor_anchor_first(ws: Workspace) -> None:
    """Declare a second anchor, VE_Vendor, before PR_Product in the model, with its mapping."""

    def change(model):
        model["schema"]["anchor"].insert(
            0,
            {
                "mnemonic": "VE",
                "descriptor": "Vendor",
                "identity": "int",
                "description": "A business the products are bought from.",
                "identifier": [{"route": "NAM"}],
                "attribute": [
                    {
                        "mnemonic": "NAM",
                        "descriptor": "Name",
                        "dataRange": "varchar(50)",
                        "timeRange": "timestamp",
                        "description": "The vendor's name; its natural key.",
                        "key": [{"stop": "1", "route": "NAM", "of": "VE"}],
                    }
                ],
            },
        )

    edit_yaml(model_path(ws), change)
    mapping = {
        "anchor": "VE",
        "source": "adventure_works__products",
        "changed_at": "modified_date",
        "attributes": [{"attribute": "NAM", "column": "name"}],
    }
    (ws.root / "anchor" / "mappings" / "VE_Vendor.yaml").write_text(yaml.safe_dump(mapping, sort_keys=False), encoding="utf-8")


def declared(ws: Workspace) -> tuple[list[str], list[str]]:
    """(``<mnemonic>_<descriptor>`` of each anchor, the name of each tie) in ``ws``'s model, in model order."""
    schema = yaml.safe_load(model_path(ws).read_text(encoding="utf-8"))["schema"]
    anchors = schema.get("anchor") or []
    ties = schema.get("tie") or []
    anchors = anchors if isinstance(anchors, list) else [anchors]
    ties = ties if isinstance(ties, list) else [ties]
    names = []
    for tie in ties:
        roles = tie.get("anchorRole") or tie.get("role") or []
        roles = roles if isinstance(roles, list) else [roles]
        names.append("_".join(f"{r.get('type')}_{r.get('role')}" for r in roles))
    return [f"{a['mnemonic']}_{a['descriptor']}" for a in anchors], names


def contracts(ws: Workspace) -> list[str]:
    """The id of each contract, in the order conform reads them: by source folder, then file name."""
    found = sorted((ws.root / "contracts").glob("*/*.yaml"))
    return [yaml.safe_load(path.read_text(encoding="utf-8"))["id"] for path in found]


def entity(descriptor: str) -> str:
    """Serve's entity name for an anchor descriptor: ``ProductSubcategory`` is ``product_subcategory``."""
    return re.sub(r"(?<!^)(?=[A-Z])", "_", descriptor).lower()
