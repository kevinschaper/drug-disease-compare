---
title: Redundancy
toc: false
---

# Redundancy — adjacent-granularity duplicate edges

A source can count one clinical concept as several edges. The cleanest case is
**hierarchical**: it asserts a disease *and* that disease's **direct is-a parent** for the
same drug — e.g. *leukemia* plus *acute / chronic / lymphoid / myeloid leukemia*, or
*melanoma* plus *metastatic melanoma*. The parent already covers the children, so the extra
edges inflate counts without adding a distinct assertion.

This page collapses each `(drug, source)` edge set by **direct-parent containment** (MONDO or
HP is-a, bounded to one hop so a broad catch-all like *cancer* doesn't swallow every distant
specific) and reports **concepts** = edges left after collapse, and **factor** = raw ÷
concepts.

**Out of scope here:** cross-ontology *synonym* redundancy — the same concept as a UMLS, EFO,
and HP term that NodeNorm didn't merge (ondansetron's nausea terms). That needs a concept
mapping layer and isn't counted below.

```js
const red = await FileAttachment("data/redundancy.json").json();
const SRC = ["medic", "dakp", "dismech"].filter((s) => red.by_source[s]);
const LABEL = {medic: "MEDIC", dakp: "DAKP", dismech: "dismech"};
```

<style>
.src { display:inline-block; min-width:3.4em; text-align:center; padding:0 6px; margin-right:4px;
  border-radius:5px; font-size:10px; font-weight:700; vertical-align:1px; }
.src.medic { background: color-mix(in srgb, #4269d0 20%, transparent); }
.src.dakp { background: color-mix(in srgb, #e15759 22%, transparent); }
.src.dismech { background: color-mix(in srgb, #59a14f 22%, transparent); }
.grp { font-size: 12.5px; line-height: 1.5; }
.grp .kept { font-weight: 600; }
.grp .sub { color: var(--theme-foreground-muted, #6b7280); }
</style>

```js
display(html`<div class="grid grid-cols-3">${SRC.map((s) => {
  const r = red.by_source[s];
  return html`<div class="card"><h2>${LABEL[s]} redundancy</h2>
    <span class="big">${r.factor}×</span>
    <div class="small muted">${r.redundant_edges.toLocaleString()} redundant of ${r.raw.toLocaleString()} edges → ${r.concepts.toLocaleString()} concepts</div></div>`;
})}</div>`);
```

## Worst offenders

Drug + source pairs with the most direct-parent-redundant edges. Each **collapse** shows the
asserted parent (kept) and the more-specific children it already subsumes.

```js
const srcSel = view(Inputs.radio(["all", ...SRC], {label: "Source", value: "all",
  format: (v) => v === "all" ? "All" : LABEL[v]}));
const search = view(Inputs.text({label: "Search", placeholder: "drug name…"}));
```

```js
const rows = red.clusters.filter((c) =>
  (srcSel === "all" || c.source === srcSel) &&
  (!search || c.drug_label.toLowerCase().includes(search.toLowerCase())));
const groupCell = (groups) => html`<div class="grp">${groups.map((g) =>
  html`<div><span class="kept">${g.kept}</span> <span class="sub">← ${g.subsumed.join(", ")}</span></div>`)}</div>`;
display(html`<div style="max-height:620px;overflow:auto;border:1px solid var(--theme-foreground-faintest);border-radius:6px">
<table style="margin:0">
<thead><tr><th>drug</th><th>source</th><th style="text-align:right">raw</th><th style="text-align:right">concepts</th><th style="text-align:right">redundant</th><th>collapses</th></tr></thead>
<tbody>${rows.map((c) => html`<tr>
<td><a href="drug?id=${encodeURIComponent(c.drug)}">${c.drug_label}</a></td>
<td><span class="src ${c.source}">${LABEL[c.source]}</span></td>
<td style="text-align:right;font-variant-numeric:tabular-nums">${c.raw}</td>
<td style="text-align:right;font-variant-numeric:tabular-nums">${c.concepts}</td>
<td style="text-align:right;font-variant-numeric:tabular-nums">${c.redundant}</td>
<td>${groupCell(c.groups)}</td>
</tr>`)}</tbody></table></div>`);
display(html`<div class="muted" style="font-size:12px;margin-top:4px">${rows.length} of ${red.clusters.length} clusters shown (top 400 by redundant-edge count)</div>`);
```
