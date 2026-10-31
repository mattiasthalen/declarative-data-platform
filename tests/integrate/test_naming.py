"""AC8 offline: the committed integrate output names Roenbaeck's objects for PR_Product.

The end-to-end test (``test_anchor_objects``) checks these names and their columns in the built warehouse.
"""

from __future__ import annotations

from harness import ATTRIBUTES, REPO, annex, attribute, posit


def generated_text() -> str:
    folder = REPO / "models" / "integrate"
    files = [p for p in folder.rglob("*") if p.is_file()]
    assert files, "models/integrate holds no generated files"
    return "\n".join(f"{p.name}\n{p.read_text(errors='replace')}" for p in files)


def test_naming():
    """AC8: the anchor, 7 x (posit, annex, view), lPR_Product, key and pkey views are all named in the integrate output."""
    text = generated_text()
    expected = ["PR_Product", "lPR_Product", "key_PR_Product_NUM", "pkey_PR_Product_NUM"]
    for m in ATTRIBUTES:
        expected += [attribute(m), posit(m), annex(m)]
    missing = [name for name in expected if name not in text]
    assert missing == []
