# ADR-0040 — Publish the explainer on GitHub Pages

**Status:** Accepted (2026-11-03) · **Supersedes:** the where-the-film-is-published decision in [ADR-0034](0034-render-the-explainer-in-ci-and-publish-it-on-a-rolling-release.md)

## Context

ADR-0034 renders the explainer in CI on `main` and publishes it by replacing the asset on one release tagged `explainer`, which the README links. Review of story #39 probed GitHub's release downloads: every asset redirects to a signed URL that forces `Content-Disposition: attachment` and `application/octet-stream`, whatever type it was uploaded with, so a browser saves the film instead of playing it, on a phone too. `gh release upload --clobber` also deletes the old asset before uploading the new one, so a failed or cancelled upload leaves the link dead. The README's link reads "Watch the two-minute explainer, with sound". ADR-0034 rejected a web page as unasked for and needing hosting; a page is now the only way to play the film in the browser, and GitHub Pages hosts one for a public repository, which this is.

## Decision

The `film` workflow deploys the explainer to the repository's GitHub Pages site: a page holding the video, and the MP4 beside it. The render runs in a job with read-only access and uploads the site as a Pages artifact; a second job, only on `main`, deploys it with `pages: write`, and is not cancelled once started. The README links the site's root, `https://mattiasthalen.github.io/declarative-data-platform/`. Rendering stays as ADR-0034 decided.

Rejected: keeping the release and calling the link a download, which gives up playing in the browser; a video uploaded to GitHub and embedded in the README, which ADR-0029 rejected; replacing the release asset under a temporary name and renaming it, which still downloads.

## Consequences

The film plays in the browser, on desktop and on a phone. A failed render deploys nothing, and a failed or cancelled deploy is cancelled by `actions/deploy-pages` and leaves the previous site up (assumption A29). The repository's Pages source must be set to GitHub Actions once, by its owner; until then the deploy job fails. The Pages site belongs to the explainer: anything else published there later shares this workflow or replaces it. A render dispatched on another branch stops at its artifact. A dependency bump (`pyproject.toml`, `uv.lock`) is not in the path filter, so it reaches the film only with the next render.
