# Methods

## What is compared

Three LLM-assisted drug→disease edge sets, each at its latest release (the previous
releases are kept to characterize [version changes](./changes)):

| | MEDIC (MeDIC redesign) | Drug Approvals KP (`dakp`) | dismech |
|---|---|---|---|
| Release | local build 2026-10-01 (`medic2@0453fd8`, MeDIC 1.0.1) — was medic-ingest 2026-06-19 | 1.16.0 (Hugging Face) — was rtx.ai 2026_04_21 | v0.1.42 — was v0.1.30 |
| Source material | regulatory labels: FDA DailyMed, EMA, PMDA, CDSCO | FAERS reports + DailyMed + EMA/EPAR | curated literature, mechanism-driven |
| Edge meaning | approved **indication** / **contraindication** | observed **application** (incl. off-label) / contraindication | curated **treatment** |
| Predicate(s) | `treats`, `contraindicated_in` | `applied_to_treat`, `treats`, `contraindicated_in` | `treats_or_applied_or_studied_to_treat` |
| Provenance per edge | one edge per regulator assertion: authority, verbatim label text, reliability tier | `clinical_approval_status`, `number_of_cases`, SPL setids, application numbers | real per-edge PMIDs + `supporting_text` |
| Comparable edges | ~14.7k (~10.2k distinct triples) | ~132k | ~3.4k (CHEBI drug subset only) |

MeDIC is described in DeLuca *et al.*, *Nucleic Acids Research* 2026;54(D1):D1477–D1487;
the redesign is not yet a published release. dismech ships ~105k KGX edges; of its
~20k treatment→disease edges, most subjects are NCIT procedures/therapies — only the
**CHEBI drug subset** is comparable here, kept via a Node-Normalizer drug-type filter. Adding a source is a one-line entry in `SOURCE_ORDER` (+ `DRUG_FILTERED` if its
"treatment" subjects mix drugs with non-drug modalities) plus a CLI loader.

## Pipeline

1. **Load & collapse predicate.** Every source is flattened to a common edge shape.
   `treats`, `applied_to_treat`, and dismech's union
   `treats_or_applied_or_studied_to_treat` collapse to a single `treats` relation (we
   ignore the distinction). `contraindicated_in` is held apart as its opposite. MEDIC's
   handful of research predicates (`in_clinical_trials_for`, `studied_to_treat`) are
   skipped. MEDIC's per-assertion edges are folded to one pair, keeping each regulator's
   label text and the best reliability tier.

2. **Reconcile identifiers via Node Normalizer cliques.** Every drug and disease
   CURIE is re-resolved through the [SRI Node Normalizer](https://nodenormalization-sri.renci.org)
   (`conflate` + `drug_chemical_conflate` on). The sources were each normalized
   *differently*, so re-resolving through one pass puts them in the same space.
   - **Drugs** → the clique-preferred CURIE. Sources whose treatment subjects mix
     modalities (dismech: NCIT) are filtered to **drug-typed** subjects via the
     clique's biolink types.
   - **Unresolvable drug ids are repaired by exact name.** The MeDIC redesign grounds
     many biologics to ChEBI ids minted after the Node Normalizer's build (e.g.
     `CHEBI:749494` adalimumab) or to DRON; unrepaired, ~28% of its treats edges would
     match nothing. For a drug CURIE the Node Normalizer returns *nothing* for, we look
     the source's own node name up as an **exact** RxNorm concept (`search=0`, single
     hit only) and use that RXCUI's clique. This never touches a CURIE the Node
     Normalizer resolves, so it repairs identifiers rather than merging drugs; the
     repaired count is reported (`summary.repaired_drugs`).
   - **Diseases** → the clique-preferred CURIE, which is MONDO-centric by
     construction (with conflation on, NodeNorm prefers a clique's MONDO whenever
     one exists; terms with no MONDO equivalent keep their preferred CURIE, usually HP).

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

The headline comparison is **indication-grade**: MEDIC, **DAKP-approved**
(`approved_for_condition`), and dismech. DAKP `off_label_use` comes from FAERS — *observed*
real-world use, not an approval, and confounded by indication — so it is **excluded from
the headline universe, agreement, and combinations** and read separately on the
[off-label view](./offlabel). **Agreement** is a pair exact in ≥2 of the indication-grade
sources. dismech is small and curated, so it overlaps less in absolute terms but is
high-provenance (every edge cites literature).

No resource is ground truth. A single-source pair (with no exact *or* related match
elsewhere) is a **lead to triage** — a coverage gap or an extraction error — not a
verdict.

## Drug collapse

The Node Normalizer deliberately keeps a prodrug separate from its active moiety, a salt
from its parent, and a CHEBI record from a UNII record it can't equate — so the *same drug*
recorded two ways (dabigatran vs dabigatran etexilate; CHEBI- vs UNII-semaglutide;
ranitidine vs (Z)-ranitidine) reads as a cross-source disagreement. To catch this, each
canonical drug is also mapped to its **active moiety** (FDA/GSRS, pivoting on UNII — or,
for a clique with no UNII/RXCUI such as DAKP 1.16's brand-name UMLS concepts, an exact
RxNorm name → single ingredient → UNII), with a
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
- **Contraindication hierarchy.** MEDIC ↔ DAKP [contraindications](./contraindications)
  are compared exactly; an is-a neighbour isn't treated as related, since a
  contraindication doesn't propagate along the disease hierarchy.
- **Node Normalizer version pinning.** DAKP baked in `node_norm_version 2025sep1`;
  our re-resolution uses the live endpoint. Pin a dated instance for strict
  reproducibility. Inputs are otherwise pinned with checksums in `data/MANIFEST.yaml`.

## Version changes

`just changes` loads each source's previous and latest release, reconciles both through
the same Node Normalizer + MONDO snapshot, and diffs them per lens (MEDIC indications /
contraindications; DAKP approved / off-label / contraindications; dismech indications).
Each added or removed canonical pair gets a reason — **re-grounded** (same pair under a
same-moiety sibling CURIE), **re-grained** (same drug ≤2 MONDO hops away), **status
flip** (DAKP approved ↔ off-label), **drug new/dropped**, or **changed**. A 2×2
*agreement trajectory* (each source pair at previous/latest × previous/latest) attributes
a shift in head-to-head overlap to the source whose release moved it.

## Reproducing

```
just fetch       # download pinned inputs (old + new of each source; MONDO)
just sync-medic  # copy the latest local MeDIC KGX export in as "new" MEDIC
just normalize   # resolve every CURIE through the Node Normalizer (cached)
just build       # reconcile + compare -> src/data/* (pairs.parquet + JSON)
just changes     # characterize each source's old -> new change -> src/data/changes.*
just dev         # preview the site locally
just site        # build the static site to dist/
```
