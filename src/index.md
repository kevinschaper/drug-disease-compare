# Overview

Three independently-built, LLM-assisted resources mine drug→disease edges:
**MEDIC** (approved indications from regulatory labels), the **Drug Approvals KP**
(DAKP — FAERS + DailyMed, including off-label use), and **dismech** (mechanism-driven,
curated; only its CHEMBL/CHEBI drug→disease edges are used — its MAXO/NCIT medical
actions are filtered out). Where their indication edges *overlap* we gain confidence;
where they *diverge* we get a lead to triage.

All feeds are compared **as peers** in MONDO-centric space: every drug/disease CURIE
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
```

<div class="grid grid-cols-4">
  <div class="card">
    <h2>Pair universe</h2>
    <span class="big">${fmt(summary.universe)}</span>
    distinct (drug, disease) pairs across all feeds
  </div>
  <div class="card">
    <h2>Agree (≥2 sources)</h2>
    <span class="big">${fmt(summary.agree_2plus)}</span>
    exact in two or more feeds
  </div>
  <div class="card">
    <h2>Agree (all three)</h2>
    <span class="big">${fmt(summary.agree_all)}</span>
    exact in MEDIC, DAKP and dismech
  </div>
  <div class="card">
    <h2>Per source</h2>
    <span class="big">${sources.map((s) => fmt(summary.source_pairs[s])).join(" · ")}</span>
    <div class="small muted">${sources.join(" · ")} pairs</div>
  </div>
</div>

## Where the feeds agree

Every (drug, disease) pair by the exact **combination of sources** that assert it.
DAKP-only dominates (it's mostly off-label use the others don't cover); the
agreement cells — anything spanning two or three feeds — are the confident core.

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
    Plot.barX(comboRows, {y: "combo", x: "n", fill: "multi", tip: true,
      title: (d) => `${d.combo}\n${d.n.toLocaleString()} pairs`}),
    Plot.text(comboRows, {y: "combo", x: "n", text: (d) => d.n.toLocaleString(), dx: 18, fontSize: 10}),
    Plot.ruleX([1]),
  ],
})
```

Comparison is **scope-aware**: a feed's *absence* only counts where it actually
covers the disease. This matters most for **dismech**, which is disease-centric and
curates only ~${summary.scope_diseases.dismech.toLocaleString()} diseases so far — so
its non-overlap is mostly "not curated yet," not disagreement. Read it on its own
terms on the [dismech lens](./dismech): of its ${summary.dismech.edges.toLocaleString()}
drug→disease edges, ${(summary.dismech.supported / summary.dismech.edges * 100).toFixed(0)}%
are corroborated by MEDIC/DAKP and ${summary.dismech.novel.toLocaleString()} are novel.

## Pairwise overlap

Exact-pair agreement between each pair of feeds (Jaccard, and the raw shared count).
MEDIC↔DAKP is the mature comparison; dismech is small and curated, so it overlaps
less in absolute terms but is high-provenance (every edge carries literature support).

```js
const pw = Object.entries(summary.pairwise).map(([k, v]) => ({pair: k, shared: v.shared, jaccard: v.jaccard}));
```

```js
Inputs.table(pw, {
  columns: ["pair", "shared", "jaccard"],
  header: {pair: "Feed pair", shared: "shared pairs", jaccard: "Jaccard"},
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
rollups across all three feeds, [disagreements](./diff) for the triage queue,
[de-conflation](./deconflation) for the MONDO/HP audit, and [methods](./methods).
