---
title: dismech
sql:
  pairs: ./data/pairs.parquet
---

# dismech lens

dismech is **disease-centric and narrow** — it curates ~1,150 diseases so far, and
only some of those have drug→disease edges yet. So its non-overlap can't be read
like MEDIC↔DAKP: a missing edge on a disease it hasn't curated means *"not curated"*,
not *"disagrees"*. This page reads dismech on its own terms — **how well do the broad
sources corroborate dismech's drug→disease edges, and what's novel to dismech** (worth a
look: possibly new and good, possibly wrong). "Supported" = the other source has the
exact pair **or** the same drug a MONDO is-a hop away.

```js
const summary = await FileAttachment("data/summary.json").json();
const d = summary.dismech;
const toRows = (t) => Array.from(t, (r) => Object.fromEntries(t.schema.fields.map((f) => [f.name, r[f.name]])));
// NB: `sql` interpolations are bound *parameters*, not raw SQL — the membership
// conditions below are written inline as literal SQL, not interpolated.
```

<div class="grid grid-cols-4">
  <div class="card">
    <h2>dismech edges</h2>
    <span class="big">${d.edges.toLocaleString()}</span>
    drug→disease pairs (CHEBI subset)
  </div>
  <div class="card">
    <h2>Corroborated</h2>
    <span class="big">${(d.supported / d.edges * 100).toFixed(0)}%</span>
    ${d.supported.toLocaleString()} backed by MEDIC or DAKP
  </div>
  <div class="card">
    <h2>Novel to dismech</h2>
    <span class="big">${d.novel.toLocaleString()}</span>
    no other source has it — worth a look
  </div>
  <div class="card">
    <h2>Curated diseases</h2>
    <span class="big">${d.scope_diseases.toLocaleString()}</span>
    its comparison scope
  </div>
</div>

## How dismech's edges are supported

Each dismech drug→disease edge by which broad source backs it (exact or is-a-related).

```js
const sup = toRows(await sql`
  SELECT
    CAST(sum(CASE WHEN medic IN ('exact','related') AND dakp IN ('exact','related') THEN 1 ELSE 0 END) AS INTEGER) AS both,
    CAST(sum(CASE WHEN medic IN ('exact','related') AND dakp NOT IN ('exact','related') THEN 1 ELSE 0 END) AS INTEGER) AS medic_only,
    CAST(sum(CASE WHEN medic NOT IN ('exact','related') AND dakp IN ('exact','related') THEN 1 ELSE 0 END) AS INTEGER) AS dakp_only,
    CAST(sum(CASE WHEN medic NOT IN ('exact','related') AND dakp NOT IN ('exact','related') THEN 1 ELSE 0 END) AS INTEGER) AS novel
  FROM pairs WHERE dismech = 'exact'`)[0];
const supRows = [
  {support: "MEDIC + DAKP", n: Number(sup.both)},
  {support: "MEDIC only", n: Number(sup.medic_only)},
  {support: "DAKP only", n: Number(sup.dakp_only)},
  {support: "novel (neither)", n: Number(sup.novel)},
];
```

```js
Plot.plot({
  width,
  marginLeft: 130,
  height: 200,
  x: {label: "dismech edges", grid: true},
  y: {label: null, domain: supRows.map((r) => r.support)},
  color: {domain: ["MEDIC + DAKP", "MEDIC only", "DAKP only", "novel (neither)"], range: ["#13315c", "#4269d0", "#6a9bd8", "#e15759"], legend: true},
  marks: [
    Plot.barX(supRows, {y: "support", x: "n", fill: "support", tip: true}),
    Plot.text(supRows, {y: "support", x: "n", text: (r) => r.n.toLocaleString(), dx: 16}),
    Plot.ruleX([0]),
  ],
})
```

