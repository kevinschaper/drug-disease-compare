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
      SELECT drug, drug_label, medic, dakp, dismech, dakp_status,
             CAST(dakp_cases AS INTEGER) AS cases, CAST(dismech_pubs AS INTEGER) AS pubs,
             CAST(n_exact AS INTEGER) AS n_exact, note
      FROM pairs WHERE disease = ${id} ORDER BY n_exact DESC, drug_label`)
  : [];
const drugLabel = new Map(detail.map((r) => [r.drug, r.drug_label]));
```

```js
id
  ? html`<div class="card">
      <h2 style="margin-top:0">${meta?.disease_label ?? id} <span class="small muted">${id}</span></h2>
      ${meta
        ? html`<div class="small muted">${meta.disease_prefix} · MEDIC ${meta.medic} · DAKP ${meta.dakp} · dismech ${meta.dismech} ·
            shared (≥2) ${meta.shared} · ${meta.offlabel.toLocaleString()} DAKP off-label</div>`
        : html`<div class="small muted">No coverage row found for this CURIE.</div>`}
      <div class="small"><a href="diseases">← all diseases</a></div>
    </div>`
  : html`<div class="card">Open a disease from the <a href="diseases">Disease coverage</a> page.</div>`
```

Every drug linked to this disease, with each feed's membership: **exact**,
**related** (a MONDO is-a hop away — see `note`), or blank. `n` is how many feeds
agree exactly. Click a drug to cross over to its detail.

```js
id
  ? Inputs.table(detail, {
      columns: ["drug", "medic", "dakp", "dismech", "dakp_status", "cases", "pubs", "n_exact", "note"],
      header: {drug: "Drug", medic: "MEDIC", dakp: "DAKP", dismech: "dismech", dakp_status: "DAKP status", cases: "FAERS cases", pubs: "dismech PMIDs", n_exact: "n", note: "Hierarchy note"},
      format: {
        drug: (cid) => html`<a href="drug?id=${encodeURIComponent(cid)}">${drugLabel.get(cid) ?? cid}</a>`,
      },
      sort: "n_exact",
      reverse: true,
      rows: 100,
      width,
    })
  : null
```
