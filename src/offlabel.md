---
title: Off-label (FAERS)
sql:
  pairs: ./data/pairs.parquet
---

# Off-label use (FAERS)

DAKP's `off_label_use` edges come from **FAERS adverse-event reports** — they record that
a drug was *used* in patients who have a condition, not that it's *approved* (or even
effective) for it. They're confounded by indication (a drug given for a chemo side-effect
shows up against the cancer), and they dominate DAKP by volume — so they're kept **out of
the headline comparison** and read here on their own terms, as observations.

```js
const summary = await FileAttachment("data/summary.json").json();
const off = summary.offlabel;
const offDrugs = await FileAttachment("data/dakp_offlabel_top_drugs.json").json();
const fmt = (n) => n.toLocaleString();
const toRows = (t) => Array.from(t, (r) => Object.fromEntries(t.schema.fields.map((f) => [f.name, r[f.name]])));
const drugCell = (cid, label) => html`<a href="drug?id=${encodeURIComponent(cid)}">${label ?? cid}</a> <span class="small muted">${cid}</span>`;
const diseaseCell = (cid, label) => html`<a href="disease?id=${encodeURIComponent(cid)}">${label ?? cid}</a> <span class="small muted">${cid}</span>`;
```

<div class="grid grid-cols-3">
  <div class="card">
    <h2>Off-label pairs</h2>
    <span class="big">${fmt(off.pairs)}</span>
    FAERS observed use · ${fmt(off.cases)} reported cases
  </div>
  <div class="card">
    <h2>Off-label only</h2>
    <span class="big">${fmt(off.only)}</span>
    no source asserts an indication
  </div>
  <div class="card">
    <h2>Coincide with an indication</h2>
    <span class="big">${fmt(off.corroborated)}</span>
    also asserted by MEDIC or dismech
  </div>
</div>

## Coincides with an indication

Off-label pairs that **another source asserts as an indication** (MEDIC label or dismech
curation) — the more interesting slice: real-world FAERS use lining up with an approval or
curated treatment. Ranked by FAERS cases.

```js
const corrob = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label,
         (medic = 'exact') AS in_medic, (dismech = 'exact') AS in_dismech,
         CAST(dakp_cases AS INTEGER) AS cases
  FROM pairs
  WHERE dakp = 'exact' AND dakp_status = 'off_label_use' AND (medic = 'exact' OR dismech = 'exact')
  ORDER BY dakp_cases DESC`);
corrob.forEach((r) => { r.indication = [r.in_medic && "MEDIC", r.in_dismech && "dismech"].filter(Boolean).join(" + "); });
const cDrug = new Map(corrob.map((r) => [r.drug, r.drug_label]));
const cDis = new Map(corrob.map((r) => [r.disease, r.disease_label]));
const corrSearch = view(Inputs.search(corrob, {placeholder: `search ${corrob.length.toLocaleString()} corroborated pairs…`}));
```

```js
Inputs.table(corrSearch, {
  columns: ["drug", "disease", "indication", "cases"],
  header: {drug: "Drug", disease: "Disease", indication: "Indication source", cases: "FAERS cases"},
  format: {
    drug: (cid) => drugCell(cid, cDrug.get(cid)),
    disease: (cid) => diseaseCell(cid, cDis.get(cid)),
  },
  sort: "cases", reverse: true, rows: 16, width,
})
```

## Top drugs by off-label pairs

The off-label volume is concentrated in a few drugs. Top ${offDrugs.length} drugs by
off-label-only pair count (drugs whose off-label use no other source asserts).

```js
const oLabel = new Map(offDrugs.map((r) => [r.drug, r.drug_label]));
const oSearch = view(Inputs.search(offDrugs, {placeholder: "search by drug…"}));
```

```js
Inputs.table(oSearch, {
  columns: ["drug", "n", "cases"],
  header: {drug: "Drug", n: "off-label pairs", cases: "FAERS cases"},
  format: {drug: (cid) => drugCell(cid, oLabel.get(cid))},
  sort: "n", reverse: true, rows: 14, width,
})
```

## Off-label-only pairs

Pairs **no source asserts as an indication** — pure FAERS observations. Top 500 by cases
(of ${fmt(off.only)} total); use a drug's or disease's detail page for the full picture.

```js
const olOnly = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label, disease_prefix, CAST(dakp_cases AS INTEGER) AS cases
  FROM pairs
  WHERE dakp = 'exact' AND dakp_status = 'off_label_use' AND medic <> 'exact' AND dismech <> 'exact'
  ORDER BY dakp_cases DESC LIMIT 500`);
const olDrug = new Map(olOnly.map((r) => [r.drug, r.drug_label]));
const olDis = new Map(olOnly.map((r) => [r.disease, r.disease_label]));
const olSearch = view(Inputs.search(olOnly, {placeholder: "search top-500 off-label-only pairs…"}));
```

```js
Inputs.table(olSearch, {
  columns: ["drug", "disease", "disease_prefix", "cases"],
  header: {drug: "Drug", disease: "Disease", disease_prefix: "Space", cases: "FAERS cases"},
  format: {
    drug: (cid) => drugCell(cid, olDrug.get(cid)),
    disease: (cid) => diseaseCell(cid, olDis.get(cid)),
  },
  sort: "cases", reverse: true, rows: 16, width,
})
```