<style>
.ev-pmid { font-variant-numeric: tabular-nums; padding: 0 1px; }
.ev-tip {
  position: fixed;
  z-index: 1000;
  display: none;
  max-width: 420px;
  padding: 0.5rem 0.65rem;
  font-size: 12.5px;
  line-height: 1.45;
  background: var(--theme-background-alt, #f4f5f7);
  color: var(--theme-foreground, #1b1e23);
  border: 1px solid color-mix(in srgb, currentColor 20%, transparent);
  border-radius: 7px;
  box-shadow: 0 6px 22px rgba(0, 0, 0, 0.28);
  pointer-events: none;
}
.ev-tip.show { display: block; }
.ev-tip-pmid {
  display: block;
  margin-bottom: 0.25rem;
  font-weight: 600;
  font-size: 11px;
  color: var(--theme-foreground-muted, #6b7280);
}
</style>

## Novel to dismech — worth a look

dismech edges no other source asserts (not even a MONDO is-a hop away). These are
dismech's distinctive, mechanism-driven calls — potentially new and correct, or
extraction errors. Ranked by **dismech PMID support** (more cited = easier to check).

```js
const novel = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label, disease_prefix,
         CAST(dismech_pubs AS INTEGER) AS pubs, dismech_evidence AS evidence
  FROM pairs WHERE dismech = 'exact'
    AND medic NOT IN ('exact','related') AND dakp NOT IN ('exact','related')
  ORDER BY dismech_pubs DESC, drug_label`);
const nDrug = new Map(novel.map((r) => [r.drug, r.drug_label]));
const nDis = new Map(novel.map((r) => [r.disease, r.disease_label]));

// One shared, theme-styled tooltip positioned with fixed coords on hover, so it
// escapes the table's scroll-container clipping (a pure-CSS tooltip would be cut off).
const evTip = (() => {
  const el = document.createElement("div");
  el.className = "ev-tip";
  document.body.appendChild(el);
  invalidation.then(() => el.remove());
  return el;
})();

const pubmed = (json) => {
  let ev = [];
  try { ev = json ? JSON.parse(json) : []; } catch (e) { ev = []; }
  if (!ev.length) return "";
  const links = ev.map((e, i) => {
    const a = html`<a class="ev-pmid" href="https://pubmed.ncbi.nlm.nih.gov/${e.pmid.replace("PMID:", "")}" target="_blank" rel="noopener">${i + 1}</a>`;
    const text = e.text || e.pmid;
    a.addEventListener("mouseenter", () => {
      evTip.innerHTML = "";
      evTip.append(html`<span class="ev-tip-pmid">${e.pmid}</span>`, document.createTextNode(text));
      evTip.classList.add("show");
      const r = a.getBoundingClientRect();
      const w = evTip.getBoundingClientRect().width;
      const h = evTip.getBoundingClientRect().height;
      evTip.style.left = Math.max(8, Math.min(r.left, window.innerWidth - w - 8)) + "px";
      const below = r.bottom + 6;
      evTip.style.top = (below + h > window.innerHeight - 8 ? r.top - h - 6 : below) + "px";
    });
    a.addEventListener("mouseleave", () => evTip.classList.remove("show"));
    return a;
  });
  return html`${links.flatMap((a, i) => (i ? [document.createTextNode(" "), a] : [a]))}`;
};
const novelSearch = view(Inputs.search(novel, {placeholder: `search ${novel.length.toLocaleString()} novel pairs…`}));
```

Each PMID is a numbered link to PubMed; **hover a number to read dismech's supporting
text** for that citation.

```js
Inputs.table(novelSearch, {
  columns: ["drug", "disease", "disease_prefix", "evidence"],
  header: {drug: "Drug", disease: "Disease", disease_prefix: "Space", evidence: "dismech PMIDs (→ PubMed)"},
  format: {
    drug: (cid) => html`<a href="drug?id=${encodeURIComponent(cid)}">${nDrug.get(cid) ?? cid}</a> <span class="small muted">${cid}</span>`,
    disease: (cid) => html`<a href="disease?id=${encodeURIComponent(cid)}">${nDis.get(cid) ?? cid}</a> <span class="small muted">${cid}</span>`,
    evidence: (json) => pubmed(json),
  },
  sort: "pubs",
  reverse: true,
  rows: 18,
  width,
})
```

## dismech gaps — within its curated diseases

The flip side: diseases dismech *has* curated, where MEDIC or DAKP carry a drug edge
dismech doesn't. Because the disease is in dismech's scope, these are genuine gaps
(candidate edges to add), not just uncurated territory. ${d.gaps_in_scope.toLocaleString()}
pairs in total.

```js
const gaps = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label, medic, dakp, dakp_status,
         CAST(dakp_cases AS INTEGER) AS cases
  FROM pairs WHERE dismech = '' AND dismech_scope
    AND (medic = 'exact' OR dakp = 'exact')
  ORDER BY dakp_cases DESC, drug_label`);
const gDrug = new Map(gaps.map((r) => [r.drug, r.drug_label]));
const gDis = new Map(gaps.map((r) => [r.disease, r.disease_label]));
const gapSearch = view(Inputs.search(gaps, {placeholder: `search ${gaps.length.toLocaleString()} gap pairs…`}));
```

```js
Inputs.table(gapSearch, {
  columns: ["drug", "disease", "medic", "dakp", "dakp_status", "cases"],
  header: {drug: "Drug", disease: "Disease", medic: "MEDIC", dakp: "DAKP", dakp_status: "DAKP status", cases: "FAERS cases"},
  format: {
    drug: (cid) => html`<a href="drug?id=${encodeURIComponent(cid)}">${gDrug.get(cid) ?? cid}</a> <span class="small muted">${cid}</span>`,
    disease: (cid) => html`<a href="disease?id=${encodeURIComponent(cid)}">${gDis.get(cid) ?? cid}</a> <span class="small muted">${cid}</span>`,
  },
  sort: "cases",
  reverse: true,
  rows: 18,
  width,
})
```
