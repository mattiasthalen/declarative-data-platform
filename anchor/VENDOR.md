# Vendored: anchor.xsd

`anchor.xsd` is Lars Rönnbäck's XML Schema for Anchor models, copied unchanged from
[Roenbaeck/anchor](https://github.com/Roenbaeck/anchor) at commit
`9ed4c9329b9985d3544cb55a52a1763fb75ffd2f` (2026-10-30). `model.yaml` mirrors it
(ADR-0004): every key in the YAML is one of its elements or attributes, which
`tests/integrate/test_model_mirrors_xsd.py` checks. Update it by copying a newer
`anchor.xsd` over this one and recording the commit here.
