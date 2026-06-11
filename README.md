# drug-edge-comparison

Hierarchy-aware comparison of **MEDIC** and the **Drug Approvals KP (DAKP)** —
two independently-built, LLM-assisted resources that mine drug→disease edges from
overlapping regulatory source material. Because their inputs overlap, their
*indication* edges should converge; where they diverge, the difference is a lead to
triage (a coverage gap, or an extraction error). Renders to a GitHub Pages site
built with [Observable Framework](https://observablehq.com/framework).

Sibling project, same frontend stack: [hpoa-compare](https://github.com/kevinschaper/hpoa-compare).

## The comparison

- **Feeds.** MEDIC (`monarch-initiative/medic-ingest`, indications from DailyMed +
  EU/Japan labels) vs DAKP (`infores:multiomics-drugapprovals`, from FAERS +
  DailyMed, including off-label use).
- **Reconciliation.** Every drug/disease CURIE is re-resolved through the SRI Node
  Normalizer so both feeds share one identifier space. The disease axis is
  **MONDO-centric**: prefer the MONDO member of each clique, keep HP only when no
  MONDO exists — undoing MONDO/HP same-name conflation.
- **Matching.** Exact (drug, disease) pairs first, then MONDO is-a-neighbor pairs
  recovered as *related*. Predicates `treats`/`applied_to_treat` are collapsed;
  `contraindicated_in` is held apart.
- **Fair overlap.** DAKP is mostly off-label and MEDIC is label-indications only, so
  the headline number is MEDIC vs DAKP **on-label** (`approved_for_condition`).

See [`src/methods.md`](src/methods.md) for the full methodology.

## Layout

```
data/MANIFEST.yaml              pinned inputs + checksums
data/inputs/                    downloaded sources (gitignored)
pipeline/drug_edge_compare/     load -> nodenorm -> reconcile -> mondo -> compare -> cli
pipeline/tests/                 pytest unit tests
src/                            Observable Framework site (pages + generated data/*.json)
.github/workflows/deploy.yml    GitHub Pages deploy (renders committed src/data/*.json)
```

## Build

Requires [`uv`](https://docs.astral.sh/uv/), Node 18+, `zstd`, and (optionally)
[`just`](https://github.com/casey/just).

```
just fetch       # download pinned inputs (MEDIC, DAKP, MONDO)
just normalize   # resolve every CURIE through the Node Normalizer (cached locally)
just build       # reconcile + compare -> src/data/*.json
just test        # run the pipeline unit tests
just dev         # preview the site at localhost
just site        # build the static site to dist/
```

CI only renders the committed `src/data/*.json`; regenerate them locally with
`just build` (needs the inputs + a Node Normalizer pass) and commit the result.

## Deployment

`.github/workflows/deploy.yml` builds and publishes to GitHub Pages on push to
`main`. Enable Pages → "GitHub Actions" in the repo settings once.
