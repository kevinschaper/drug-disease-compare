# Drug coverage

Per-drug rollup across all three sources, after canonicalizing every drug to its Node
Normalizer clique-preferred CURIE. For each drug: how many distinct diseases each
source asserts (exact pairs), how many are **shared** (exact in ≥2 sources), and the
MEDIC↔DAKP per-drug Jaccard. Drugs with high counts but low overlap are good places
to look for systematic extraction differences.

```js
const byDrug = await FileAttachment("data/by_drug.json").json();
const summary = await FileAttachment("data/summary.json").json();
const sources = summary.sources;
const labelOfDrug = new Map(byDrug.map((d) => [d.drug, d.drug_label]));
```

<div class="grid grid-cols-3">
  <div class="card">
    <h2>Drugs</h2>
    <span class="big">${byDrug.length.toLocaleString()}</span> across all sources
  </div>
  <div class="card">
    <h2>In MEDIC & DAKP</h2>
    <span class="big">${byDrug.filter((d) => d.medic > 0 && d.dakp > 0).length.toLocaleString()}</span> drugs
  </div>
  <div class="card">
    <h2>In dismech</h2>
    <span class="big">${byDrug.filter((d) => d.dismech > 0).length.toLocaleString()}</span> drugs
  </div>
</div>

## Disease counts per drug — pick any two sources

Each point is a drug: diseases asserted by one source (x) vs another (y); the scatter is
inherently a pairwise view, so choose which two. Color is how many of that drug's
pairs are shared across **≥2 sources**.

```js
const xSrc = view(Inputs.select(sources, {label: "x axis", value: sources[0]}));
const ySrc = view(Inputs.select(sources, {label: "y axis", value: sources[1] ?? sources[0]}));
```

```js
const both = byDrug.filter((d) => d[xSrc] > 0 && d[ySrc] > 0);
```

```js
Plot.plot({
  width,
  grid: true,
  x: {label: `${xSrc} diseases per drug`, type: "sqrt"},
  y: {label: `${ySrc} diseases per drug`, type: "sqrt"},
  color: {label: "shared (≥2 sources)", scheme: "BuYlRd", legend: true},
  marks: [
    Plot.dot(both, {
      x: (d) => d[xSrc], y: (d) => d[ySrc], r: 3, fill: "shared", fillOpacity: 0.7,
      channels: {drug: "drug_label", shared: "shared"}, tip: true,
    }),
  ],
})
```

## Browse drugs

Click a drug to open its detail page.

```js
const drugSearch = view(Inputs.search(byDrug, {placeholder: "search by drug…"}));
```

```js
Inputs.table(drugSearch, {
  columns: ["drug", ...sources, "shared", "jaccard"],
  header: {drug: "Drug", medic: "MEDIC", dakp: "DAKP", dismech: "dismech", shared: "shared (≥2)", jaccard: "MEDIC∩DAKP J"},
  format: {
    drug: (cid) => html`<a href="drug?id=${encodeURIComponent(cid)}">${labelOfDrug.get(cid) ?? cid}</a> <span class="small muted">${cid}</span>`,
  },
  sort: "shared",
  reverse: true,
  rows: 18,
  width,
})
```
