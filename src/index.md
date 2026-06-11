# Overview

MEDIC and the Drug Approvals KP (DAKP) are **two independently-built, LLM-assisted
resources** that mine drug→disease edges. MEDIC reads regulatory drug labels
(DailyMed plus EU/Japan approvals) and extracts approved **indications**. DAKP draws
on FAERS adverse-event reports and DailyMed and records how drugs are **applied**,
including off-label use. Because their source material overlaps, we expect their
**indication** edges to converge — and where they diverge, the difference is a lead
worth triaging: a gap in one resource, or an extraction error.

Both feeds are compared **as peers** in MONDO-centric space. Every drug and disease
CURIE is re-resolved through the SRI Node Normalizer so the two land in the same
identifier space; the disease axis prefers the MONDO member of each normalizer
clique (keeping HP only when no MONDO exists). Matching is **hierarchy-aware** —
agreement is credited when the two annotate the same disease one MONDO is-a hop
apart. One caveat dominates the reading of the numbers: **DAKP includes off-label
use and MEDIC does not**, so DAKP's off-label edges are *expected* to be
MEDIC-absent and are not errors. The fair comparison is MEDIC vs DAKP **on-label**.

```js
const summary = await FileAttachment("data/summary.json").json();
const fmt = (n) => n.toLocaleString();
```

<div class="grid grid-cols-4">
  <div class="card">
    <h2>Pairs in agreement</h2>
    <span class="big">${fmt(summary.agree_exact)}</span>
    exact + ${fmt(summary.related_hierarchy)} via MONDO hierarchy
  </div>
  <div class="card">
    <h2>Overlap, on-label</h2>
    <span class="big">${summary.jaccard_onlabel.toFixed(2)}</span>
    Jaccard (all-treats ${summary.jaccard_all.toFixed(2)})
  </div>
  <div class="card">
    <h2>of MEDIC, in DAKP</h2>
    <span class="big">${(summary.medic_share_in_dakp * 100).toFixed(0)}%</span>
    of MEDIC indications also appear in DAKP
  </div>
  <div class="card">
    <h2>of DAKP on-label, in MEDIC</h2>
    <span class="big">${(summary.dakp_onlabel_share_in_medic * 100).toFixed(0)}%</span>
    of DAKP's approved-for-condition edges are in MEDIC
  </div>
</div>

## Why on-label is the fair comparison

Exact-ID matching across *all* DAKP edges understates agreement badly, because DAKP
is dominated by off-label use that MEDIC — being label-indications only — could
never contain. Restricting DAKP to `approved_for_condition` is the apples-to-apples
view, and the overlap roughly doubles.

```js
const overlapRows = [
  {scope: "all DAKP treats", value: summary.jaccard_all},
  {scope: "DAKP on-label only", value: summary.jaccard_onlabel},
];
```

```js
Plot.plot({
  width,
  marginLeft: 140,
  x: {label: "overlap (Jaccard)", domain: [0, Math.max(0.2, summary.jaccard_onlabel * 1.3)], grid: true},
  y: {label: null},
  marks: [
    Plot.barX(overlapRows, {y: "scope", x: "value", fill: "#4269d0"}),
    Plot.text(overlapRows, {y: "scope", x: "value", text: (d) => d.value.toFixed(3), dx: 18}),
    Plot.ruleX([0]),
  ],
})
```

## Where every drug→disease pair lands

The union of all `treats`/`applied_to_treat` pairs across both feeds, bucketed.
**Off-label DAKP-only** is the giant expected-divergence block; the actionable
disagreements are the much smaller **MEDIC-only** and **DAKP on-label-only** sets.

```js
const disposition = [
  {bucket: "agree (exact)", n: summary.agree_exact, kind: "agree"},
  {bucket: "related (hierarchy)", n: summary.related_hierarchy, kind: "agree"},
  {bucket: "MEDIC-only", n: summary.medic_only, kind: "disagree"},
  {bucket: "DAKP-only, on-label", n: summary.dakp_only_onlabel, kind: "disagree"},
  {bucket: "DAKP-only, off-label", n: summary.dakp_only_offlabel, kind: "expected"},
];
```

```js
Plot.plot({
  width,
  marginLeft: 160,
  x: {label: "pairs (log scale)", type: "log", grid: true},
  y: {label: null, domain: disposition.map((d) => d.bucket)},
  color: {domain: ["agree", "disagree", "expected"], range: ["#4269d0", "#e15759", "#bab0ac"], legend: true},
  marks: [
    Plot.barX(disposition, {y: "bucket", x: "n", fill: "kind"}),
    Plot.text(disposition, {y: "bucket", x: "n", text: (d) => d.n.toLocaleString(), dx: 22}),
    Plot.ruleX([1]),
  ],
})
```

The disagreements are where to look for errors: see [disagreements](./diff) for the
MEDIC-only and DAKP-on-label-only pairs, [drug coverage](./drugs) for a per-drug
rollup, [de-conflation](./deconflation) for the MONDO/HP normalization audit, and
[methods](./methods) for exactly what is and isn't compared.
