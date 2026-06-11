# De-conflation

The disease axis is reconciled MONDO-centrically. For every disease CURIE in either
feed we fetch the full SRI Node Normalizer clique and **prefer its MONDO member**;
we keep the original term (typically HP) only when the clique contains no MONDO.
This undoes node-normalizer collisions where a phenotype and a disease of the same
name share a clique — e.g. `HP:0001250` (Seizure) ↔ `MONDO:0005027` (epilepsy) —
by pulling the MONDO identity back out, MONDO-centrically.

```js
const dc = await FileAttachment("data/deconflation.json").json();
const summary = dc.summary;
const total = Object.values(summary).reduce((a, b) => a + b, 0);
```

<div class="grid grid-cols-3">
  <div class="card">
    <h2>HP → MONDO de-conflated</h2>
    <span class="big">${(summary.hp_to_mondo ?? 0).toLocaleString()}</span>
    HP-origin terms with a MONDO in their clique
  </div>
  <div class="card">
    <h2>Kept as HP</h2>
    <span class="big">${(summary.kept_hp ?? 0).toLocaleString()}</span>
    genuine phenotypes, no MONDO in clique
  </div>
  <div class="card">
    <h2>Disease CURIEs resolved</h2>
    <span class="big">${total.toLocaleString()}</span>
    distinct, across both feeds
  </div>
</div>

## Normalization outcomes

How each distinct disease CURIE resolved. `already_mondo` and `lifted_to_mondo`
(e.g. DOID/UMLS → MONDO) are the bulk; `hp_to_mondo` is the de-conflation of
interest; `kept_hp` / `kept_*` are terms with no MONDO equivalent.

```js
const outcomeRows = Object.entries(summary).map(([outcome, n]) => ({outcome, n}));
```

```js
Plot.plot({
  width,
  marginLeft: 150,
  x: {label: "disease CURIEs", type: "log", grid: true},
  y: {label: null, domain: outcomeRows.sort((a, b) => b.n - a.n).map((d) => d.outcome)},
  marks: [
    Plot.barX(outcomeRows, {y: "outcome", x: "n", fill: "#4269d0"}),
    Plot.text(outcomeRows, {y: "outcome", x: "n", text: (d) => d.n.toLocaleString(), dx: 20}),
    Plot.ruleX([1]),
  ],
})
```

## HP → MONDO remaps

The terms where node normalization had conflated a phenotype with a disease, and we
recovered the MONDO identity.

```js
Inputs.table(dc.hp_to_mondo, {
  columns: ["original", "mondo", "label"],
  header: {original: "Original (HP)", mondo: "MONDO", label: "MONDO label"},
  rows: 20,
})
```

## Kept as HP

Disease objects that stay HP because their clique holds no MONDO term — genuine
phenotype-typed targets, left as-is per the MONDO-centric-but-HP-fallback rule.

```js
const hpSearch = view(Inputs.search(dc.kept_hp, {placeholder: "search HP terms…"}));
```

```js
Inputs.table(hpSearch, {
  columns: ["original", "label"],
  header: {original: "HP term", label: "label"},
  rows: 18,
})
```
