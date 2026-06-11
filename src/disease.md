---
title: Disease detail
sql:
  pairs: ./data/pairs.parquet
---

# Disease detail

```js
const byDisease = await FileAttachment("data/by_disease.json").json();
const id = new URLSearchParams(typeof location !== "undefined" ? location.search : "").get("id");
const meta = byDisease.find((d) => d.disease === id);
```

```js
// DuckDB-WASM slices the per-pair Parquet to just this disease's rows.
const toRows = (t) => Array.from(t, (r) => Object.fromEntries(t.schema.fields.map((f) => [f.name, r[f.name]])));
const detail = id
  ? toRows(await sql`
      SELECT bucket, drug, drug_label, status, CAST(cases AS INTEGER) AS cases, note
      FROM pairs WHERE disease = ${id} ORDER BY bucket, drug_label`)
  : [];
const drugLabel = new Map(detail.map((r) => [r.drug, r.drug_label]));
```

```js
id
  ? html`<div class="card">
      <h2 style="margin-top:0">${meta?.disease_label ?? id} <span class="small muted">${id}</span></h2>
      ${meta
        ? html`<div class="small muted">${meta.disease_prefix} · MEDIC ${meta.medic} · DAKP ${meta.dakp} · shared ${meta.shared} ·
            ${meta.offlabel_only.toLocaleString()} DAKP off-label-only (counted, not listed below)</div>`
        : html`<div class="small muted">No coverage row found for this CURIE.</div>`}
      <div class="small"><a href="diseases">← all diseases</a></div>
    </div>`
  : html`<div class="card">Open a disease from the <a href="diseases">Disease coverage</a> page.</div>`
```

Each drug linked to this disease, in either feed, by bucket. `related` rows are a
MONDO is-a hop away on the disease axis (see the `note`). Click a drug to cross
over to its detail.

```js
id
  ? Inputs.table(detail, {
      columns: ["bucket", "drug", "status", "cases", "note"],
      header: {bucket: "Bucket", drug: "Drug", status: "DAKP status", cases: "FAERS cases", note: "Hierarchy note"},
      format: {
        drug: (cid) => html`<a href="drug?id=${encodeURIComponent(cid)}">${drugLabel.get(cid) ?? cid}</a>`,
      },
      sort: "bucket",
      rows: 100,
      width: {note: 280},
    })
  : null
```
