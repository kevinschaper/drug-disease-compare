# Drug coverage

Per-drug rollup across both feeds, after canonicalizing every drug to its Node
Normalizer clique-preferred CURIE. For each drug: how many distinct diseases MEDIC
asserts, how many DAKP asserts (all `treats`/`applied_to_treat`), how many they
**share** exactly, and the per-drug Jaccard. Drugs with high counts on both sides
but low overlap are good places to look for systematic extraction differences.

```js
const byDrug = await FileAttachment("data/by_drug.json").json();
const labelOfDrug = new Map(byDrug.map((d) => [d.drug, d.drug_label]));
```

<div class="grid grid-cols-3">
  <div class="card">
    <h2>Drugs</h2>
    <span class="big">${byDrug.length.toLocaleString()}</span> across both feeds
  </div>
  <div class="card">
    <h2>In both feeds</h2>
    <span class="big">${byDrug.filter((d) => d.medic > 0 && d.dakp > 0).length.toLocaleString()}</span> drugs
  </div>
  <div class="card">
    <h2>MEDIC-only / DAKP-only drugs</h2>
    <span class="big">${byDrug.filter((d) => d.medic > 0 && d.dakp === 0).length.toLocaleString()} / ${byDrug.filter((d) => d.dakp > 0 && d.medic === 0).length.toLocaleString()}</span>
  </div>
</div>

## MEDIC vs DAKP disease counts per drug

Each point is a drug: diseases asserted by MEDIC (x) vs by DAKP (y). Color is the
per-drug exact Jaccard.

```js
const both = byDrug.filter((d) => d.medic > 0 && d.dakp > 0);
```

```js
Plot.plot({
  width,
  grid: true,
  x: {label: "MEDIC diseases per drug", type: "sqrt"},
  y: {label: "DAKP diseases per drug", type: "sqrt"},
  color: {label: "Jaccard", scheme: "BuYlRd", domain: [0, 1], legend: true},
  marks: [
    Plot.dot(both, {
      x: "medic", y: "dakp", r: 3, fill: "jaccard", fillOpacity: 0.7,
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
  columns: ["drug", "medic", "dakp", "shared", "jaccard", "offlabel_only"],
  header: {drug: "Drug", medic: "MEDIC", dakp: "DAKP", shared: "shared", jaccard: "Jaccard", offlabel_only: "off-label only"},
  format: {
    drug: (cid) => html`<a href="drug?id=${encodeURIComponent(cid)}">${labelOfDrug.get(cid) ?? cid}</a> <span class="small muted">${cid}</span>`,
  },
  sort: "shared",
  reverse: true,
  rows: 18,
})
```
