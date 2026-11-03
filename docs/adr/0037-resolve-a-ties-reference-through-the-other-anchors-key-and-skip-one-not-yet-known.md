# ADR-0037 — Resolve a tie's reference through the other anchor's key, and skip one not yet known

**Status:** Accepted (2026-11-03)

## Context

A Products row names its subcategory only by `ProductSubcategoryId`, the source's own id. ADR-0005 identifies an anchor by a surrogate found through its key view. The subcategory anchor must therefore be keyed by something the product row carries, and a product can name a subcategory whose own row has not landed yet.

## Decision

ProductSubcategory is keyed by the source's id, attribute `PS_SID_ProductSubcategory_SourceId`, its identifier route. The mapping that loads a tie names the column holding the other role's key; the load finds that identity through the posits of the other anchor's identifier attribute, as a key known by the product row's own PositedAt. A row whose key was not known by then is skipped: no posit, nothing retracted. Reading the key as known at the row's PositedAt, not as known now, gives one history however loads are grouped into builds. Within one build the referenced anchor loads before the tie.

Rejected: keying the subcategory by its Name, which the product row lacks; mapping it would need a join in conform, which is the combining layer's work (#11). Rejected: creating the subcategory's identity from the product's reference, which lets two mappings write one anchor's key.

## Consequences

Products are pulled whole every run (A1), so a skipped reference is posited by the next build whose product rows land after the subcategory, at the product row's own ChangedAt. This holds while the referenced resource lands before the one naming it (A33); a subcategories load landed later under an older load id is not read back into product rows already built. A skipped row also takes no part in the contradiction check of its load, so two values in one load, one of them naming an unknown key, posit the known one. A source whose ids are reused or renumbered breaks the key (A32). A second source of subcategories would need a key both share.
