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
filter. Adding a source is a one-line entry in `SOURCE_ORDER` (+ `DRUG_FILTERED` if its
"treatment" subjects mix drugs with non-drug modalities) plus a CLI loader.

## Pipeline

1. **Load & collapse predicate.** Every source is flattened to a common edge shape.
   `treats`, `applied_to_treat`, and dismech's union
   `treats_or_applied_or_studied_to_treat` collapse to a single `treats` relation (we
   ignore the distinction). `contraindicated_in` is held apart as its opposite.

2. **Reconcile identifiers via Node Normalizer cliques.** Every drug and disease
   CURIE is re-resolved through the [SRI Node Normalizer](https://nodenormalization-sri.renci.org)
   (`conflate` + `drug_chemical_conflate` on). The sources were each normalized
   *differently*, so re-resolving through one pass puts them in the same space.
   - **Drugs** → the clique-preferred CURIE. Sources whose treatment subjects mix
     modalities (dismech: MAXO/NCIT) are filtered to **drug-typed** subjects via the
     clique's biolink types.
   - **Diseases** → the clique's **MONDO** member when one exists; otherwise the
     original term (usually HP). This undoes MONDO/HP same-name conflation. See
     [de-conflation](./deconflation).

3. **Build (drug, disease) pairs** per source under the `treats` relation; aggregate
   DAKP's `clinical_approval_status` (approved beats off-label) + `number_of_cases`,
   and dismech's per-edge publication count.

4. **Per-source membership.** Each pair in the universe records, for every source, a
   status: **exact**, **related** (the source has the same drug on a disease ≤2 MONDO
   `subclass_of` hops away — a granularity difference, not a disagreement), or absent.
   MONDO closure comes from the release KGX `mondo_edges.tsv` / `mondo_nodes.tsv`.

5. **Scope-aware comparison.** Each source has a disease **scope** — where its absence
   is a real signal vs "not covered." Broad sources (MEDIC/DAKP) scope to the diseases
   they assert any drug for; dismech is disease-centric, so its scope is every disease
   it *curates* (the MONDO terms across all its edges, ~1,150), which is wider than the
   diseases it has drug edges for. Each pair carries a per-source `_scope` flag, so a
   "source-only" pair is only flagged where the other source actually covers the disease.

6. **Emit.** One `pairs.parquet` holds the universe with per-source status + scope
   columns, queried client-side via DuckDB-WASM; coverage rollups and reports are JSON.

## Reading the overlap

**Agreement** is a pair exact in ≥2 sources. The DAKP off-label split still governs the
reading: MEDIC and dismech are approved/curated indications, so a DAKP off-label pair
absent from them is *expected*, not an error — the fair MEDIC↔DAKP comparison
restricts DAKP to `approved_for_condition`. dismech is small and curated, so it
overlaps less in absolute terms but is high-provenance (every edge cites literature).

No resource is ground truth. A single-source pair (with no exact *or* related match
elsewhere) is a **lead to triage** — a coverage gap or an extraction error — not a
verdict.

## Drug collapse

The Node Normalizer deliberately keeps a prodrug separate from its active moiety, a salt
from its parent, and a CHEBI record from a UNII record it can't equate — so the *same drug*
recorded two ways (dabigatran vs dabigatran etexilate; CHEBI- vs UNII-semaglutide;
ranitidine vs (Z)-ranitidine) reads as a cross-source disagreement. To catch this, each
canonical drug is also mapped to its **active moiety** (FDA/GSRS, pivoting on UNII), with a
guard that rejects bare-ion moieties (metal cations, NO — formula < 3 heavy atoms) that
would over-merge therapeutically distinct products (iron salts, nitrovasodilators).

This collapse is **our inference, not a source's assertion**, so it never rewrites an edge
or counts as exact agreement. It lives in its own columns (`drug_group`, `n_group`,
`drug_note`): a same-moiety match on the same disease is a flagged drug-axis bridge, exactly
parallel to a disease is-a `related`. It recovers cross-source agreements that were
hidden by identifier mismatch (reported as `moiety.new_agreements` in the summary), surfaced
on [disagreements](./diff) under "same drug, different identifier." Compared three grouping
authorities (active moiety, RxNorm ingredient, ChEBI functional parent) before choosing
active moiety — see `experiments/drug_collapse.py`. Run with `just build` (default) or
`uv run … cli build --no-drug-collapse` to disable.

## What this does *not* yet do

- **Drug-axis hierarchy.** Collapse handles same-drug *variants* (salt/ester/prodrug/
  stereoisomer, above) but not true drug-*class* relationships: a CHEBI/ATC parent-class vs
  child-drug difference still reads as a disagreement.
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
