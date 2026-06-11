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
      SELECT bucket, disease, disease_label, disease_prefix, status, CAST(cases AS INTEGER) AS cases, note
      FROM pairs WHERE drug = ${id} ORDER BY bucket, disease_label`)
  : [];
const diseaseLabel = new Map(detail.map((r) => [r.disease, r.disease_label]));
```

```js
id
  ? html`<div class="card">
      <h2 style="margin-top:0">${meta?.drug_label ?? id} <span class="small muted">${id}</span></h2>
      ${meta
        ? html`<div class="small muted">MEDIC ${meta.medic} · DAKP ${meta.dakp} · shared ${meta.shared} ·
            ${meta.offlabel_only.toLocaleString()} DAKP off-label-only (counted, not listed below)</div>`
        : html`<div class="small muted">No coverage row found for this CURIE.</div>`}
      <div class="small"><a href="drugs">← all drugs</a></div>
    </div>`
  : html`<div class="card">Open a drug from the <a href="drugs">Drug coverage</a> page.</div>`
```

Each disease this drug is linked to, in either feed, by bucket — `agree`,
`related` (a MONDO is-a hop apart), `medic_only`, or `dakp_onlabel_only`. The
`note` carries the hierarchy relationship for `related` rows. Click a disease to
cross over to its detail.

```js
id
  ? Inputs.table(detail, {
      columns: ["bucket", "disease", "disease_prefix", "status", "cases", "note"],
      header: {bucket: "Bucket", disease: "Disease", disease_prefix: "Space", status: "DAKP status", cases: "FAERS cases", note: "Hierarchy note"},
      format: {
        disease: (cid) => html`<a href="disease?id=${encodeURIComponent(cid)}">${diseaseLabel.get(cid) ?? cid}</a>`,
      },
      sort: "bucket",
      rows: 100,
      width: {note: 280},
    })
  : null
```
