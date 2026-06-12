# Disease coverage

Per-disease rollup across all three feeds, after MONDO-centric reconciliation. For
each disease: how many distinct **drugs** each feed asserts, how many are **shared**
(exact in ≥2 feeds), and the MEDIC↔DAKP per-disease Jaccard. Coverage also rolls up
the **MONDO is-a hierarchy** into recognizable disease areas you can drill into.

```js
const byDisease = await FileAttachment("data/by_disease.json").json();
const diseaseAreas = await FileAttachment("data/disease_areas.json").json();
const summary = await FileAttachment("data/summary.json").json();
const sources = summary.sources;
const labelOfDisease = new Map(byDisease.map((d) => [d.disease, d.disease_label]));
```

<div class="grid grid-cols-3">
  <div class="card">
    <h2>Diseases</h2>
    <span class="big">${byDisease.length.toLocaleString()}</span> across both feeds
  </div>
  <div class="card">
    <h2>In MEDIC & DAKP / in dismech</h2>
    <span class="big">${byDisease.filter((d) => d.medic > 0 && d.dakp > 0).length.toLocaleString()} / ${byDisease.filter((d) => d.dismech > 0).length.toLocaleString()}</span> diseases
  </div>
  <div class="card">
    <h2>MONDO / non-MONDO</h2>
    <span class="big">${byDisease.filter((d) => d.disease_prefix === "MONDO").length.toLocaleString()} / ${byDisease.filter((d) => d.disease_prefix !== "MONDO").length.toLocaleString()}</span>
    <div class="small muted">non-MONDO = HP/UMLS/… with no MONDO in clique</div>
  </div>
</div>

## Coverage by MONDO disease area

Each disease is rolled up to its area(s) one level below MONDO's
`disease by body system / process / etiology` axes. A disease with multiple parents
(MONDO multiple-inheritance) is counted under each area, so area totals can exceed
the global pair count — these are *where the pairs concentrate*, not a partition.
Bars are nested from the same origin: DAKP (light) ⊃ MEDIC (mid) ⊃ shared (dark).

```js
const areaTop = diseaseAreas.slice(0, 22);
```

```js
Plot.plot({
  width,
  marginLeft: 210,
  height: 560,
  x: {label: "drug–disease pairs", grid: true},
  y: {label: null, domain: areaTop.map((a) => a.label)},
  marks: [
    Plot.barX(areaTop, {y: "label", x: "dakp", fill: "#b6cbe8"}),
    Plot.barX(areaTop, {y: "label", x: "medic", fill: "#4269d0"}),
    Plot.barX(areaTop, {y: "label", x: "shared", fill: "#13315c"}),
    Plot.text(areaTop, {y: "label", x: "dakp", text: (d) => d.dakp.toLocaleString(), dx: 16, fontSize: 10}),
    // transparent full-width hit area so hovering anywhere on a row shows all values
    Plot.barX(areaTop, {
      y: "label", x: "dakp", fillOpacity: 0, tip: true,
      title: (d) =>
        `${d.label}\nDAKP ${d.dakp.toLocaleString()} pairs\nMEDIC ${d.medic.toLocaleString()} pairs\n` +
        `dismech ${d.dismech.toLocaleString()}\nshared(≥2) ${d.shared.toLocaleString()}\nJaccard ${d.jaccard}\n${d.diseases.toLocaleString()} diseases`,
    }),
    Plot.ruleX([0]),
  ],
})
```

<div class="small muted">
  <span style="color:#b6cbe8">■</span> DAKP &nbsp;
  <span style="color:#4269d0">■</span> MEDIC &nbsp;
  <span style="color:#13315c">■</span> shared
</div>

Per-area agreement (Jaccard) — areas where the two feeds converge most vs least.

```js
Plot.plot({
  width,
  marginLeft: 210,
  height: 560,
  x: {label: "per-area Jaccard", grid: true, domain: [0, Math.max(...diseaseAreas.map((a) => a.jaccard)) * 1.15]},
  y: {label: null, domain: [...diseaseAreas].sort((a, b) => b.jaccard - a.jaccard).slice(0, 22).map((a) => a.label)},
  marks: [
    Plot.barX(diseaseAreas, {
      y: "label", x: "jaccard", fill: "#4269d0", sort: {y: "x", reverse: true, limit: 22}, tip: true,
      title: (d) =>
        `${d.label}\nJaccard ${d.jaccard}\nMEDIC ${d.medic.toLocaleString()} | DAKP ${d.dakp.toLocaleString()} | shared ${d.shared.toLocaleString()}`,
    }),
    Plot.ruleX([0]),
  ],
})
```

```js
Inputs.table(diseaseAreas, {
  columns: ["label", "diseases", "medic", "dakp", "dismech", "shared", "jaccard"],
  header: {label: "Disease area", diseases: "diseases", medic: "MEDIC", dakp: "DAKP", dismech: "dismech", shared: "shared (≥2)", jaccard: "Jaccard"},
  sort: "dakp",
  reverse: true,
  rows: 12,
  width,
})
```

## Drill down by area

Pick a disease area to scope the per-disease table to it, then search within.

```js
const areaChoices = ["All areas", ...diseaseAreas.map((a) => a.label)];
const area = view(Inputs.select(areaChoices, {label: "Disease area", value: "All areas"}));
```

```js
const scoped = area === "All areas"
  ? byDisease
  : byDisease.filter((d) => (d.categories ?? []).includes(area));
```

Click a disease to open its detail page.

```js
const diseaseSearch = view(Inputs.search(scoped, {placeholder: `search ${scoped.length.toLocaleString()} diseases…`}));
```

```js
Inputs.table(diseaseSearch, {
  columns: ["disease", "disease_prefix", "medic", "dakp", "dismech", "shared", "jaccard"],
  header: {disease: "Disease", disease_prefix: "Space", medic: "MEDIC", dakp: "DAKP", dismech: "dismech", shared: "shared (≥2)", jaccard: "MEDIC∩DAKP J"},
  format: {
    disease: (cid) => html`<a href="disease?id=${encodeURIComponent(cid)}">${labelOfDisease.get(cid) ?? cid}</a> <span class="small muted">${cid}</span>`,
  },
  sort: "shared",
  reverse: true,
  rows: 18,
  width,
})
```

## Drugs per disease — pick any two feeds

Each point is a disease: drugs asserted by one feed (x) vs another (y); color is how
many of that disease's pairs are shared across **≥2 feeds**. Diseases off the diagonal
carry very different drug sets between the two chosen feeds.

```js
const xSrcD = view(Inputs.select(sources, {label: "x axis", value: sources[0]}));
const ySrcD = view(Inputs.select(sources, {label: "y axis", value: sources[1] ?? sources[0]}));
```

```js
const bothD = byDisease.filter((d) => d[xSrcD] > 0 && d[ySrcD] > 0);
```

```js
Plot.plot({
  width,
  grid: true,
  x: {label: `${xSrcD} drugs per disease`, type: "sqrt"},
  y: {label: `${ySrcD} drugs per disease`, type: "sqrt"},
  color: {label: "shared (≥2 feeds)", scheme: "BuYlRd", legend: true},
  marks: [
    Plot.dot(bothD, {
      x: (d) => d[xSrcD], y: (d) => d[ySrcD], r: 3, fill: "shared", fillOpacity: 0.7,
      channels: {disease: "disease_label", shared: "shared"}, tip: true,
    }),
  ],
})
```
