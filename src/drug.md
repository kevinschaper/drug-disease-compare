---
title: Drug detail
sql:
  pairs: ./data/pairs.parquet
---

# Drug detail

```js
const byDrug = await FileAttachment("data/by_drug.json").json();
const id = new URLSearchParams(typeof location !== "undefined" ? location.search : "").get("id");
const meta = byDrug.find((d) => d.drug === id);
```

```js
// DuckDB-WASM slices the per-pair Parquet to just this drug's rows.
const toRows = (t) => Array.from(t, (r) => Object.fromEntries(t.schema.fields.map((f) => [f.name, r[f.name]])));
const detail = id
  ? toRows(await sql`
      SELECT disease, disease_label, disease_prefix, medic, dakp, dismech,
             dakp_status, CAST(dakp_cases AS INTEGER) AS cases, CAST(dismech_pubs AS INTEGER) AS pubs,
             CAST(n_exact AS INTEGER) AS n_exact, note
      FROM pairs WHERE drug = ${id} ORDER BY n_exact DESC, disease_label`)
  : [];
const diseaseLabel = new Map(detail.map((r) => [r.disease, r.disease_label]));
```

```js
id
  ? html`<div class="card">
      <h2 style="margin-top:0">${meta?.drug_label ?? id} <span class="small muted">${id}</span></h2>
      ${meta
        ? html`<div class="small muted">MEDIC ${meta.medic} · DAKP ${meta.dakp} · dismech ${meta.dismech} ·
            shared (≥2) ${meta.shared} · ${meta.offlabel.toLocaleString()} DAKP off-label</div>`
        : html`<div class="small muted">No coverage row found for this CURIE.</div>`}
      <div class="small"><a href="drugs">← all drugs</a></div>
    </div>`
  : html`<div class="card">Open a drug from the <a href="drugs">Drug coverage</a> page.</div>`
```

Every disease this drug is linked to, with each feed's membership: **exact**,
**related** (same drug, a MONDO is-a hop away — see `note`), or blank (absent).
`n` is how many feeds agree exactly. Click a disease to cross over to its detail.

```js
id
  ? Inputs.table(detail, {
      columns: ["disease", "disease_prefix", "medic", "dakp", "dismech", "dakp_status", "cases", "pubs", "n_exact", "note"],
      header: {disease: "Disease", disease_prefix: "Space", medic: "MEDIC", dakp: "DAKP", dismech: "dismech", dakp_status: "DAKP status", cases: "FAERS cases", pubs: "dismech PMIDs", n_exact: "n", note: "Hierarchy note"},
      format: {
        disease: (cid) => html`<a href="disease?id=${encodeURIComponent(cid)}">${diseaseLabel.get(cid) ?? cid}</a>`,
      },
      sort: "n_exact",
      reverse: true,
      rows: 100,
      width,
    })
  : null
```
