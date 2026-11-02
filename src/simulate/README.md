# The change simulator

Hand-written, no generator owns this folder. `adventure_works__products.jsonl` is the AdventureWorks
Products feed as it served on 2026-11-01: 504 rows, one JSON row per line, as `ingest` lands them.
Refresh it by hand if the feed changes (A20). See ADR-0027.

A product dropped from one load returns in the next within a run that completes. A run stopped between the
two leaves it out of the lake's latest load, and later runs start from that load without it.
