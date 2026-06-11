# Contraindications

DAKP carries `biolink:contraindicated_in` edges — the **opposite** of a treatment
relation. MEDIC's indication export has no contraindications, so there is **nothing
to compare them against yet**; they are surfaced here for completeness and as a
marker of what a future MEDIC contraindication export could be reconciled against.

These are held entirely apart from the treatment overlap on the other pages: a
contraindication is never collapsed into the `treats` bucket.

```js
const contra = await FileAttachment("data/contraindications.json").json();
```

<div class="grid grid-cols-2">
  <div class="card">
    <h2>DAKP contraindication pairs</h2>
    <span class="big">${contra.summary.pairs.toLocaleString()}</span>
    drug↛disease (canonical, MONDO-centric)
  </div>
  <div class="card">
    <h2>MEDIC contraindications</h2>
    <span class="big">0</span>
    not in the current indication export
  </div>
</div>

## DAKP contraindications

Ranked by `number_of_cases` (FAERS support). Showing up to 1,000 pairs.

```js
const search = view(Inputs.search(contra.rows, {placeholder: "search by drug or disease…"}));
```

```js
Inputs.table(search, {
  columns: ["drug_label", "drug", "disease_label", "disease", "cases"],
  header: {drug_label: "Drug", drug: "Drug ID", disease_label: "Disease (contraindicated)", disease: "Disease ID", cases: "FAERS cases"},
  sort: "cases",
  reverse: true,
  rows: 20,
})
```
