---
paths:
  - "**/serve/**"
---

# Serve rules

- **Serve reads integrate, never conform or raw.** Business meaning is settled in integrate.
- **Serve uses only *changed-at* time** ([lexicon](../../docs/lexicon.md),
  [ADR-0011](../../docs/adr/0011-serve-a-uss-from-staged-bridges-unioned-by-name.md)): positing
  time and batches stay in integrate.
- **Hand-written models live here**, in a package folder under `models/serve/` that has no
  generator `README.md`, so no generator ever touches them
  ([ADR-0012](../../docs/adr/0012-lay-the-repo-out-by-kind-with-generator-owned-folders.md)).
