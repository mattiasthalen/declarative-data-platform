"""The narration names no field and no count (story #39: AC6).

The script is ``src/film/explainer/narration.json`` (``{"voice", "speed", "lines": [{"text",
"cue"}]}``). The names are those [7]'s declarations hold: the contract's id, schema and
property names (logical and physical), the resource's file name, endpoint and conform name, and
the anchor's and its attributes' mnemonics and descriptors, with the mapping's columns. A name is
matched as a whole word, ignoring case, when it is 4 or more characters long.

- ``-k film_narration_generic``: AC6.
"""

from __future__ import annotations

import json
import re

import yaml
from harness import REPO

NARRATION = REPO / "src" / "film" / "explainer" / "narration.json"
SOURCE = REPO / "sources" / "adventure_works" / "products.yaml"
CONTRACT = REPO / "contracts" / "adventure_works" / "products.yaml"
MODEL = REPO / "anchor" / "model.yaml"
MAPPING = REPO / "anchor" / "mappings" / "PR_Product.yaml"


def load(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def declared_names() -> set[str]:
    names: set[str] = set()

    source = load(SOURCE)
    names |= {SOURCE.stem, f"{SOURCE.parent.name}__{SOURCE.stem}"}
    endpoint = (source or {}).get("endpoint") or {}
    if endpoint.get("path"):
        names.add(str(endpoint["path"]))

    contract = load(CONTRACT)
    names |= {str(contract[k]) for k in ("id", "name") if contract.get(k)}
    for table in contract.get("schema") or []:
        names |= {str(table[k]) for k in ("name", "physicalName") if table.get(k)}
        for prop in table.get("properties") or []:
            names |= {str(prop[k]) for k in ("name", "physicalName") if prop.get(k)}

    for anchor in load(MODEL)["schema"]["anchor"]:
        names |= {str(anchor["mnemonic"]), str(anchor["descriptor"])}
        for attribute in anchor.get("attribute") or []:
            names |= {
                str(attribute["mnemonic"]),
                str(attribute["descriptor"]),
                f"{anchor['mnemonic']}_{attribute['mnemonic']}_{anchor['descriptor']}_{attribute['descriptor']}",
            }

    mapping = load(MAPPING)
    names |= {str(mapping[k]) for k in ("anchor", "source", "changed_at") if mapping.get(k)}
    for attribute in mapping.get("attributes") or []:
        names |= {str(attribute[k]) for k in ("attribute", "column") if attribute.get(k)}

    return {name for name in names if len(name) >= 4}


def test_film_narration_generic():
    """AC6: no narration line holds a digit, or a field, resource or anchor name from [7]'s files."""
    lines = json.loads(NARRATION.read_text(encoding="utf-8"))["lines"]
    assert lines, f"{NARRATION.relative_to(REPO)} has no lines"
    names = declared_names()
    assert names, "found no names in the declarations"
    offending = []
    for number, line in enumerate(lines, 1):
        text = line["text"]
        if re.search(r"\d", text):
            offending.append(f"line {number} holds a digit: {text!r}")
        for name in sorted(names):
            if re.search(rf"(?<![A-Za-z0-9_]){re.escape(name)}(?![A-Za-z0-9_])", text, re.IGNORECASE):
                offending.append(f"line {number} names {name!r}: {text!r}")
    assert not offending, "the narration names a count or a declared name:\n" + "\n".join(offending)
