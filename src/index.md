# Overview

Three independently-built, LLM-assisted resources mine drug→disease edges:
**MEDIC** (approved indications from regulatory labels), the **Drug Approvals KP**
(DAKP — FAERS + DailyMed, including off-label use), and **dismech** (mechanism-driven,
curated; only its CHEMBL/CHEBI drug→disease edges are used — its MAXO/NCIT medical
actions are filtered out). Where their indication edges *overlap* we gain confidence;
where they *diverge* we get a lead to triage.

All sources are compared **as peers** in MONDO-centric space: every drug/disease CURIE
is re-resolved through the SRI Node Normalizer (disease axis prefers the MONDO member
of each clique), and matching is **hierarchy-aware** — a pair counts as *related* when
a source has the same drug on a disease one–two MONDO is-a hops away. One caveat
governs the reading: **DAKP includes off-label use; MEDIC and dismech are approved
indications only**, so DAKP's off-label edges are expected to be absent from the
others, not errors.

```js
const summary = await FileAttachment("data/summary.json").json();
const fmt = (n) => n.toLocaleString();
const sources = summary.sources;
const nSources = (combo) => combo.split("+").length;
const support = [1, 2, 3].map((k) => ({
  sources: k === 1 ? "1 source (unique)" : k === 3 ? "all 3 sources" : `${k} sources`,
  n: Object.entries(summary.combinations).filter(([c]) => nSources(c) === k)
    .reduce((a, [, n]) => a + n, 0),
}));
const universeN = support.reduce((a, s) => a + s.n, 0);
support.forEach((s, i) => { s.share = s.n / universeN; s.color = ["#bab0ac", "#6a9bd8", "#13315c"][i]; });
```

Every drug→disease pair, grouped by **how many sources assert it**. Most are unique to
one source — overwhelmingly DAKP's off-label use, which MEDIC and dismech (approved
indications only) don't carry. **Agreement** (≥2 sources) is the smaller,
higher-confidence core: ${fmt(summary.agree_2plus)} pairs, ${fmt(summary.agree_all)} of
them in all three.

<div class="grid grid-cols-4">
  <div class="card">
    <h2>Pair universe</h2>
    <span class="big">${fmt(summary.universe)}</span>
    distinct (drug, disease) pairs
  </div>
  <div class="card">
    <h2>Unique — 1 source</h2>
    <span class="big">${fmt(support[0].n)}</span>
    ${(support[0].share * 100).toFixed(0)}% of pairs
  </div>
  <div class="card">
    <h2>Backed by 2 sources</h2>
    <span class="big">${fmt(support[1].n)}</span>
    ${(support[1].share * 100).toFixed(1)}% of pairs
  </div>
  <div class="card">
    <h2>Backed by all 3</h2>
    <span class="big">${fmt(support[2].n)}</span>
    ${(support[2].share * 100).toFixed(1)}% of pairs
  </div>
</div>

<div class="grid grid-cols-4">
  <div class="card">
    <h2>Pairs per source</h2>
    ${html`<div class="src-counts">${sources.map((s) => html`<div class="src-row"><span class="src-name">${s}</span><span class="src-n">${fmt(summary.source_pairs[s])}</span></div>`)}</div>`}
  </div>
</div>

