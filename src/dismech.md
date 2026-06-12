---
title: dismech
sql:
  pairs: ./data/pairs.parquet
---

# dismech lens

dismech is **disease-centric and narrow** — it curates ~1,150 diseases so far, and
only some of those have drug→disease edges yet. So its non-overlap can't be read
like MEDIC↔DAKP: a missing edge on a disease it hasn't curated means *"not curated"*,
not *"disagrees"*. This page reads dismech on its own terms — **how well do the broad
feeds corroborate dismech's drug→disease edges, and what's novel to dismech** (worth a
look: possibly new and good, possibly wrong). "Supported" = the other feed has the
exact pair **or** the same drug a MONDO is-a hop away.

```js
const summary = await FileAttachment("data/summary.json").json();
const d = summary.dismech;
const toRows = (t) => Array.from(t, (r) => Object.fromEntries(t.schema.fields.map((f) => [f.name, r[f.name]])));
const backed = (s) => `${s} IN ('exact','related')`;
const unbacked = (s) => `${s} NOT IN ('exact','related')`;
```

<div class="grid grid-cols-4">
  <div class="card">
    <h2>dismech edges</h2>
    <span class="big">${d.edges.toLocaleString()}</span>
    drug→disease pairs (CHEBI subset)
  </div>
  <div class="card">
    <h2>Corroborated</h2>
    <span class="big">${(d.supported / d.edges * 100).toFixed(0)}%</span>
    ${d.supported.toLocaleString()} backed by MEDIC or DAKP
  </div>
  <div class="card">
    <h2>Novel to dismech</h2>
    <span class="big">${d.novel.toLocaleString()}</span>
    no other feed has it — worth a look
  </div>
  <div class="card">
    <h2>Curated diseases</h2>
    <span class="big">${d.scope_diseases.toLocaleString()}</span>
    its comparison scope
  </div>
</div>

## How dismech's edges are supported

Each dismech drug→disease edge by which broad feed backs it (exact or is-a-related).

```js
const sup = toRows(await sql`
  SELECT
    CAST(sum(CASE WHEN ${backed("medic")} AND ${backed("dakp")} THEN 1 ELSE 0 END) AS INTEGER) AS both,
    CAST(sum(CASE WHEN ${backed("medic")} AND ${unbacked("dakp")} THEN 1 ELSE 0 END) AS INTEGER) AS medic_only,
    CAST(sum(CASE WHEN ${unbacked("medic")} AND ${backed("dakp")} THEN 1 ELSE 0 END) AS INTEGER) AS dakp_only,
    CAST(sum(CASE WHEN ${unbacked("medic")} AND ${unbacked("dakp")} THEN 1 ELSE 0 END) AS INTEGER) AS novel
  FROM pairs WHERE dismech = 'exact'`)[0];
const supRows = [
  {support: "MEDIC + DAKP", n: Number(sup.both)},
  {support: "MEDIC only", n: Number(sup.medic_only)},
  {support: "DAKP only", n: Number(sup.dakp_only)},
  {support: "novel (neither)", n: Number(sup.novel)},
];
```

```js
Plot.plot({
  width,
  marginLeft: 130,
  height: 200,
  x: {label: "dismech edges", grid: true},
  y: {label: null, domain: supRows.map((r) => r.support)},
  color: {domain: ["MEDIC + DAKP", "MEDIC only", "DAKP only", "novel (neither)"], range: ["#13315c", "#4269d0", "#6a9bd8", "#e15759"], legend: true},
  marks: [
    Plot.barX(supRows, {y: "support", x: "n", fill: "support", tip: true}),
    Plot.text(supRows, {y: "support", x: "n", text: (r) => r.n.toLocaleString(), dx: 16}),
    Plot.ruleX([0]),
  ],
})
```

## Novel to dismech — worth a look

dismech edges no other feed asserts (not even a MONDO is-a hop away). These are
dismech's distinctive, mechanism-driven calls — potentially new and correct, or
extraction errors. Ranked by **dismech PMID support** (more cited = easier to check).

```js
const novel = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label, disease_prefix, CAST(dismech_pubs AS INTEGER) AS pubs
  FROM pairs WHERE dismech = 'exact' AND ${unbacked("medic")} AND ${unbacked("dakp")}
  ORDER BY dismech_pubs DESC, drug_label`);
const nDrug = new Map(novel.map((r) => [r.drug, r.drug_label]));
const nDis = new Map(novel.map((r) => [r.disease, r.disease_label]));
const novelSearch = view(Inputs.search(novel, {placeholder: `search ${novel.length.toLocaleString()} novel pairs…`}));
```

```js
Inputs.table(novelSearch, {
  columns: ["drug", "disease", "disease_prefix", "pubs"],
  header: {drug: "Drug", disease: "Disease", disease_prefix: "Space", pubs: "dismech PMIDs"},
  format: {
    drug: (cid) => html`<a href="drug?id=${encodeURIComponent(cid)}">${nDrug.get(cid) ?? cid}</a> <span class="small muted">${cid}</span>`,
    disease: (cid) => html`<a href="disease?id=${encodeURIComponent(cid)}">${nDis.get(cid) ?? cid}</a> <span class="small muted">${cid}</span>`,
  },
  sort: "pubs",
  reverse: true,
  rows: 18,
  width,
})
```

## dismech gaps — within its curated diseases

The flip side: diseases dismech *has* curated, where MEDIC or DAKP carry a drug edge
dismech doesn't. Because the disease is in dismech's scope, these are genuine gaps
(candidate edges to add), not just uncurated territory. ${d.gaps_in_scope.toLocaleString()}
pairs in total.

```js
const gaps = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label, medic, dakp, dakp_status,
         CAST(dakp_cases AS INTEGER) AS cases
  FROM pairs WHERE dismech = '' AND dismech_scope
    AND (medic = 'exact' OR dakp = 'exact')
  ORDER BY dakp_cases DESC, drug_label`);
const gDrug = new Map(gaps.map((r) => [r.drug, r.drug_label]));
const gDis = new Map(gaps.map((r) => [r.disease, r.disease_label]));
const gapSearch = view(Inputs.search(gaps, {placeholder: `search ${gaps.length.toLocaleString()} gap pairs…`}));
```

```js
Inputs.table(gapSearch, {
  columns: ["drug", "disease", "medic", "dakp", "dakp_status", "cases"],
  header: {drug: "Drug", disease: "Disease", medic: "MEDIC", dakp: "DAKP", dakp_status: "DAKP status", cases: "FAERS cases"},
  format: {
    drug: (cid) => html`<a href="drug?id=${encodeURIComponent(cid)}">${gDrug.get(cid) ?? cid}</a> <span class="small muted">${cid}</span>`,
    disease: (cid) => html`<a href="disease?id=${encodeURIComponent(cid)}">${gDis.get(cid) ?? cid}</a> <span class="small muted">${cid}</span>`,
  },
  sort: "cases",
  reverse: true,
  rows: 18,
  width,
})
```
