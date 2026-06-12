# drug-disease-compare

Hierarchy-aware, **scope-aware** comparison of independently-built, LLM-assisted
resources that mine drug→disease edges — currently **MEDIC**, the **Drug Approvals KP
(DAKP)**, and **dismech**. Because their inputs overlap, their indication edges should
converge; where they diverge, the difference is a lead to triage (a coverage gap, or
an extraction error). Renders to a GitHub Pages site built with
[Observable Framework](https://observablehq.com/framework).

Sibling project, same frontend stack: [hpoa-compare](https://github.com/kevinschaper/hpoa-compare).

## The comparison

- **Feeds.** MEDIC (`monarch-initiative/medic-ingest`, approved indications from
  DailyMed + EU/Japan labels), DAKP (`infores:multiomics-drugapprovals`, FAERS +
  DailyMed including off-label use), and dismech (`monarch-initiative/dismech`,
  curated/mechanism-driven — its CHEBI drug→disease subset). Adding a feed is one
  entry in `SOURCE_ORDER` plus a loader.
- **Reconciliation.** Every drug/disease CURIE is re-resolved through the SRI Node
  Normalizer so all feeds share one identifier space. The disease axis is
  **MONDO-centric**: prefer the MONDO member of each clique, keep HP only when no
  MONDO exists — undoing MONDO/HP same-name conflation.
- **Per-source membership.** Each (drug, disease) pair records, per feed, a status:
  `exact`, `related` (same drug ≤2 MONDO is-a hops away), or absent. "Agreement" is a
  pair exact in ≥2 feeds.
- **Scope-aware.** A feed's *absence* only counts where it covers the disease. dismech
  is disease-centric (~1,150 curated diseases), so it's read on its own terms — how
  many of its edges the broad feeds corroborate, and what's novel to it.

See [`src/methods.md`](src/methods.md) for the full methodology.

## Layout

```
data/MANIFEST.yaml              pinned inputs + checksums
data/inputs/                    downloaded sources (gitignored)
pipeline/drug_edge_compare/     load -> nodenorm -> reconcile -> mondo -> compare -> cli
pipeline/tests/                 pytest unit tests
src/                            Observable Framework site (pages + generated data/)
src/data/pairs.parquet          per-pair table, queried client-side via DuckDB-WASM
.github/workflows/deploy.yml    GitHub Pages deploy (renders committed src/data/)
```

## Build

Requires [`uv`](https://docs.astral.sh/uv/), Node 18+, `zstd`, and (optionally)
[`just`](https://github.com/casey/just).

```
just fetch       # download pinned inputs (MEDIC, DAKP, dismech, MONDO)
just normalize   # resolve every CURIE through the Node Normalizer (cached locally)
just build       # reconcile + compare -> src/data/ (pairs.parquet + JSON)
just test        # run the pipeline unit tests
just dev         # preview the site at localhost
just site        # build the static site to dist/
```

CI only renders the committed `src/data/`; regenerate locally with `just build`
(needs the inputs + a Node Normalizer pass) and commit the result.

## Deployment

`.github/workflows/deploy.yml` builds and publishes to GitHub Pages on push to
`main` (Pages source: GitHub Actions).
