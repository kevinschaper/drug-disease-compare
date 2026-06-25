---
title: Drug detail
sql:
  pairs: ./data/pairs.parquet
  medev: ./data/medic_evidence.parquet
---

# Drug detail

```js
import {comboKey, comboCounts} from "./components/sources.js";
```

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
             dakp_status, CAST(dakp_cases AS INTEGER) AS cases, dismech_evidence,
             dakp_evidence, CAST(n_exact AS INTEGER) AS n_exact, note
      FROM pairs WHERE drug = ${id} ORDER BY n_exact DESC, disease_label`)
  : [];
const diseaseLabel = new Map(detail.map((r) => [r.disease, r.disease_label]));
// MEDIC's verbatim approving-agency indication text, joined on disease for this drug.
const medEv = id ? toRows(await sql`SELECT disease, evidence FROM medev WHERE drug = ${id}`) : [];
const medEvBy = new Map(medEv.map((r) => [r.disease, r.evidence]));
detail.forEach((r) => { r.indication = medEvBy.get(r.disease) ?? ""; });
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

// DAKP's underlying evidence: DailyMed SPL labels (setids) + FDA application numbers.
// Each links out to the source document — the actual label backing the approval.
const dailymedCell = (json) => {
  let v = null;
  try { v = json ? JSON.parse(json) : null; } catch (e) { v = null; }
  if (!v) return "";
  const setids = v.setids || [], fda = v.fda || [], cap = 5, out = [];
  setids.slice(0, cap).forEach((sid, i) => {
    out.push(html`<a class="dm-ref" href="https://dailymed.nlm.nih.gov/dailymed/drugInfo.cfm?setid=${sid}" target="_blank" rel="noopener" title="DailyMed label ↗">SPL${i + 1}</a>`, document.createTextNode(" "));
  });
  if (setids.length > cap) out.push(html`<span class="muted" style="font-size:11px">+${setids.length - cap}</span>`, document.createTextNode(" "));
  fda.forEach((appl) => {
    const num = String(appl).replace(/[^0-9]/g, "");
    out.push(html`<a class="dm-fda" href="https://www.accessdata.fda.gov/scripts/cder/daf/index.cfm?event=overview.process&ApplNo=${num}" target="_blank" rel="noopener" title="Drugs@FDA ↗">${appl}</a>`, document.createTextNode(" "));
  });
  return out.length ? html`${out}` : "";
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
.dm-ref, .dm-fda { font-size: 11px; font-weight: 600; white-space: nowrap; color: #4269d0; }
.dm-fda { color: #6b7280; }
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
.ind-details { margin: 0.75rem 0 0.25rem; }
.ind-agency { margin: 0.7rem 0 0.2rem; font-size: 11px; font-weight: 700; letter-spacing: 0.04em; color: var(--theme-foreground-muted, #6b7280); }
.ind-text {
  margin: 0 0 0.5rem; padding: 0.5rem 0.7rem; white-space: pre-wrap;
  font-size: 13px; line-height: 1.5; border-radius: 0 6px 6px 0;
  border-left: 3px solid color-mix(in srgb, #4269d0 55%, transparent);
  background: var(--theme-background-alt, #f4f5f7);
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

```js
// The current FDA label "Indications and Usage" fetched live from DailyMed via the
// openFDA drug-label API — straight from source, independent of MEDIC, so MEDIC's
// extraction can be checked against the actual label. Try the FDA UNII first (precise),
// then fall back to the drug name (the clique UNII can be the parent acid while the label
// uses a salt's UNII, e.g. pravastatin).
const fdaSearch = (term) =>
  fetch(`https://api.fda.gov/drug/label.json?search=${encodeURIComponent(term)}&limit=1`)
    .then((r) => (r.ok ? r.json() : null))
    .then((j) => j?.results?.[0] ?? null)
    .catch(() => null);
const fdaTerms = [
  meta?.drug_unii && `openfda.unii:"${meta.drug_unii}"`,
  meta?.drug_label && `openfda.generic_name:"${meta.drug_label}"`,
].filter(Boolean);
const fdaLabel = id
  ? await (async () => {
      for (const t of fdaTerms) {
        const r = await fdaSearch(t);
        if (r?.indications_and_usage?.length) return r;
      }
      return null;
    })()
  : null;
```

```js
id && fdaTerms.length
  ? (fdaLabel?.indications_and_usage?.length
      ? html`<details class="ind-details">
          <summary class="combo-h">FDA label — Indications &amp; Usage
            <span>· live from DailyMed (openFDA)${fdaLabel.openfda?.brand_name?.[0] ? " · " + fdaLabel.openfda.brand_name[0] : ""}</span></summary>
          <div class="ind-block">${fdaLabel.indications_and_usage.map((t) => html`<p class="ind-text">${t}</p>`)}</div>
          <div class="small muted">The FDA's source text from one SPL, not MEDIC's extraction.
            <a href="https://dailymed.nlm.nih.gov/dailymed/search.cfm?query=${encodeURIComponent(meta.drug_label)}" target="_blank" rel="noopener">Search DailyMed ↗</a></div>
        </details>`
      : html`<div class="small muted">No FDA label in openFDA for “${meta.drug_label}” (EU/Japan-only, OTC, or name mismatch).
          <a href="https://dailymed.nlm.nih.gov/dailymed/search.cfm?query=${encodeURIComponent(meta.drug_label)}" target="_blank" rel="noopener">Search DailyMed ↗</a></div>`)
  : null
```

Every disease this drug is linked to, **broken out by the exact set of sources that assert
it** (DAKP split into approved vs off-label; off-label groups last). Membership is
**exact** / **related** (a MONDO is-a hop away — see `note`) / blank; **click** an
**FDA/EMA/PMDA chip** for the per-indication agency text, or a **dismech ref** number for
its supporting text (both pin a copyable panel). The **DailyMed / FDA** column links DAKP's
underlying evidence — each `SPL` opens the DailyMed product label, each `NDA/ANDA` opens the
Drugs@FDA approval record.

```js
// shared table renderer. Explicit column widths so long disease names (and the
// hierarchy note) don't truncate.
const renderTable = (rows) => Inputs.table(rows, {
  columns: ["disease", "disease_prefix", "medic", "indication", "dakp", "dismech", "dakp_status", "dakp_evidence", "cases", "dismech_evidence", "n_exact", "note"],
  header: {disease: "Disease", disease_prefix: "Space", medic: "MEDIC", indication: "MEDIC indication", dakp: "DAKP", dismech: "dismech", dakp_status: "DAKP status", dakp_evidence: "DailyMed / FDA", cases: "FAERS cases", dismech_evidence: "dismech refs", n_exact: "n", note: "Hierarchy note"},
  format: {
    disease: (cid) => html`<a href="disease?id=${encodeURIComponent(cid)}">${diseaseLabel.get(cid) ?? cid}</a>`,
    indication: (json) => agencyCell(json),
    dakp_evidence: (json) => dailymedCell(json),
    dismech_evidence: (json) => dismechCell(json),
  },
  width: {disease: 400, disease_prefix: 60, medic: 60, indication: 86, dakp: 60, dismech: 70, dakp_status: 150, dakp_evidence: 150, cases: 80, dismech_evidence: 110, n_exact: 36, note: 220},
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
  : (id ? html`<div class="small muted">No linked diseases.</div>` : null)
```
