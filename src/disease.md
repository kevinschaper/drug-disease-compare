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
// Click an FDA/EMA/PMDA chip or a dismech ref to PIN a panel with the verbatim text. It
// stays open and is selectable/copyable; close with ×, the same chip again, or a click
// outside. (Hover tooltips vanished before you could select the text.)
const evTip = (() => {
  const el = document.createElement("div");
  el.className = "ev-tip";
  el.addEventListener("click", (e) => e.stopPropagation());  // selecting inside doesn't close
  const onDoc = () => { el.classList.remove("show"); el._anchor = null; };
  document.addEventListener("click", onDoc);
  document.body.appendChild(el);
  invalidation.then(() => { el.remove(); document.removeEventListener("click", onDoc); });
  return el;
})();

function showEvidence(anchor, header, body, href) {
  if (evTip.classList.contains("show") && evTip._anchor === anchor) {  // toggle off
    evTip.classList.remove("show"); evTip._anchor = null; return;
  }
  evTip._anchor = anchor;
  evTip.innerHTML = "";
  const close = html`<button type="button" class="ev-close" aria-label="close">×</button>`;
  close.addEventListener("click", (e) => { e.stopPropagation(); evTip.classList.remove("show"); evTip._anchor = null; });
  evTip.append(html`<div class="ev-tip-head"><span class="ev-tip-pmid">${header}</span>${close}</div>`,
               document.createTextNode(body));
  if (href) evTip.append(html`<div class="ev-tip-link"><a href="${href}" target="_blank" rel="noopener">PubMed ↗</a></div>`);
  evTip.classList.add("show");
  const r = anchor.getBoundingClientRect();
  const w = evTip.getBoundingClientRect().width;
  const h = evTip.getBoundingClientRect().height;
  evTip.style.left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8)) + "px";
  const below = r.bottom + 6;
  evTip.style.top = (below + h > window.innerHeight - 8 ? r.top - h - 6 : below) + "px";
}

// FDA/EMA/PMDA chips — click to pin the verbatim approving-agency indication text.
const agencyCell = (json) => {
  let ev = [];
  try { ev = json ? JSON.parse(json) : []; } catch (e) { ev = []; }
  if (!ev.length) return "";
  const chips = ev.map((e) => {
    const c = html`<button type="button" class="agency-chip">${e.agency}</button>`;
    c.addEventListener("click", (x) => { x.stopPropagation(); showEvidence(c, `${e.agency} indication`, e.text); });
    return c;
  });
  return html`${chips.flatMap((c, i) => (i ? [document.createTextNode(" "), c] : [c]))}`;
};

// dismech refs — click a number to pin its supporting text (with a PubMed link).
const dismechCell = (json) => {
  let ev = [];
  try { ev = json ? JSON.parse(json) : []; } catch (e) { ev = []; }
  if (!ev.length) return "";
  const links = ev.map((e, i) => {
    const a = html`<button type="button" class="ev-pmid">${i + 1}</button>`;
    const href = `https://pubmed.ncbi.nlm.nih.gov/${e.pmid.replace("PMID:", "")}`;
    a.addEventListener("click", (x) => { x.stopPropagation(); showEvidence(a, e.pmid, e.text || "(no supporting text)", href); });
    return a;
  });
  return html`${links.flatMap((a, i) => (i ? [document.createTextNode(" "), a] : [a]))}`;
};
```

<style>
.agency-chip {
  appearance: none; font: inherit; color: inherit;
  display: inline-block; padding: 0 6px; border-radius: 6px;
  font-size: 10.5px; font-weight: 600; letter-spacing: 0.02em; cursor: pointer;
  border: 1px solid transparent;
  background: color-mix(in srgb, var(--theme-foreground, #1b1e23) 9%, transparent);
}
.agency-chip:hover { border-color: color-mix(in srgb, currentColor 32%, transparent); }
.ev-pmid {
  appearance: none; font: inherit; cursor: pointer; border: none; background: none; padding: 0 2px;
  color: #4269d0; text-decoration: underline; font-variant-numeric: tabular-nums;
}
.ev-tip {
  position: fixed; z-index: 1000; display: none; max-width: 460px; max-height: 55vh; overflow: auto;
  padding: 0.5rem 0.65rem; font-size: 12.5px; line-height: 1.45; white-space: pre-wrap;
  background: var(--theme-background-alt, #f4f5f7); color: var(--theme-foreground, #1b1e23);
  border: 1px solid color-mix(in srgb, currentColor 20%, transparent);
  border-radius: 7px; box-shadow: 0 6px 22px rgba(0, 0, 0, 0.28);
  pointer-events: auto; user-select: text;
}
.ev-tip.show { display: block; }
.ev-tip-head { display: flex; justify-content: space-between; align-items: baseline; gap: 1rem; margin-bottom: 0.3rem; }
.ev-tip-pmid { font-weight: 600; font-size: 11px; color: var(--theme-foreground-muted, #6b7280); }
.ev-close { appearance: none; border: none; background: none; cursor: pointer; padding: 0; font-size: 15px; line-height: 1; color: var(--theme-foreground-muted, #6b7280); }
.ev-tip-link { margin-top: 0.4rem; font-size: 11px; }
.combo-h { margin: 1.4rem 0 0.35rem; font-size: 14px; font-weight: 600; }
.combo-h span { font-weight: 400; color: var(--theme-foreground-muted, #6b7280); }
summary.combo-h { cursor: pointer; }
details.combo-d { margin-top: 0.4rem; }
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
// off-label groups last. Off-label (FAERS) groups are collapsed by default.
id && detail.length
  ? html`<div>${comboCounts(detail).map(([combo, n]) => {
      const rows = detail.filter((r) => comboKey(r) === combo);
      const head = html`${combo} <span>· ${n} pair${n === 1 ? "" : "s"}</span>`;
      return combo.includes("DAKP off-label")
        ? html`<details class="combo-d"><summary class="combo-h">${head} <span class="small muted">— FAERS off-label, click to expand</span></summary>${renderTable(rows)}</details>`
        : html`<div class="combo-h">${head}</div>${renderTable(rows)}`;
    })}</div>`
  : (id ? html`<div class="small muted">No linked drugs.</div>` : null)
```
