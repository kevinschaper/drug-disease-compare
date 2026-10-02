# Contraindications

<div class="note">
  <b>In-progress work.</b> The MEDIC (MeDIC redesign, a local, unreleased build) and DAKP
  (1.16.0) updates compared here are both under active development. Treat every number on
  this page as a snapshot of work in progress, to inform the next iteration of each source —
  not as a final characterization of either resource.
</div>

`contraindicated_in` is the **opposite** of a treatment relation, so it is held entirely
apart from the indication overlap on the other pages. Since the MeDIC redesign, **both
MEDIC and DAKP** export contraindications mined from the label's contraindications
section, so for the first time they can be compared head to head.

```js
const contra = await FileAttachment("data/contraindications.json").json();
const cs = contra.summary;
const fmt = (n) => n.toLocaleString();
```

<div class="grid grid-cols-4">
  <div class="card">
    <h2>MEDIC</h2>
    <span class="big">${fmt(cs.pairs.medic)}</span>
    contraindication pairs · ${fmt(cs.medic_drugs)} drugs
  </div>
  <div class="card">
    <h2>DAKP</h2>
    <span class="big">${fmt(cs.pairs.dakp)}</span>
    contraindication pairs · ${fmt(cs.dakp_drugs)} drugs
  </div>
  <div class="card">
    <h2>Shared</h2>
    <span class="big">${fmt(cs.shared)}</span>
    exact pairs · Jaccard ${cs.jaccard.toFixed(3)}
  </div>
  <div class="card">
    <h2>Drugs in both</h2>
    <span class="big">${fmt(cs.shared_drugs)}</span>
    drugs with contraindications in each source
  </div>
</div>

Pairs are canonical (Node Normalizer cliques, MONDO-preferred) and compared **exactly** —
no is-a "related" matching here, since a contraindication on a parent disease does not
imply one on each subtype (or vice versa).

## Indication ↔ contraindication clashes

A pair a source lists as a **contraindication** that some source (possibly the same one)
also lists as an **indication** (MEDIC, DAKP-approved or dismech; FAERS off-label use doesn't
count) is a strong lead: usually a negation-scoping or
section-attribution error in extraction, occasionally a real subpopulation nuance
("contraindicated in severe X", "indicated for mild X").

<div class="grid grid-cols-2">
  <div class="card">
    <h2>MEDIC contraindications that are also indications</h2>
    <span class="big">${fmt(cs.clash.medic)}</span>
    of ${fmt(cs.pairs.medic)} · an indication in MEDIC, DAKP-approved or dismech
  </div>
  <div class="card">
    <h2>DAKP contraindications that are also indications</h2>
    <span class="big">${fmt(cs.clash.dakp)}</span>
    of ${fmt(cs.pairs.dakp)} · an indication in MEDIC, DAKP-approved or dismech
  </div>
</div>

## All contraindication pairs

Agreement first, then clashes, then by DAKP's FAERS case count. Up to 3,000 pairs.

```js
const which = view(Inputs.radio(["all", "both", "MEDIC only", "DAKP only", "clash"], {label: "Show", value: "all"}));
```

```js
const filtered = contra.rows.filter((r) =>
  which === "all" ? true
  : which === "both" ? r.medic && r.dakp
  : which === "MEDIC only" ? r.medic && !r.dakp
  : which === "DAKP only" ? r.dakp && !r.medic
  : !!r.treats_in);
const search = view(Inputs.search(filtered, {placeholder: "search by drug or disease…"}));
```

```js
Inputs.table(search, {
  columns: ["drug_label", "disease_label", "medic", "dakp", "treats_in", "dakp_cases", "drug", "disease"],
  header: {drug_label: "Drug", disease_label: "Disease (contraindicated)", medic: "MEDIC", dakp: "DAKP",
           treats_in: "Indication in", dakp_cases: "FAERS cases", drug: "Drug ID", disease: "Disease ID"},
  format: {
    drug_label: (l, i, data) => html`<a href="drug?id=${encodeURIComponent(data[i].drug)}">${l}</a>`,
    medic: (v) => (v ? "✓" : ""), dakp: (v) => (v ? "✓" : ""),
  },
  width: {drug_label: 200, disease_label: 280, medic: 56, dakp: 56, treats_in: 150, dakp_cases: 90},
  sort: null, rows: 25, select: false,
})
```
