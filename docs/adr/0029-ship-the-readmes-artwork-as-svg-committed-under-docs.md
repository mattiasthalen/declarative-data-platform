# ADR-0029 — Ship the README's artwork as SVG committed under docs/

**Status:** Accepted (2026-11-01)

## Context

Epic 5 puts artwork in the README: a hero image (#37), the same scene in motion (#38) and a longer explainer linked from the README (#39). GitHub shows a README image through an image tag, serving a relative one from the repository. It plays video inline only from its own uploads, which live outside the repository. The README is reviewed as text in pull requests, and its hero is shown at whatever width the reader's screen gives it, on high-density screens too.

## Decision

The README's artwork is SVG, one file per image, committed under `docs/` and referenced from the README by a relative path.

Rejected: PNG, which is soft when GitHub scales it unless exported at two or three times its size, cannot be animated from the same source for #38, and changes as an opaque binary in review. PNG stays the right format for the repository's social preview, which GitHub takes only as PNG, JPG or GIF and which is a repository setting, not a file in the repo. Video uploaded to GitHub, which plays inline but lives outside the repository, so it cannot be reviewed, versioned or rebuilt with the README.

## Consequences

The artwork scales sharply to any width, reviews as a text diff, and #38 can build on the same file instead of a separate asset. Everything the README shows lives in the repository. SVG shown through an image tag may fetch nothing from outside and cannot see GitHub's theme, so each file must carry its own fonts and its own ground; those choices are made per story and recorded in its PR. A social-preview PNG, if wanted, is exported from the SVG by hand and set in the repository's settings.
