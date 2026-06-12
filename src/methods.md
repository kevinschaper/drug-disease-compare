# Methods

## What is compared

Three LLM-assisted drug→disease edge sets:

| | MEDIC (`medic-ingest`) | Drug Approvals KP (`dakp`) | dismech |
|---|---|---|---|
| Source material | regulatory labels: DailyMed + EU/Japan | FAERS reports + DailyMed | curated literature, mechanism-driven |
| Edge meaning | approved **indication** | observed **application** (incl. off-label) | curated **treatment** |
| Predicate(s) | `biolink:treats` | `applied_to_treat`, `treats`, `contraindicated_in` | `treats_or_applied_or_studied_to_treat` |
| Provenance per edge | blanket `PMID:41385096` | `clinical_approval_status`, `number_of_cases` | real per-edge PMIDs + `supporting_text` |
| Comparable edges | ~15.7k | ~74k | ~1.2k (CHEBI drug subset only) |

MeDIC is described in DeLuca *et al.*, *Nucleic Acids Research* 2026;54(D1):D1477–D1487.
dismech ships ~38k KGX edges; of its 7,424 treatment→disease edges, subjects are
mostly MAXO medical actions and NCIT procedures — only the **CHEBI drug subset**
(~1,173 edges, 447 drugs) is comparable here, kept via a Node-Normalizer drug-type
filter. Adding a feed is a one-line entry in `SOURCE_ORDER` (+ `DRUG_FILTERED` if its
"treatment" subjects mix drugs with non-drug modalities) plus a CLI loader.

## Pipeline

1. **Load & collapse predicate.** Every feed is flattened to a common edge shape.
   `treats`, `applied_to_treat`, and dismech's union
   `treats_or_applied_or_studied_to_treat` collapse to a single `treats` relation (we
   ignore the distinction). `contraindicated_in` is held apart as its opposite.

2. **Reconcile identifiers via Node Normalizer cliques.** Every drug and disease
   CURIE is re-resolved through the [SRI Node Normalizer](https://nodenormalization-sri.renci.org)
   (`conflate` + `drug_chemical_conflate` on). The feeds were each normalized
   *differently*, so re-resolving through one pass puts them in the same space.
   - **Drugs** → the clique-preferred CURIE. Feeds whose treatment subjects mix
     modalities (dismech: MAXO/NCIT) are filtered to **drug-typed** subjects via the
     clique's biolink types.
   - **Diseases** → the clique's **MONDO** member when one exists; otherwise the
     original term (usually HP). This undoes MONDO/HP same-name conflation. See
     [de-conflation](./deconflation).

3. **Build (drug, disease) pairs** per feed under the `treats` relation; aggregate
   DAKP's `clinical_approval_status` (approved beats off-label) + `number_of_cases`,
   and dismech's per-edge publication count.

4. **Per-source membership.** Each pair in the universe records, for every feed, a
   status: **exact**, **related** (the feed has the same drug on a disease ≤2 MONDO
   `subclass_of` hops away — a granularity difference, not a disagreement), or absent.
   MONDO closure comes from the release KGX `mondo_edges.tsv` / `mondo_nodes.tsv`.

5. **Scope-aware comparison.** Each feed has a disease **scope** — where its absence
   is a real signal vs "not covered." Broad feeds (MEDIC/DAKP) scope to the diseases
   they assert any drug for; dismech is disease-centric, so its scope is every disease
   it *curates* (the MONDO terms across all its edges, ~1,150), which is wider than the
   diseases it has drug edges for. Each pair carries a per-source `_scope` flag, so a
   "source-only" pair is only flagged where the other feed actually covers the disease.

6. **Emit.** One `pairs.parquet` holds the universe with per-source status + scope
   columns, queried client-side via DuckDB-WASM; coverage rollups and reports are JSON.

## Reading the overlap

**Agreement** is a pair exact in ≥2 feeds. The DAKP off-label split still governs the
reading: MEDIC and dismech are approved/curated indications, so a DAKP off-label pair
absent from them is *expected*, not an error — the fair MEDIC↔DAKP comparison
restricts DAKP to `approved_for_condition`. dismech is small and curated, so it
overlaps less in absolute terms but is high-provenance (every edge cites literature).

No resource is ground truth. A single-feed pair (with no exact *or* related match
elsewhere) is a **lead to triage** — a coverage gap or an extraction error — not a
verdict.

## What this does *not* yet do

- **Drug-axis hierarchy.** Matching is hierarchy-aware on the disease (MONDO) axis
  only. CHEBI/ATC drug-class relationships are not yet used, so a parent-drug vs
  child-drug difference reads as a disagreement.
- **MEDIC contraindications.** Not in the current indication export, so DAKP's
  contraindications have nothing to compare against ([contraindications](./contraindications)).
- **Node Normalizer version pinning.** DAKP baked in `node_norm_version 2025sep1`;
  our re-resolution uses the live endpoint. Pin a dated instance for strict
  reproducibility. Inputs are otherwise pinned with checksums in `data/MANIFEST.yaml`.

## Reproducing

```
just fetch       # download pinned inputs (MEDIC, DAKP, dismech, MONDO)
just normalize   # resolve every CURIE through the Node Normalizer (cached)
just build       # reconcile + compare -> src/data/* (pairs.parquet + JSON)
just dev         # preview the site locally
just site        # build the static site to dist/
```
