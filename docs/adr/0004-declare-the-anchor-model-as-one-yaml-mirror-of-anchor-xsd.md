# ADR-0004 — Declare the Anchor model as one YAML file that mirrors anchor.xsd

**Status:** Accepted (2026-10-31)

## Context

The Anchor model is authored by people and agents and read by the integrate and serve generators. Roenbaeck's format is XML validated by `anchor.xsd`, which the online modeler opens and saves; XML is painful to write by hand.

## Decision

The model is one `anchor/model.yaml` for the whole model, using only the elements and attributes of `anchor.xsd`, with the same names, so it converts to the modeler's XML and back without loss. Mappings from contract columns to attributes are ours, not Anchor's, and live apart in `anchor/mappings/<anchor>.yaml`, one per anchor. The converter waits for a later story.

Rejected: XML as the source, which is hard to compose and diff; YAML with our own shape, which loses the modeler.

## Consequences

Any field we want that `anchor.xsd` lacks goes in the mapping files or in Anchor's `metadata`, never as a new key in `model.yaml`. Until the converter exists, the modeler cannot open our model.
