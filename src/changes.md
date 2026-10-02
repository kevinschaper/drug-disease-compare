---
title: Version changes
sql:
  churn: ./data/changes.parquet
---

# Version changes

Every source moved since the last build of this site. Before reading the head-to-head,
it helps to know **how each source changed relative to its own previous release** —
otherwise a shift in agreement can't be attributed to the source that moved.

```js
const ch = await FileAttachment("data/changes.json").json();
const fmt = (n) => n.toLocaleString();
const SRC = {medic: "MEDIC", dakp: "DAKP", dismech: "dismech"};
const LENS = {treats: "indications", approved: "approved", "off-label": "off-label (FAERS)",
              contraindicated: "contraindications"};
```

```js
Inputs.table(Object.values(ch.sources).map((s) => ({
  source: SRC[s.source], old: s.versions.old, new: s.versions.new,
  edges: `${fmt(s.raw.old.edges)} → ${fmt(s.raw.new.edges)}`,
})), {header: {source: "Source", old: "Previous release", new: "Latest release", edges: "Raw edges"},
      sort: null, select: false})
```

Both releases of each source are re-resolved through the **same** Node Normalizer
snapshot and MONDO graph, so a difference below is a change in what the source asserts
(or in how it grounds its own identifiers), not drift in our reconciliation. Each
churned pair is explained where possible:

<div class="reason-key">
  <span><i style="background: var(--r-regrounded)"></i><b>re-grounded</b> — same pair, the drug under a different CURIE of the same FDA/GSRS active moiety (salt ↔ parent, brand ↔ ingredient, a re-minted id)</span>
  <span><i style="background: var(--r-changed)"></i><b>changed</b> — same drug, but no nearby disease in the other release: a genuine content change</span>
  <span><i style="background: var(--r-regrained)"></i><b>re-grained</b> — same drug on a disease 1–2 MONDO is-a hops away: a granularity change</span>
  <span><i style="background: var(--r-flip)"></i><b>status flip</b> — (DAKP) moved between approved and off-label</span>
  <span><i style="background: var(--r-drug)"></i><b>drug new / dropped</b> — the drug isn't in the other release at all</span>
</div>

