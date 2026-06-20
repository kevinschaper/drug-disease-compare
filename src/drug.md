---
title: Drug detail
sql:
  pairs: ./data/pairs.parquet
  medev: ./data/medic_evidence.parquet
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
// MEDIC's verbatim approving-agency indication text, joined on disease for this drug.
const medEv = id ? toRows(await sql`SELECT disease, evidence FROM medev WHERE drug = ${id}`) : [];
const medEvBy = new Map(medEv.map((r) => [r.disease, r.evidence]));
detail.forEach((r) => { r.indication = medEvBy.get(r.disease) ?? ""; });
```

```js
// One shared, fixed-position tooltip so it escapes the table's scroll clipping.
const medTip = (() => {
  const el = document.createElement("div");
  el.className = "ev-tip";
  document.body.appendChild(el);
  invalidation.then(() => el.remove());
  return el;
})();

// Render the FDA/EMA/PMDA agency chips; hover a chip to read the verbatim indication.
const agencyCell = (json) => {
  let ev = [];
  try { ev = json ? JSON.parse(json) : []; } catch (e) { ev = []; }
  if (!ev.length) return "";
  const chips = ev.map((e) => {
    const c = html`<span class="agency-chip">${e.agency}</span>`;
    c.addEventListener("mouseenter", () => {
      medTip.innerHTML = "";
      medTip.append(html`<span class="ev-tip-pmid">${e.agency} indication</span>`, document.createTextNode(e.text));
      medTip.classList.add("show");
      const r = c.getBoundingClientRect();
      const w = medTip.getBoundingClientRect().width;
      const h = medTip.getBoundingClientRect().height;
      medTip.style.left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8)) + "px";
      const below = r.bottom + 6;
      medTip.style.top = (below + h > window.innerHeight - 8 ? r.top - h - 6 : below) + "px";
    });
    c.addEventListener("mouseleave", () => medTip.classList.remove("show"));
    return c;
  });
  return html`${chips.flatMap((c, i) => (i ? [document.createTextNode(" "), c] : [c]))}`;
};
```

<style>
.agency-chip {
  display: inline-block;
  padding: 0 6px;
  border-radius: 6px;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
  cursor: help;
  background: color-mix(in srgb, var(--theme-foreground, #1b1e23) 9%, transparent);
}
.ev-tip {
  position: fixed; z-index: 1000; display: none; max-width: 460px;
  padding: 0.5rem 0.65rem; font-size: 12.5px; line-height: 1.45;
  background: var(--theme-background-alt, #f4f5f7); color: var(--theme-foreground, #1b1e23);
  border: 1px solid color-mix(in srgb, currentColor 20%, transparent);
  border-radius: 7px; box-shadow: 0 6px 22px rgba(0, 0, 0, 0.28); pointer-events: none;
}
.ev-tip.show { display: block; }
.ev-tip-pmid {
  display: block; margin-bottom: 0.25rem; font-weight: 600; font-size: 11px;
  color: var(--theme-foreground-muted, #6b7280);
}
</style>

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

Every disease this drug is linked to, with each source's membership: **exact**,
**related** (same drug, a MONDO is-a hop away — see `note`), or blank (absent).
`n` is how many sources agree exactly. Click a disease to cross over to its detail.
Where MEDIC asserts the indication, **hover the FDA/EMA/PMDA chip to read the verbatim
approving-agency indication text.**

```js
id
  ? Inputs.table(detail, {
      columns: ["disease", "disease_prefix", "medic", "indication", "dakp", "dismech", "dakp_status", "cases", "pubs", "n_exact", "note"],
      header: {disease: "Disease", disease_prefix: "Space", medic: "MEDIC", indication: "MEDIC indication", dakp: "DAKP", dismech: "dismech", dakp_status: "DAKP status", cases: "FAERS cases", pubs: "dismech PMIDs", n_exact: "n", note: "Hierarchy note"},
      format: {
        disease: (cid) => html`<a href="disease?id=${encodeURIComponent(cid)}">${diseaseLabel.get(cid) ?? cid}</a>`,
        indication: (json) => agencyCell(json),
      },
      sort: "n_exact",
      reverse: true,
      rows: 100,
      width,
    })
  : null
```
