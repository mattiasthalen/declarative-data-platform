# ADR-0034 — Render the explainer in CI and publish it on a rolling release

**Status:** Accepted (2026-11-02)

## Context

Story #39 is a longer explainer linked from the README: about two minutes that take a viewer through ingest, conform, integrate and serve, each shown through its declaration, saying what the layer does and why. It must have sound: a narrator and music. ADR-0029 made the README's artwork SVG committed in the repository and rejected video uploaded to GitHub, because it lives outside the repository and cannot be reviewed, versioned or rebuilt with the README. An SVG carries no sound. A rendered video is a binary of several megabytes that would change on every edit if committed. The film reads Products' declarations when it renders, so it changes whenever they do, and AdventureWorks will be declared in full. daana-code/daana-promo renders its films the same way and attaches the cuts to releases, but asks its maintainer for each release and reviews a committed storyboard in every pull request.

## Decision

The explainer is a video rendered from files in the repository: an HTML composition in `src/film/`, rendered frame by frame with Playwright and ffmpeg, with a synthesized score and narration. It is not committed. A `film` workflow renders it on every push to `main` that touches what it is made from (`src/film/`, `src/artwork/`, `sources/`, `contracts/`, `anchor/`, `orchestrate/prefect.yaml`), and on demand, and replaces the asset on one release tagged `explainer`, creating the release the first time. The README links the asset's fixed download URL. One cut: landscape, narrated, captions burned in.

Rejected: an animated SVG like the hero, which has no sound; a web page, which nobody asked for and needs hosting; committing the video, which puts a large binary in every film change's diff; a new release per render, which collides with any future version release at "latest" and breaks a fixed link; daana-promo's review flow (storyboard committed and reviewed in the pull request, a frame-by-frame check against `main`, a release only when the maintainer asks), which repeats what the pull request's evidence and the render on `main` already give; the soundtrack-only cut, the portrait stage and caption holds, which nothing asks for yet.

## Consequences

The film is always the one `main` renders; a pull request shows it only through its evidence. A render that fails turns the `film` workflow red and leaves the previous asset up. Every change to a declaration re-renders the film, a few minutes of CI. The release carries no version and is never "latest" in a meaningful sense. The workflow needs `contents: write`, which the `ci` workflow does not have.