<style>
:root {
  --r-regrounded: #2a78d6; --r-changed: #eb6834; --r-regrained: #1baf7a;
  --r-flip: #eda100; --r-drug: #e87ba4; --r-mixed: #9ec3ec;
}
@media (prefers-color-scheme: dark) {
  :root {
    --r-regrounded: #3987e5; --r-changed: #d95926; --r-regrained: #199e70;
    --r-flip: #c98500; --r-drug: #d55181; --r-mixed: #2c5a8f;
  }
}
.reason-key { display: flex; flex-direction: column; gap: 0.3rem; margin: 0.5rem 0 1rem; font-size: 13px; }
.reason-key i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 6px; vertical-align: -1px; }
.delta-up { color: var(--theme-foreground-focus, #2a78d6); }
.delta-down { color: var(--theme-foreground-muted, #6b7280); }
.lens-cards .card h2 { margin-bottom: 0.2rem; }
.lens-cards .sub { font-size: 12px; color: var(--theme-foreground-muted, #6b7280); line-height: 1.5; }
</style>

```js
const REASONS = ["re-grounded", "changed", "re-grained", "status flip", "drug new / dropped"];
const RCOLOR = ["var(--r-regrounded)", "var(--r-changed)", "var(--r-regrained)", "var(--r-flip)", "var(--r-drug)"];
const norm = (r) => (r === "drug new" || r === "drug dropped" ? "drug new / dropped" : r);

// one card per lens: old -> new, kept / added / removed
function lensCards(src) {
  const s = ch.sources[src];
  return html`<div class="grid grid-cols-4 lens-cards">${Object.entries(s.lenses).map(([lens, L]) => {
    const d = L.new - L.old;
    return html`<div class="card">
      <h2>${LENS[lens]}</h2>
      <span class="big">${fmt(L.new)}</span>
      <span class="${d >= 0 ? "delta-up" : "delta-down"}">${d >= 0 ? "+" : "−"}${fmt(Math.abs(d))}</span>
      <div class="sub">pairs, was ${fmt(L.old)}<br>
        kept ${fmt(L.kept)} · +${fmt(L.added)} new · −${fmt(L.removed)} gone<br>
        drugs ${fmt(L.drugs.old)} → ${fmt(L.drugs.new)} · diseases ${fmt(L.diseases.old)} → ${fmt(L.diseases.new)}<br>
        old↔new Jaccard ${L.jaccard.toFixed(2)}</div>
    </div>`;
  })}</div>`;
}

// diverging churn bar per lens: removed (left, by reason) | added (right, by reason)
function churnChart(src) {
  const s = ch.sources[src];
  const rows = [];
  for (const [lens, L] of Object.entries(s.lenses)) {
    for (const change of ["removed", "added"]) {
      const agg = new Map();
      for (const [r, n] of Object.entries(L.reasons[change] ?? {})) agg.set(norm(r), (agg.get(norm(r)) ?? 0) + n);
      for (const [reason, n] of agg) rows.push({lens: LENS[lens], change, reason, n, x: change === "removed" ? -n : n});
    }
  }
  const lenses = Object.keys(s.lenses).map((l) => LENS[l]);
  return Plot.plot({
    width, height: 50 + 46 * lenses.length, marginLeft: 140, marginRight: 20,
    x: {label: "← pairs gone · pairs new →", tickFormat: (d) => Math.abs(d).toLocaleString(), grid: true},
    y: {label: null, domain: lenses},
    color: {domain: REASONS, range: RCOLOR, legend: true},
    marks: [
      Plot.barX(rows, Plot.stackX({y: "lens", x: "x", fill: "reason", order: REASONS, inset: 1, rx: 2,
        tip: true, title: (d) => `${d.lens} · ${d.change}\n${d.reason}: ${d.n.toLocaleString()} pairs`})),
      Plot.ruleX([0], {strokeWidth: 1.5}),
    ],
  });
}

function churnDrugs(src, lens) {
  return Inputs.table(ch.sources[src].lenses[lens].top_churn_drugs, {
    columns: ["drug_label", "drug", "added", "removed"],
    header: {drug_label: "Drug", drug: "ID", added: "pairs new", removed: "pairs gone"},
    format: {drug_label: (l, i, data) => html`<a href="drug?id=${encodeURIComponent(data[i].drug)}">${l}</a>`},
    rows: 10, select: false, sort: null,
  });
}

function rawTable(src) {
  const {old: o, new: n} = ch.sources[src].raw;
  const keys = (a, b) => [...new Set([...Object.keys(a), ...Object.keys(b)])];
  const rows = [
    {what: "edges", old: fmt(o.edges), new: fmt(n.edges)},
    {what: "distinct (subject, predicate, object)", old: fmt(o.triples), new: fmt(n.triples)},
    {what: "distinct subjects / objects", old: `${fmt(o.subjects)} / ${fmt(o.objects)}`, new: `${fmt(n.subjects)} / ${fmt(n.objects)}`},
    ...keys(o.predicates, n.predicates).map((p) => ({what: p, old: fmt(o.predicates[p] ?? 0), new: fmt(n.predicates[p] ?? 0)})),
    {what: "subject id prefixes", old: Object.entries(o.subject_prefixes).slice(0, 6).map(([k, v]) => `${k} ${fmt(v)}`).join(", "),
                                  new: Object.entries(n.subject_prefixes).slice(0, 6).map(([k, v]) => `${k} ${fmt(v)}`).join(", ")},
    {what: "object id prefixes", old: Object.entries(o.object_prefixes).slice(0, 6).map(([k, v]) => `${k} ${fmt(v)}`).join(", "),
                                 new: Object.entries(n.object_prefixes).slice(0, 6).map(([k, v]) => `${k} ${fmt(v)}`).join(", ")},
  ];
  if (Object.keys(n.agencies).length) rows.push({what: "regulator (per edge)", old: Object.entries(o.agencies).map(([k, v]) => `${k} ${fmt(v)}`).join(", "), new: Object.entries(n.agencies).map(([k, v]) => `${k} ${fmt(v)}`).join(", ")});
  if (Object.keys(n.reliability).length) rows.push({what: "reliability tier (per edge)", old: "—", new: Object.entries(n.reliability).map(([k, v]) => `${k} ${fmt(v)}`).join(", ")});
  if (Object.keys(n.approval_status).length) rows.push({what: "approval status (treats edges)", old: Object.entries(o.approval_status).map(([k, v]) => `${k} ${fmt(v)}`).join(", "), new: Object.entries(n.approval_status).map(([k, v]) => `${k} ${fmt(v)}`).join(", ")});
  return Inputs.table(rows, {header: {what: "Raw (pre-normalization)", old: "previous", new: "latest"},
    width: {what: 260}, select: false, sort: null, rows: rows.length, layout: "auto"});
}

const M = ch.sources.medic.lenses, D = ch.sources.dakp.lenses, X = ch.sources.dismech.lenses;
const r = (L, ch_, k) => L.reasons[ch_]?.[k] ?? 0;
```

## MEDIC — ${ch.sources.medic.versions.old} → ${ch.sources.medic.versions.new}

The redesigned MeDIC pipeline is a different export, not an increment: it emits **one edge
per regulator assertion** (${fmt(ch.sources.medic.raw.new.edges)} edges over
${fmt(ch.sources.medic.raw.new.triples)} distinct triples) where medic-ingest emitted one
per pair, adds **contraindications** (${fmt(M.contraindicated.new)} canonical pairs) and
**CDSCO (India)** as a fourth regulator, and carries a per-pair **reliability tier**
(HIGH/MEDIUM/LOW) and the label's verbatim section text on every edge.

Its indication set is **more conservative**: ${fmt(M.treats.old)} → ${fmt(M.treats.new)}
canonical pairs, keeping ${fmt(M.treats.kept)}. Of the
${fmt(M.treats.removed)} pairs gone, ${fmt(r(M.treats, "removed", "re-grounded"))} are the same
pair under a sibling drug CURIE and ${fmt(r(M.treats, "removed", "re-grained"))} moved to a
nearby MONDO term; ${fmt(r(M.treats, "removed", "changed"))} are content changes on a drug
MEDIC still covers, and ${fmt(r(M.treats, "removed", "drug dropped"))} belong to drugs no
longer in the indication set.

**Drug grounding.** The redesign grounds to recent ChEBI ids (e.g. `CHEBI:749494`
adalimumab, `CHEBI:749495` bevacizumab) and DRON (rituximab, pembrolizumab) that the
Node Normalizer snapshot doesn't know — without help, **~28% of its treats edges** would
match nothing anywhere. We rescue a CURIE the Node Normalizer can't resolve by matching
MEDIC's own node name *exactly* to an RxNorm concept (${fmt(ch.repaired_drugs)} drugs
repaired, see [methods](./methods)). It also grounds more often to salt/hydrate forms
(gentamicin *sulfate*, vancomycin *hydrochloride*), which the moiety layer bridges, and
at least one regression worth reporting upstream: cyclophosphamide → `CHEBI:1864`
**4-hydroxycyclophosphamide** (its active metabolite).

```js
lensCards("medic")
```

```js
churnChart("medic")
```

<details><summary>Raw shape, previous vs latest</summary>

```js
rawTable("medic")
```

</details>

<details><summary>Drugs with the most indication churn</summary>

```js
churnDrugs("medic", "treats")
```

</details>

## DAKP — ${ch.sources.dakp.versions.old} → ${ch.sources.dakp.versions.new}

DAKP moved from the rtx.ai build (`infores:multiomics-drugapprovals`) to the Tablassert
build on Hugging Face (`infores:drugapprovals-kp`), and roughly doubled:
${fmt(ch.sources.dakp.raw.old.edges)} → ${fmt(ch.sources.dakp.raw.new.edges)} edges. It
now ingests **EMA/EPAR** alongside DailyMed and FAERS, so its **approved** set nearly
tripled (${fmt(D.approved.old)} → ${fmt(D.approved.new)} pairs) and contraindications
grew ${fmt(D.contraindicated.old)} → ${fmt(D.contraindicated.new)}.

**Approval status was re-adjudicated.** ${fmt(r(D.approved, "removed", "status flip"))}
pairs that were *approved* are now *off-label*, and
${fmt(r(D.approved, "added", "status flip"))} went the other way.

**Drug grounding got coarser in one respect.** About 2,700 drugs now ground to **UMLS
concepts** — mostly brand names (Gemzar, Endoxan, Zometa, Rivotril, Vioxx, …) plus
combination products — that the Node Normalizer can't link to an ingredient; ~11% of its
treats edges. The previous build
grounded these to ingredient-level CHEBI/UNII. Strict agreement can't see through a brand;
the moiety layer can (via an exact RxNorm brand → ingredient lookup), so those show up
as **re-grounded** churn here and as moiety-bridged agreement on the [overview](./).
The disease axis also widened from MONDO/HP only to include UMLS and NCIT terms.

```js
lensCards("dakp")
```

```js
churnChart("dakp")
```

<details><summary>Raw shape, previous vs latest</summary>

```js
rawTable("dakp")
```

</details>

<details><summary>Drugs with the most approved-indication churn</summary>

```js
churnDrugs("dakp", "approved")
```

</details>

## dismech — ${ch.sources.dismech.versions.old} → ${ch.sources.dismech.versions.new}

dismech is growing, and almost purely additively: it now curates
${fmt(X.treats.diseases.new)} diseases with drug edges (was ${fmt(X.treats.diseases.old)}),
and its CHEBI drug→disease subset went ${fmt(X.treats.old)} → ${fmt(X.treats.new)} pairs
with only ${fmt(X.treats.removed)} removed. Its treatment edges no longer use MAXO medical
actions as subjects (NCIT + CHEBI only), which doesn't affect the drug subset compared here.

```js
lensCards("dismech")
```

```js
churnChart("dismech")
```

<details><summary>Raw shape, previous vs latest</summary>

```js
rawTable("dismech")
```

</details>

## Agreement trajectory

How the indication-grade overlap between each pair of sources moved, and **which source's
release moved it**. Each row holds one side fixed while swapping the other's release:
going from *previous ↔ previous* to *latest ↔ latest* through the two mixed cells
separates the effect of each source's change.

```js
const traj = ch.trajectory.map((t) => ({
  pair: t.pair,
  prev: t.old_old.shared,
  a_moved: `${fmt(t.new_old.shared)} (${t.a} latest)`,
  b_moved: `${fmt(t.old_new.shared)} (${t.b} latest)`,
  latest: t.new_new.shared,
  jaccard: `${t.old_old.jaccard.toFixed(3)} → ${t.new_new.jaccard.toFixed(3)}`,
}));
```

```js
const STEP_FILL = {"previous ↔ previous": "#9498a0", "one side latest": "var(--r-mixed)", "latest ↔ latest": "var(--r-regrounded)"};
const trajBars = ch.trajectory.flatMap((t) => [
  {pair: t.pair, step: "previous ↔ previous", kind: "previous ↔ previous", ...t.old_old},
  {pair: t.pair, step: `only ${t.a} on latest`, kind: "one side latest", ...t.new_old},
  {pair: t.pair, step: `only ${t.b} on latest`, kind: "one side latest", ...t.old_new},
  {pair: t.pair, step: "latest ↔ latest", kind: "latest ↔ latest", ...t.new_new},
]);
```

```js
const trajMax = d3.max(trajBars, (d) => d.shared);
display(html`<div class="traj-legend">${Object.entries(STEP_FILL).map(([k, c]) => html`<span><i style="background:${c}"></i>${k}</span>`)}</div>
${ch.trajectory.map((t) => {
  const rows = trajBars.filter((d) => d.pair === t.pair);
  return html`<div class="traj-panel"><h3>${t.pair}</h3>${Plot.plot({
    width, height: 140, marginLeft: 220, marginRight: 70,
    x: {label: null, domain: [0, trajMax], grid: true, axis: t === ch.trajectory.at(-1) ? "bottom" : null},
    y: {label: null, domain: rows.map((d) => d.step)},
    color: {domain: Object.keys(STEP_FILL), range: Object.values(STEP_FILL)},
    marks: [
      Plot.barX(rows, {y: "step", x: "shared", fill: "kind", rx: 2, insetTop: 3, insetBottom: 3, tip: true,
        title: (d) => `${d.step}\n${d.shared.toLocaleString()} shared (Jaccard ${d.jaccard.toFixed(3)})`}),
      Plot.text(rows, {y: "step", x: "shared", text: (d) => d.shared.toLocaleString(), dx: 6, textAnchor: "start", fontSize: 11}),
      Plot.ruleX([0]),
    ],
  })}</div>`;
})}`);
```

<style>
.traj-legend { display: flex; gap: 1.2rem; font-size: 12px; margin: 0.4rem 0; }
.traj-legend i { display: inline-block; width: 10px; height: 10px; border-radius: 2px; margin-right: 5px; vertical-align: -1px; }
.traj-panel h3 { margin: 0.6rem 0 0; font-size: 13px; }
</style>

Each panel holds one source pair; the middle bars put just one source on its latest
release, so comparing them with the top bar shows which source's change moved the overlap.

```js
Inputs.table(traj, {
  header: {pair: "Source pair", prev: "previous ↔ previous", a_moved: "first source moved",
           b_moved: "second source moved", latest: "latest ↔ latest", jaccard: "Jaccard"},
  format: {prev: fmt, latest: fmt},
  width: {pair: 200}, select: false, sort: null,
})
```

```js
const md = ch.trajectory.find((t) => t.pair === "MEDIC + DAKP-approved");
```

The flagship **MEDIC ↔ DAKP-approved** overlap went ${fmt(md.old_old.shared)} →
${fmt(md.new_new.shared)} shared pairs. Holding DAKP at its previous release, MEDIC's
change alone takes it to ${fmt(md.new_old.shared)}; holding MEDIC, DAKP's change alone
gives ${fmt(md.old_new.shared)}. So the drop is **MEDIC's** narrower indication set, while
DAKP's tripled approved set adds few *new* MEDIC matches. Of the ~12.6k latest
DAKP-approved pairs MEDIC lacks, about half involve a drug MEDIC doesn't carry at all,
~4.3k sit on UMLS/NCIT/EFO/MeSH disease terms (MEDIC is mostly MONDO), ~1.3k are one
MONDO hop from a MEDIC pair (granularity), and ~900 match MEDIC only through a same-moiety
sibling drug (mostly DAKP's brand-name groundings). Both dismech pairings roughly
doubled, tracking dismech's own growth.

## Browse the churn

Every canonical pair that appeared or disappeared between releases, with its reason.

```js
const fSource = view(Inputs.select(["medic", "dakp", "dismech"], {label: "Source", format: (s) => SRC[s]}));
```

```js
const lensOpts = Object.keys(ch.sources[fSource].lenses);
const fLens = view(Inputs.select(lensOpts, {label: "Lens", format: (l) => LENS[l]}));
```

```js
const fChange = view(Inputs.radio(["both", "added", "removed"], {label: "Change", value: "both"}));
const fReason = view(Inputs.select(["any", "re-grounded", "changed", "re-grained", "status flip", "drug new", "drug dropped"], {label: "Reason", value: "any"}));
```

```js
const toRows = (t) => Array.from(t, (r) => Object.fromEntries(t.schema.fields.map((f) => [f.name, r[f.name]])));
const churnRows = toRows(await sql`
  SELECT drug, drug_label, disease, disease_label, change, reason
  FROM churn
  WHERE source = ${fSource} AND lens = ${fLens}
    AND (${fChange} = 'both' OR change = ${fChange})
    AND (${fReason} = 'any' OR reason = ${fReason})
  ORDER BY drug_label, disease_label`);
const churnSearch = view(Inputs.search(churnRows, {placeholder: "search drug or disease…"}));
```

```js
Inputs.table(churnSearch, {
  columns: ["drug_label", "disease_label", "change", "reason", "drug", "disease"],
  header: {drug_label: "Drug", disease_label: "Disease", change: "Change", reason: "Reason", drug: "Drug ID", disease: "Disease ID"},
  format: {
    drug_label: (l, i, data) => html`<a href="drug?id=${encodeURIComponent(data[i].drug)}">${l}</a>`,
    disease_label: (l, i, data) => html`<a href="disease?id=${encodeURIComponent(data[i].disease)}">${l}</a>`,
  },
  width: {drug_label: 280, disease_label: 340, change: 80, reason: 110, drug: 180, disease: 160},
  rows: 25, select: false, layout: "fixed",
})
```

A **removed** pair links to the detail page of a drug or disease that may now only exist in
the previous release — the detail pages show the latest releases.
