# Overview

Three independently-built, LLM-assisted resources mine drug→disease **indications**:
**MEDIC** (approved indications from FDA / EMA / PMDA labels), **DAKP** (the Drug
Approvals KP — its `approved_for_condition` edges, from DailyMed / Drugs@FDA), and
**dismech** (mechanism-driven, curated; only its CHEBI drug→disease subset). Where their
indications *overlap* we gain confidence; where they *diverge* we get a lead to triage.

DAKP also carries a large volume of **FAERS off-label use** — *observed* real-world use,
not approvals. That is **excluded from the headline** here (it isn't an indication) and
read separately on the [off-label view](./offlabel). Everything below is the
**indication-grade** comparison: MEDIC, DAKP-approved, and dismech.

All sources are compared **as peers** in MONDO-centric space: every CURIE is re-resolved
through the SRI Node Normalizer (the disease axis prefers the MONDO member of each
clique), and matching is **hierarchy-aware** — a pair counts as *related* when a source
has the same drug on a disease one–two MONDO is-a hops away.

```js
const summary = await FileAttachment("data/summary.json").json();
const ind = summary.indication;
const off = summary.offlabel;
const fmt = (n) => n.toLocaleString();
const sources = ind.sources;
const nSources = (combo) => combo.split(" + ").length;
const support = [1, 2, 3].map((k) => ({
  sources: k === 1 ? "1 source (unique)" : k === 3 ? "all 3 sources" : `${k} sources`,
  n: Object.entries(ind.combinations).filter(([c]) => nSources(c) === k)
    .reduce((a, [, n]) => a + n, 0),
}));
const universeN = support.reduce((a, s) => a + s.n, 0);
support.forEach((s, i) => { s.share = s.n / universeN; s.color = ["#bab0ac", "#6a9bd8", "#13315c"][i]; });
```

Every indication pair, grouped by **how many sources assert it**. **Agreement** (≥2
sources) is the higher-confidence core: ${fmt(ind.agree_2plus)} pairs, ${fmt(ind.agree_all)}
of them in all three. The flagship comparison, MEDIC ↔ DAKP-approved, shares
**${fmt(summary.medic_vs_dakp_onlabel.shared)}** pairs (Jaccard
${summary.medic_vs_dakp_onlabel.jaccard.toFixed(3)}; ${(summary.medic_vs_dakp_onlabel.of_dakp_onlabel_in_medic * 100).toFixed(0)}%
of DAKP-approved pairs are in MEDIC).

<div class="grid grid-cols-4">
  <div class="card">
    <h2>Indication universe</h2>
    <span class="big">${fmt(ind.universe)}</span>
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
    ${html`<div class="src-counts">${sources.map((s) => html`<div class="src-row"><span class="src-name">${s}</span><span class="src-n">${fmt(ind.source_pairs[s])}</span></div>`)}</div>`}
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

The same split, to scale — a **log axis** so the smaller agreement bands stay visible:

```js
Plot.plot({
  width,
  height: 150,
  marginLeft: 120,
  x: {label: "pairs (log scale)", type: "log", grid: true},
  y: {label: null, domain: support.map((s) => s.sources)},
  color: {type: "identity"},
  marks: [
    // x1:1 gives the bar a baseline; without it, barX has no valid left edge on a log scale
    Plot.barX(support, {y: "sources", x1: 1, x2: "n", fill: "color", tip: true,
      title: (d) => `${d.sources}\n${d.n.toLocaleString()} pairs (${(d.share * 100).toFixed(1)}%)`}),
    Plot.text(support, {y: "sources", x: "n", text: (d) => `${d.n.toLocaleString()} · ${(d.share * 100).toFixed(1)}%`, dx: 34, fontSize: 11}),
    Plot.ruleX([1]),
  ],
})
```

## Pairs by source combination

The detail behind the headline: each indication pair grouped by the **exact set** of
sources that assert it — an [UpSet-style](https://upset.app/) breakdown. So
`MEDIC + DAKP-approved` means pairs both have but dismech doesn't; `MEDIC` means
MEDIC-only. Blue bars are agreement (≥2 sources). Log scale, because the single-source
buckets dwarf the rest.

```js
const comboRows = Object.entries(ind.combinations)
  .map(([combo, n]) => ({combo, n, multi: combo.includes(" + ")}))
  .sort((a, b) => b.n - a.n);
```

```js
Plot.plot({
  width,
  marginLeft: 220,
  x: {label: "pairs (log scale)", type: "log", grid: true},
  y: {label: null, domain: comboRows.map((d) => d.combo)},
  color: {domain: [true, false], range: ["#4269d0", "#bab0ac"], legend: true, tickFormat: (d) => d ? "≥2 sources (agree)" : "single source"},
  marks: [
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

Exact-pair agreement between each pair of indication sources (Jaccard + raw shared count).

```js
const pw = Object.entries(ind.pairwise).map(([k, v]) => ({pair: k, shared: v.shared, jaccard: v.jaccard}));
```

```js
Inputs.table(pw, {
  columns: ["pair", "shared", "jaccard"],
  header: {pair: "Source pair", shared: "shared pairs", jaccard: "Jaccard"},
  sort: "shared",
  reverse: true,
})
```

## FAERS off-label use — context, not indications

DAKP additionally reports **${fmt(off.pairs)}** off-label drug→disease pairs from FAERS —
*observed* real-world use, not approvals — kept out of the headline above.
**${fmt(off.only)}** are off-label only (no source asserts them as an indication);
**${fmt(off.corroborated)}** coincide with an indication asserted elsewhere. Browse them,
framed as observations, on the [off-label view](./offlabel).

<div class="grid grid-cols-3">
  <div class="card">
    <h2>Off-label pairs</h2>
    <span class="big">${fmt(off.pairs)}</span>
    FAERS observed use
  </div>
  <div class="card">
    <h2>Off-label only</h2>
    <span class="big">${fmt(off.only)}</span>
    no indication anywhere
  </div>
  <div class="card">
    <h2>Coincide with an indication</h2>
    <span class="big">${fmt(off.corroborated)}</span>
    seen off-label *and* on-label
  </div>
</div>

Dig in: [drug coverage](./drugs) and [disease coverage](./diseases) for per-entity
rollups, [disagreements](./diff) for the triage queue, the [off-label view](./offlabel)
for FAERS observations, the [error taxonomy](./error-taxonomy) for the label-grounded
audit, and [methods](./methods).
