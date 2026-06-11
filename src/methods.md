# Methods

## What is compared

Two LLM-assisted drug→disease edge sets:

| | MEDIC (`medic-ingest`) | Drug Approvals KP (`dakp`) |
|---|---|---|
| Source material | regulatory labels: DailyMed + EU/Japan approvals | FAERS adverse-event reports + DailyMed |
| Edge meaning | approved **indication** | observed **application** (incl. off-label) |
| Predicate(s) | `biolink:treats` | `applied_to_treat`, `treats`, `contraindicated_in` |
| Provenance per edge | blanket `PMID:41385096` (the MeDIC paper) | `clinical_approval_status`, `number_of_cases`, FAERS/DailyMed sources |
| Format | TSV, ~15.7k edges | KGX JSONL, ~74k edges |

MeDIC is described in DeLuca *et al.*, *Nucleic Acids Research* 2026;54(D1):D1477–D1487.

## Pipeline

1. **Load & collapse predicate.** Both feeds are flattened to a common edge shape.
   `treats` and `applied_to_treat` collapse to a single `treats` relation (we ignore
   the distinction — it may be the wrong predicate choice on the medic-ingest side).
   `contraindicated_in` is held apart as its semantic opposite.

2. **Reconcile identifiers via Node Normalizer cliques.** Every drug and disease
   CURIE is re-resolved through the [SRI Node Normalizer](https://nodenormalization-sri.renci.org)
   (`conflate` + `drug_chemical_conflate` on). This is deliberate: both feeds were
   already normalized, but *differently* (MEDIC keeps more UMLS/NCIT; DAKP resolved
   further), so re-resolving both through one pass puts them in the same space.
   - **Drugs** → the clique-preferred CURIE.
   - **Diseases** → the clique's **MONDO** member when one exists; otherwise the
     original term (usually HP). This undoes MONDO/HP same-name conflation
     MONDO-centrically. See [de-conflation](./deconflation).

3. **Build (drug, disease) pairs** per feed under the `treats` relation; aggregate
   DAKP's `clinical_approval_status` per pair (approved beats off-label) and sum
   `number_of_cases`.

4. **Hierarchy-aware matching.** Exact pair agreement is counted first. Then,
   same-drug pairs whose diseases are within `LINEAGE_HOPS = 2` MONDO `subclass_of`
   steps of each other are recovered as **related** (a granularity difference, not a
   disagreement) before the remaining sets are reported as "only". MONDO closure
   comes from the release KGX `mondo_edges.tsv` / `mondo_nodes.tsv`.

5. **Bucket and emit.** Pairs land in agree / related / MEDIC-only / DAKP-only,
   with DAKP-only split by approval status. Artifacts are written to `src/data/*.json`.

## Reading the overlap

The headline number is the **on-label** Jaccard, not the all-treats Jaccard.
DAKP is dominated by off-label use; MEDIC is label-indications only, so off-label
DAKP-only edges are *expected* MEDIC-absences, not errors. Restricting DAKP to
`approved_for_condition` is the apples-to-apples comparison. The two directional
shares are reported separately and are expected to be asymmetric.

Neither resource is treated as ground truth. A MEDIC-only or DAKP-on-label-only pair
is a **lead to triage** — a coverage gap on one side, or an extraction error — not a
verdict against either feed.

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
just fetch       # download pinned inputs (MEDIC, DAKP, MONDO)
just normalize   # resolve every CURIE through the Node Normalizer (cached)
just build       # reconcile + compare -> src/data/*.json
just dev         # preview the site locally
just site        # build the static site to dist/
```
