---
title: Disease detail
sql:
  pairs: ./data/pairs.parquet
  medev: ./data/medic_evidence.parquet
---

# Disease detail

```js
import {comboKey, comboCounts} from "./components/sources.js";
```

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
             CAST(dakp_cases AS INTEGER) AS cases, dismech_evidence,
             CAST(n_exact AS INTEGER) AS n_exact, note
      FROM pairs WHERE disease = ${id} ORDER BY n_exact DESC, drug_label`)
  : [];
const drugLabel = new Map(detail.map((r) => [r.drug, r.drug_label]));
// MEDIC's verbatim approving-agency indication text, joined on drug for this disease.
const medEv = id ? toRows(await sql`SELECT drug, evidence FROM medev WHERE disease = ${id}`) : [];
const medEvBy = new Map(medEv.map((r) => [r.drug, r.evidence]));
detail.forEach((r) => { r.indication = medEvBy.get(r.drug) ?? ""; });
```

```js
const medTip = (() => {
  const el = document.createElement("div");
  el.className = "ev-tip";
  document.body.appendChild(el);
  invalidation.then(() => el.remove());
  return el;
})();

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

// dismech evidence: numbered PubMed links; hover a number to read the supporting text.
const dismechCell = (json) => {
  let ev = [];
  try { ev = json ? JSON.parse(json) : []; } catch (e) { ev = []; }
  if (!ev.length) return "";
  const links = ev.map((e, i) => {
    const a = html`<a class="ev-pmid" href="https://pubmed.ncbi.nlm.nih.gov/${e.pmid.replace("PMID:", "")}" target="_blank" rel="noopener">${i + 1}</a>`;
    const text = e.text || e.pmid;
    a.addEventListener("mouseenter", () => {
      medTip.innerHTML = "";
      medTip.append(html`<span class="ev-tip-pmid">${e.pmid}</span>`, document.createTextNode(text));
      medTip.classList.add("show");
      const r = a.getBoundingClientRect();
      const w = medTip.getBoundingClientRect().width;
      const h = medTip.getBoundingClientRect().height;
      medTip.style.left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8)) + "px";
      const below = r.bottom + 6;
      medTip.style.top = (below + h > window.innerHeight - 8 ? r.top - h - 6 : below) + "px";
    });
    a.addEventListener("mouseleave", () => medTip.classList.remove("show"));
    return a;
  });
  return html`${links.flatMap((a, i) => (i ? [document.createTextNode(" "), a] : [a]))}`;
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
.ev-pmid { font-variant-numeric: tabular-nums; padding: 0 1px; }
.combo-h { margin: 1.4rem 0 0.35rem; font-size: 14px; font-weight: 600; }
.combo-h span { font-weight: 400; color: var(--theme-foreground-muted, #6b7280); }
</style>

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

Every drug linked to this disease, **broken out by the exact set of sources that assert
it** (DAKP split into approved vs off-label; off-label groups last). Membership is
**exact** / **related** (a MONDO is-a hop away — see `note`) / blank; where MEDIC asserts
the indication, **hover the FDA/EMA/PMDA chip** for the verbatim approving-agency text, and
hover a **dismech ref** number for its supporting text.

```js
// shared table renderer. Explicit column widths so long drug names (and the
// hierarchy note) don't truncate.
const renderTable = (rows) => Inputs.table(rows, {
  columns: ["drug", "medic", "indication", "dakp", "dismech", "dakp_status", "cases", "dismech_evidence", "n_exact", "note"],
  header: {drug: "Drug", medic: "MEDIC", indication: "MEDIC indication", dakp: "DAKP", dismech: "dismech", dakp_status: "DAKP status", cases: "FAERS cases", dismech_evidence: "dismech refs", n_exact: "n", note: "Hierarchy note"},
  format: {
    drug: (cid) => html`<a href="drug?id=${encodeURIComponent(cid)}">${drugLabel.get(cid) ?? cid}</a>`,
    indication: (json) => agencyCell(json),
    dismech_evidence: (json) => dismechCell(json),
  },
  width: {drug: 440, medic: 64, indication: 86, dakp: 64, dismech: 72, dakp_status: 150, cases: 84, dismech_evidence: 120, n_exact: 36, note: 240},
  sort: "n_exact", reverse: true, rows: 100, maxWidth: width,
});
```

```js
// One standalone table per exact source-combination (UpSet group), biggest first,
// off-label groups last.
id && detail.length
  ? html`<div>${comboCounts(detail).map(([combo, n]) =>
      html`<div class="combo-h">${combo} <span>· ${n} pair${n === 1 ? "" : "s"}</span></div>
           ${renderTable(detail.filter((r) => comboKey(r) === combo))}`)}</div>`
  : (id ? html`<div class="small muted">No linked drugs.</div>` : null)
```
