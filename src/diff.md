---
sql:
  pairs: ./data/pairs.parquet
---

# Disagreements

The drug→disease pairs where the two feeds part ways — the triage queue for
potential errors. Each row is one *(drug, disease)* pair in canonical MONDO-centric
space, after hierarchy-aware matching has already absorbed same-drug pairs that
differ only by one MONDO is-a hop (those live under [agreement](./#where-every-drug-disease-pair-lands)).

* **MEDIC-only** — MEDIC asserts an indication DAKP has no record of. Either DAKP
  hasn't surfaced it, or MEDIC over-extracted from a label.
* **DAKP on-label-only** — DAKP records an `approved_for_condition` use that MEDIC
  missed. Either MEDIC under-extracted, or DAKP's approval status is wrong.

Off-label DAKP-only pairs are **excluded here** — MEDIC is label-indications only,
so their absence from MEDIC is expected, not a disagreement. They are summarized by
drug at the bottom.

```js
// DuckDB-WASM slices the per-pair Parquet by bucket.
const toRows = (t) => Array.from(t, (r) => Object.fromEntries(t.schema.fields.map((f) => [f.name, r[f.name]])));
const medicOnly = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label, disease_prefix
  FROM pairs WHERE bucket = 'medic_only' ORDER BY drug_label, disease_label`);
const dakpOnly = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label, disease_prefix, CAST(cases AS INTEGER) AS cases
  FROM pairs WHERE bucket = 'dakp_onlabel_only' ORDER BY cases DESC`);
const offlabel = await FileAttachment("data/dakp_offlabel_top_drugs.json").json();
const summary = await FileAttachment("data/summary.json").json();
const uniq = (rows, k) => new Set(rows.map((r) => r[k])).size;
const drugCell = (cid, label) => html`<a href="drug?id=${encodeURIComponent(cid)}">${label ?? cid}</a> <span class="small muted">${cid}</span>`;
const diseaseCell = (cid, label) => html`<a href="disease?id=${encodeURIComponent(cid)}">${label ?? cid}</a> <span class="small muted">${cid}</span>`;
const dLabel = new Map([...medicOnly, ...dakpOnly].map((r) => [r.drug, r.drug_label]));
const xLabel = new Map([...medicOnly, ...dakpOnly].map((r) => [r.disease, r.disease_label]));
const oLabel = new Map(offlabel.map((r) => [r.drug, r.drug_label]));
```

<div class="grid grid-cols-2">
  <div class="card">
    <h2>MEDIC-only</h2>
    <span class="big">${medicOnly.length.toLocaleString()}</span> pairs
    <div class="small muted">${uniq(medicOnly, "drug").toLocaleString()} drugs · ${uniq(medicOnly, "disease").toLocaleString()} diseases</div>
  </div>
  <div class="card">
    <h2>DAKP on-label-only</h2>
    <span class="big">${dakpOnly.length.toLocaleString()}</span> pairs
    <div class="small muted">${uniq(dakpOnly, "drug").toLocaleString()} drugs · ${uniq(dakpOnly, "disease").toLocaleString()} diseases</div>
  </div>
</div>

## MEDIC-only — MEDIC asserts, DAKP doesn't

```js
const mSearch = view(Inputs.search(medicOnly, {placeholder: "search by drug or disease…"}));
```

```js
Inputs.table(mSearch, {
  columns: ["drug", "disease", "disease_prefix"],
  header: {drug: "Drug", disease: "Disease", disease_prefix: "Disease space"},
  format: {
    drug: (cid) => drugCell(cid, dLabel.get(cid)),
    disease: (cid) => diseaseCell(cid, xLabel.get(cid)),
  },
  sort: "drug",
  rows: 18,
})
```

## DAKP on-label-only — DAKP approved-for-condition, MEDIC doesn't have it

Ranked by `number_of_cases` (FAERS support), highest first.

```js
const dSearch = view(Inputs.search(dakpOnly, {placeholder: "search by drug or disease…"}));
```

```js
Inputs.table(dSearch, {
  columns: ["drug", "disease", "cases"],
  header: {drug: "Drug", disease: "Disease", cases: "FAERS cases"},
  format: {
    drug: (cid) => drugCell(cid, dLabel.get(cid)),
    disease: (cid) => diseaseCell(cid, xLabel.get(cid)),
  },
  sort: "cases",
  reverse: true,
  rows: 18,
})
```

## DAKP off-label-only — expected divergence, by drug

These are not disagreements; shown for context. Top 200 drugs by off-label pair
count (the full off-label-only set is ${summary.dakp_only_offlabel.toLocaleString()} pairs).

```js
const oSearch = view(Inputs.search(offlabel, {placeholder: "search by drug…"}));
```

```js
Inputs.table(oSearch, {
  columns: ["drug", "n", "cases"],
  header: {drug: "Drug", n: "off-label pairs", cases: "FAERS cases"},
  format: {
    drug: (cid) => drugCell(cid, oLabel.get(cid)),
  },
  sort: "n",
  reverse: true,
  rows: 12,
})
```
