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
const medicOnly = await FileAttachment("data/medic_only.json").json();
const dakpOnly = await FileAttachment("data/dakp_onlabel_only.json").json();
const offlabel = await FileAttachment("data/dakp_offlabel_top_drugs.json").json();
const uniq = (rows, k) => new Set(rows.map((r) => r[k])).size;
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
  columns: ["drug_label", "drug", "disease_label", "disease", "disease_prefix"],
  header: {drug_label: "Drug", drug: "Drug ID", disease_label: "Disease", disease: "Disease ID", disease_prefix: "Disease space"},
  sort: "drug_label",
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
  columns: ["drug_label", "drug", "disease_label", "disease", "cases"],
  header: {drug_label: "Drug", drug: "Drug ID", disease_label: "Disease", disease: "Disease ID", cases: "FAERS cases"},
  sort: "cases",
  reverse: true,
  rows: 18,
})
```

## DAKP off-label-only — expected divergence, by drug

These are not disagreements; shown for context. Top 200 drugs by off-label pair
count (the full off-label-only set is ${offlabel.reduce((a, d) => a + d.n, 0).toLocaleString()}+ pairs).

```js
const oSearch = view(Inputs.search(offlabel, {placeholder: "search by drug…"}));
```

```js
Inputs.table(oSearch, {
  columns: ["drug_label", "drug", "n", "cases"],
  header: {drug_label: "Drug", drug: "Drug ID", n: "off-label pairs", cases: "FAERS cases"},
  sort: "n",
  reverse: true,
  rows: 12,
})
```
