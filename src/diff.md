---
sql:
  pairs: ./data/pairs.parquet
---

# Disagreements

The drug→disease pairs where a feed stands alone — the triage queue for potential
errors. Each row is one *(drug, disease)* pair in canonical MONDO-centric space.
"Only" here means **no other feed asserts it, even as a MONDO is-a neighbor** —
hierarchy-related and multi-source pairs are confirmed elsewhere, not disagreements.

* **MEDIC-only** — MEDIC asserts an indication neither DAKP nor dismech has, **and
  DAKP covers that disease** (so its absence is a real gap, not uncurated territory).
* **DAKP on-label-only** — DAKP records an `approved_for_condition` use no other feed
  has, where MEDIC covers the disease. Either they under-extracted, or DAKP is wrong.

This is **scope-aware**: a pair is only "only" where the other broad feed actually
covers the disease. DAKP off-label pairs are expected to be feed-unique (MEDIC/dismech
are approved indications only), so they're summarized by drug at the bottom. dismech's
unique edges have their own [dismech lens](./dismech) (it's too narrow to read here).

```js
// DuckDB-WASM slices the per-pair Parquet by source membership.
const toRows = (t) => Array.from(t, (r) => Object.fromEntries(t.schema.fields.map((f) => [f.name, r[f.name]])));
const medicOnly = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label, disease_prefix
  FROM pairs WHERE medic = 'exact' AND dakp = '' AND dismech = '' AND dakp_scope
  ORDER BY drug_label, disease_label`);
const dakpOnly = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label, disease_prefix, CAST(dakp_cases AS INTEGER) AS cases
  FROM pairs WHERE dakp = 'exact' AND dakp_status = 'approved_for_condition'
    AND medic = '' AND dismech = '' AND medic_scope ORDER BY dakp_cases DESC`);
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

## MEDIC-only — MEDIC asserts, no other feed does

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
  width,
})
```

## DAKP on-label-only — DAKP approved-for-condition, no other feed has it

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
  width,
})
```

## DAKP off-label-only — expected divergence, by drug

These are not disagreements; shown for context. Top 200 drugs by off-label-only pair
count (DAKP has ${summary.dakp_offlabel_pairs.toLocaleString()} off-label pairs overall).

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
  width,
})
```
