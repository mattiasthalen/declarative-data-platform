"""AC24: anchor/model.yaml is a mirror of anchor.xsd -- it names only the XSD's elements and attributes."""

from __future__ import annotations

import xml.etree.ElementTree as ET

import yaml

from harness import ATTRIBUTES, REPO

XS = "{http://www.w3.org/2001/XMLSchema}"


def xsd_names() -> set[str]:
    found = [p for p in REPO.rglob("anchor.xsd") if not {".venv", ".git"} & set(p.relative_to(REPO).parts)]
    assert len(found) == 1, f"expected one vendored anchor.xsd, found {found}"
    root = ET.parse(found[0]).getroot()
    return {
        node.get("name")
        for node in root.iter()
        if node.tag in (f"{XS}element", f"{XS}attribute") and node.get("name")
    }


def keys(node, path="") -> list[tuple[str, str]]:
    out = []
    if isinstance(node, dict):
        for key, value in node.items():
            out.append((str(key), path))
            out += keys(value, f"{path}/{key}")
    elif isinstance(node, list):
        for item in node:
            out += keys(item, path)
    return out


def model() -> dict:
    return yaml.safe_load((REPO / "anchor" / "model.yaml").read_text())


def test_model_mirrors_xsd():
    """AC24: every key in anchor/model.yaml is an element or attribute of anchor.xsd."""
    allowed = xsd_names()
    strange = [(k, where) for k, where in keys(model()) if k.lstrip("@") not in allowed]
    assert strange == [], f"not in anchor.xsd: {strange}"


def test_model_declares_product():
    """AC24 / [6]: the model holds PR Product and its seven attributes, each with a description ([10])."""
    found = {}

    def walk(node):
        if isinstance(node, dict):
            fields = {str(k).lstrip("@"): v for k, v in node.items()}
            if "mnemonic" in fields and "descriptor" in fields:
                found[fields["mnemonic"]] = fields
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(model())
    assert found.get("PR", {}).get("descriptor") == "Product"
    for mnemonic, descriptor in ATTRIBUTES.items():
        assert found.get(mnemonic, {}).get("descriptor") == descriptor, mnemonic
    for mnemonic in ["PR", *ATTRIBUTES]:
        assert str(found[mnemonic].get("description") or "").strip(), f"{mnemonic} has no description"