<style>
.src-counts { margin-top: 0.35rem; }
.src-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 1rem;
  line-height: 1.7;
  border-bottom: 1px solid color-mix(in srgb, currentColor 8%, transparent);
}
.src-row:last-child { border-bottom: none; }
.src-name { color: var(--theme-foreground-muted, #6b7280); }
.src-n { font-weight: 600; font-variant-numeric: tabular-nums; }
</style>

The same split, to scale — a **log axis** so the small agreement bands stay visible
(single-source pairs outnumber agreement by ~20×):

```js
Plot.plot({
  width,
  height: 150,
  marginLeft: 120,
  x: {label: "pairs (log scale)", type: "log", grid: true},
  y: {label: null, domain: support.map((s) => s.sources)},
  color: {type: "identity"},
  marks: [
    // x1:1 gives the bar a baseline; without it, barX has no valid left edge on a log scale and won't draw
    Plot.barX(support, {y: "sources", x1: 1, x2: "n", fill: "color", tip: true,
      title: (d) => `${d.sources}\n${d.n.toLocaleString()} pairs (${(d.share * 100).toFixed(1)}%)`}),
    Plot.text(support, {y: "sources", x: "n", text: (d) => `${d.n.toLocaleString()} · ${(d.share * 100).toFixed(1)}%`, dx: 34, fontSize: 11}),
    Plot.ruleX([1]),
  ],
})
```

## Pairs by source combination

The detail behind the headline: each pair grouped by the **exact set** of sources that
assert it — an [UpSet-style](https://upset.app/) breakdown. So `medic+dakp` means
pairs MEDIC and DAKP **both** have but dismech does **not**; `medic` means MEDIC-only.
Blue bars are agreement (≥2 sources). Log scale, because the single-source buckets dwarf
the rest.

```js
const comboRows = Object.entries(summary.combinations)
  .map(([combo, n]) => ({combo, n, multi: combo.includes("+")}))
  .sort((a, b) => b.n - a.n);
```

```js
Plot.plot({
  width,
  marginLeft: 150,
  x: {label: "pairs (log scale)", type: "log", grid: true},
  y: {label: null, domain: comboRows.map((d) => d.combo)},
  color: {domain: [true, false], range: ["#4269d0", "#bab0ac"], legend: true, tickFormat: (d) => d ? "≥2 sources (agree)" : "single source"},
  marks: [
    // x1:1 gives the bars a baseline on the log scale (otherwise they don't draw)
    Plot.barX(comboRows, {y: "combo", x1: 1, x2: "n", fill: "multi", tip: true,
      title: (d) => `${d.combo}\n${d.n.toLocaleString()} pairs`}),
    Plot.text(comboRows, {y: "combo", x: "n", text: (d) => d.n.toLocaleString(), dx: 18, fontSize: 10}),
    Plot.ruleX([1]),
  ],
})
```

Comparison is **scope-aware**: a source's *absence* only counts where it actually
covers the disease. This matters most for **dismech**, which is disease-centric and
curates only ~${summary.scope_diseases.dismech.toLocaleString()} diseases so far — so
its non-overlap is mostly "not curated yet," not disagreement. Read it on its own
terms on the [dismech lens](./dismech): of its ${summary.dismech.edges.toLocaleString()}
drug→disease edges, ${(summary.dismech.supported / summary.dismech.edges * 100).toFixed(0)}%
are corroborated by MEDIC/DAKP and ${summary.dismech.novel.toLocaleString()} are novel.

## Pairwise overlap

Exact-pair agreement between each pair of sources (Jaccard, and the raw shared count).
MEDIC↔DAKP is the mature comparison; dismech is small and curated, so it overlaps
less in absolute terms but is high-provenance (every edge carries literature support).

```js
const pw = Object.entries(summary.pairwise).map(([k, v]) => ({pair: k, shared: v.shared, jaccard: v.jaccard}));
```

```js
Inputs.table(pw, {
  columns: ["pair", "shared", "jaccard"],
  header: {pair: "Source pair", shared: "shared pairs", jaccard: "Jaccard"},
  sort: "shared",
  reverse: true,
})
```

## The fair MEDIC vs DAKP comparison

DAKP is dominated by off-label use, which MEDIC (label-indications only) can't
contain. Restricting DAKP to `approved_for_condition` is the apples-to-apples view.

<div class="grid grid-cols-3">
  <div class="card">
    <h2>DAKP on-label pairs</h2>
    <span class="big">${fmt(summary.dakp_onlabel_pairs)}</span>
    of ${fmt(summary.source_pairs.dakp)} DAKP pairs (rest off-label)
  </div>
  <div class="card">
    <h2>MEDIC ∩ DAKP on-label</h2>
    <span class="big">${fmt(summary.medic_vs_dakp_onlabel.shared)}</span>
    Jaccard ${summary.medic_vs_dakp_onlabel.jaccard.toFixed(3)}
  </div>
  <div class="card">
    <h2>of DAKP on-label, in MEDIC</h2>
    <span class="big">${(summary.medic_vs_dakp_onlabel.of_dakp_onlabel_in_medic * 100).toFixed(0)}%</span>
    of approved-for-condition pairs are in MEDIC
  </div>
</div>

Dig in: [drug coverage](./drugs) and [disease coverage](./diseases) for per-entity
rollups across all three sources, [disagreements](./diff) for the triage queue,
[de-conflation](./deconflation) for the MONDO/HP audit, and [methods](./methods).
