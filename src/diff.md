---
sql:
  pairs: ./data/pairs.parquet
---

# Disagreements

The drug→disease pairs where a source stands alone — the triage queue for potential
errors. Each row is one *(drug, disease)* pair in canonical MONDO-centric space.
"Only" here means **no other source asserts it, even as a MONDO is-a neighbor** —
hierarchy-related and multi-source pairs are confirmed elsewhere, not disagreements.

* **MEDIC-only** — MEDIC asserts an indication neither DAKP nor dismech has, **and
  DAKP covers that disease** (so its absence is a real gap, not uncurated territory).
* **DAKP on-label-only** — DAKP records an `approved_for_condition` use no other source
  has, where MEDIC covers the disease. Either they under-extracted, or DAKP is wrong.

This is **scope-aware**: a pair is only "only" where the other broad source actually
covers the disease. DAKP **off-label** (FAERS) pairs aren't disagreements — they're
observed use, read separately on the [off-label view](./offlabel). dismech's unique
edges have their own [dismech lens](./dismech) (it's too narrow to read here).

Pairs that look source-unique but are really **the same drug under a different identifier**
(a salt/ester/prodrug/stereoisomer the Node Normalizer didn't merge) are lifted out of the
queues below and shown separately — they're *false* disagreements, not leads. That bridge is
our inference (active-moiety, ion-guarded), not a source's assertion, so it's never counted
as exact agreement; see [methods](./methods#drug-collapse).

```js
// DuckDB-WASM slices the per-pair Parquet by source membership.
// n_group >= 2 marks a pair the same drug-moiety reaches in another source via a
// different CURIE, so we exclude those from the "only" queues (they're not real leads).
const toRows = (t) => Array.from(t, (r) => Object.fromEntries(t.schema.fields.map((f) => [f.name, r[f.name]])));
const medicOnly = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label, disease_prefix
  FROM pairs WHERE medic = 'exact' AND dakp = '' AND dismech = '' AND dakp_scope AND n_group < 2
  ORDER BY drug_label, disease_label`);
const dakpOnly = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label, disease_prefix, CAST(dakp_cases AS INTEGER) AS cases
  FROM pairs WHERE dakp = 'exact' AND dakp_status = 'approved_for_condition'
    AND medic = '' AND dismech = '' AND medic_scope AND n_group < 2 ORDER BY dakp_cases DESC`);
const moietyBridges = toRows(await sql`
  SELECT drug_group, any_value(drug_group_label) AS moiety, disease,
         any_value(disease_label) AS disease_label, any_value(disease_prefix) AS disease_prefix,
         string_agg(DISTINCT drug_label, ' ≡ ') AS variants,
         bool_or(medic = 'exact') AS in_medic, bool_or(dakp = 'exact') AS in_dakp,
         bool_or(dismech = 'exact') AS in_dismech
  FROM pairs WHERE n_group >= 2
  GROUP BY drug_group, disease HAVING max(n_exact) < 2
  ORDER BY disease_label`);
moietyBridges.forEach((r) => {
  r.sources = [r.in_medic && "MEDIC", r.in_dakp && "DAKP", r.in_dismech && "dismech"].filter(Boolean).join(" + ");
});
const uniq = (rows, k) => new Set(rows.map((r) => r[k])).size;
const drugCell = (cid, label) => html`<a href="drug?id=${encodeURIComponent(cid)}">${label ?? cid}</a> <span class="small muted">${cid}</span>`;
const diseaseCell = (cid, label) => html`<a href="disease?id=${encodeURIComponent(cid)}">${label ?? cid}</a> <span class="small muted">${cid}</span>`;
const dLabel = new Map([...medicOnly, ...dakpOnly].map((r) => [r.drug, r.drug_label]));
const xLabel = new Map([...medicOnly, ...dakpOnly].map((r) => [r.disease, r.disease_label]));
```

<div class="grid grid-cols-3">
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
  <div class="card">
    <h2>Same drug, different ID</h2>
    <span class="big">${moietyBridges.length.toLocaleString()}</span> recovered
    <div class="small muted">lifted out of the queues — agree once variants are collapsed</div>
  </div>
</div>

## MEDIC-only — MEDIC asserts, no other source does

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

## DAKP on-label-only — DAKP approved-for-condition, no other source has it

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

## Same drug, different identifier — recovered agreement

These looked source-unique but are the **same drug recorded under different CURIEs**
(salt, ester, prodrug, stereoisomer, or just CHEBI-vs-UNII) that the Node Normalizer keeps
in separate cliques. Collapsing each to its **active moiety** (ion-guarded) bridges them, so
they agree across sources. They're shown here — *not* in the disagreement queues — and are
**not** counted as exact agreement: the bridge is our inference, the sources never asserted
the same identifier. `variants` lists the merged drug records.

```js
const bSearch = view(Inputs.search(moietyBridges, {placeholder: `search ${moietyBridges.length.toLocaleString()} recovered pairs…`}));
const bxLabel = new Map(moietyBridges.map((r) => [r.disease, r.disease_label]));
```

```js
Inputs.table(bSearch, {
  columns: ["moiety", "variants", "disease", "sources"],
  header: {moiety: "Active moiety", variants: "Merged drug records", disease: "Disease", sources: "Agreeing sources"},
  format: {
    disease: (cid) => diseaseCell(cid, bxLabel.get(cid)),
  },
  sort: "moiety",
  rows: 18,
  width,
})
```

DAKP's **off-label** (FAERS) observations are not disagreements — they're read separately
on the [off-label view](./offlabel).
