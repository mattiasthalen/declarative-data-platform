# ADR-0037 — Resolve a tie's reference through the other anchor's key, and skip one not yet known

**Status:** Accepted (2026-11-03)

## Context

A Products row names its subcategory only by `ProductSubcategoryId`, the source's own id. ADR-0005 identifies an anchor by a surrogate found through its key view. The subcategory anchor must therefore be keyed by something the product row carries, and a product can name a subcategory whose own row has not landed yet.

## Decision

ProductSubcategory is keyed by the source's id, attribute `PS_SID_ProductSubcategory_SourceId`, its identifier route. The mapping that loads a tie names the column holding the other role's key; the load finds that identity through the other anchor's key view. A key the view does not know yet is skipped: no posit, nothing retracted. Within one build the referenced anchor loads before the tie.

Rejected: keying the subcategory by its Name, which the product row lacks; mapping it would need a join in conform, which is the combining layer's work (#11). Rejected: creating the subcategory's identity from the product's reference, which lets two mappings write one anchor's key.

## Consequences

Products are pulled whole every run (A1), so a skipped reference is posited by the next build that finds the subcategory, at the product row's own ChangedAt. A source whose ids are reused or renumbered breaks the key (A32). A second source of subcategories would need a key both share.
