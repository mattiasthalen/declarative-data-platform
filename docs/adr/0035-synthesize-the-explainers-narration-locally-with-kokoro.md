# ADR-0035 — Synthesize the explainer's narration locally with Kokoro-82M

**Status:** Accepted (2026-11-02)

## Context

The explainer (ADR-0034) is narrated, and CI renders it again whenever its sources change, unattended. The narration is a script of lines with their cues in `src/film/`. daana-code/daana-promo narrates its films with Kokoro-82M through `kokoro-onnx`, run locally, its model files downloaded by checksum; its ADR-0007 rejected a hosted voice.

## Decision

The narration is synthesized from its script with Kokoro-82M (Apache-2.0) through `kokoro-onnx`, run on the machine that renders, with model files fetched from a pinned URL and verified by SHA-256 before use. The script names no field and no count: the picture carries every specific, so a declaration change never makes the voice false.

Rejected: a recorded voice, which must be recorded again after every script change; a hosted voice, which adds an account, a secret, a network dependency and a cost per render, and whose voice the repository cannot pin; counts or names templated into the script, which make the voice harder to tune.

## Consequences

A render downloads about 350 MB of model files once per cache; the `film` workflow caches them by checksum. The voice sounds synthetic. The narration is English only. Changing a line re-synthesizes the narration; moving a cue may need the composition's timing moved with it, and a line that runs past the next cue fails the render.
