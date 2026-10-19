---
title: What to load
toc: true
---

# Which MEDIC indications are ready for monarch-kg?

<div class="note">
  <b>In-progress work.</b> This page scores the latest local MeDIC build (2026-10-13, see
  <a href="./methods">methods</a>) against the label audit and against the other sources, to
  say which of its indication edges are ready to load and which should wait for an upstream
  fix. It is advice for one consumer (monarch-kg), not a verdict on the source.
</div>

```js
const T0 = await FileAttachment("data/tiers.json").json();
```

**Short version:** the one signal that separates clean from wrong is whether the
independently fetched label text supports the edge. ${T0.tiers["T1 label-confirmed"].pairs.toLocaleString()} pairs
(${T0.tiers["T1 label-confirmed"].share}% of MEDIC) pass that check with high confidence and are
${T0.tiers["T1 label-confirmed"].fresh_fp[0]}% wrong in the audit; everything else is 35–70% wrong or unmeasurable.
Cross-source agreement and MEDIC's own reliability tier do not substitute for it. For a
disease-centric graph the cut is sharper still: restrict to MONDO diseases and the
label-confirmed set is ${T0.rules["T1 restricted to MONDO diseases"].pairs.toLocaleString()} pairs,
${T0.t1_rare.pairs.toLocaleString()} of them on ${T0.t1_rare.diseases} rare diseases.

```js
const T = await FileAttachment("data/tiers.json").json();
const fmt = (n) => n.toLocaleString();
const ci = ([p, lo, hi]) => `${p}% (CI ${lo}–${hi})`;
const R = T.rules;
const tierOrder = ["T1 label-confirmed", "T2 corroborated, label check inconclusive", "T3 unscreened (no FDA/EMA text held)", "T4 unconfirmed single-source", "T5 flagged/suspect"];
const TIER_WHY = {
  "T1 label-confirmed": "the automated label check (Jev, confidence ≥ 0.9) reads the independently fetched FDA/EMA text as supporting the indication; no suspect feature",
  "T2 corroborated, label check inconclusive": "label check ran but was not confident either way; the pair is backed by DAKP/dismech agreement (exact or same-moiety) or by ≥2 regulators; no suspect feature",
  "T3 unscreened (no FDA/EMA text held)": "we hold no FDA/EMA label text for the drug (mostly PMDA- or CDSCO-only approvals), so the label check could not run and the audit has no measurement here",
  "T4 unconfirmed single-source": "label check inconclusive, one regulator, no agreement with any source; no suspect feature",
  "T5 flagged/suspect": "the label check confidently flags an error, or the pair is supported only by combination-product labels, or by a homeopathic label, or the drug is a counter-ion / active metabolite, or MeDIC itself detected negation, or rates it LOW/EXCLUDED",
};
const tiers = tierOrder.filter((t) => T.tiers[t]).map((t) => ({tier: t, why: TIER_WHY[t], ...T.tiers[t]}));
```

<style>
table { width: 100%; }
.sub { font-size: 12px; color: var(--theme-foreground-muted, #6b7280); }
</style>

## How the rules were scored

Every MEDIC indication pair in the latest build gets a set of features: which regulators
assert it, MEDIC's own reliability tier and grounding flags, whether its only FDA support
is a combination-product label, whether the drug is a counter-ion or active metabolite,
whether the pair also appears in DAKP or dismech (exactly, or via the same active moiety),
and the automated label check (Jev, confidence ≥ 0.9). Each candidate rule is then scored
two ways against the [label audit](./error-taxonomy): on the **fresh random sample** judged
on this build (${fmt(T.labeled_fresh)} pairs — the unbiased number), and on the **pooled**
labeled set (${fmt(T.labeled_pooled)} pairs: the fresh sample plus every pair judged on an
earlier MEDIC release or build that this build still asserts — more pairs, but it
over-represents kept pairs, which are cleaner, so it tightens the comparison between rules
rather than the absolute level).

## Load tiers

```js
Inputs.table(tiers, {
  columns: ["tier", "pairs", "share", "fresh_fp", "fresh_n", "pooled_fp", "pooled_n", "why"],
  header: {tier: "Tier", pairs: "MEDIC pairs", share: "% of MEDIC", fresh_fp: "error rate (fresh sample)", fresh_n: "n",
           pooled_fp: "error rate (pooled)", pooled_n: "n", why: "Definition"},
  format: {share: (s) => `${s}%`, fresh_fp: ci, pooled_fp: ci},
  width: {why: 420}, select: false, sort: null, rows: 6,
})
```

```js
Plot.plot({
  width, height: 60 + 36 * tiers.length, marginLeft: 190, marginRight: 60,
  x: {label: "false-positive rate (%) with 95% CI — fresh sample", domain: [0, 80], grid: true},
  y: {label: null, domain: tiers.map((d) => d.tier)},
  marks: [
    Plot.ruleY(tiers, {y: "tier", x1: (d) => d.fresh_fp[1], x2: (d) => d.fresh_fp[2], stroke: "#9498a0", strokeWidth: 2}),
    Plot.dot(tiers, {y: "tier", x: (d) => d.fresh_fp[0], r: (d) => 4 + Math.sqrt(d.pairs) / 10, fill: "var(--theme-foreground-focus, #2a78d6)", tip: true,
      title: (d) => `${d.tier}\n${fmt(d.pairs)} pairs (${d.share}% of MEDIC)\n${ci(d.fresh_fp)}, n = ${d.fresh_n} fresh; ${ci(d.pooled_fp)}, n = ${d.pooled_n} pooled`}),
    Plot.text(tiers, {y: "tier", x: (d) => d.fresh_fp[2], text: (d) => `${d.fresh_fp[0]}% · ${fmt(d.pairs)} pairs`, dx: 8, textAnchor: "start", fontSize: 11}),
  ],
})
```

## The disease axis

monarch-kg is disease-centric, and rare disease is where it matters. Not every MEDIC
"disease" is one: HP-phenotype targets are mostly OTC symptom-relief claims (fatigue, nasal
congestion, pruritus, cough, pain, fever), and UMLS targets include unnamed stubs. The two
questions are therefore *which disease class* an edge is on and *how clean MEDIC is there*.

```js
const axisOrder = ["MONDO rare", "MONDO other", "HP phenotype", "UMLS/other"];
const axisRows = axisOrder.map((a) => ({axis: a, ...T.by_axis[a]}));
Inputs.table(axisRows, {
  columns: ["axis", "pairs", "diseases", "fresh_fp", "fresh_n", "pooled_fp", "pooled_n"],
  header: {axis: "Disease class", pairs: "MEDIC pairs", diseases: "distinct diseases", fresh_fp: "error rate (fresh)", fresh_n: "n", pooled_fp: "error rate (pooled)", pooled_n: "n"},
  format: {fresh_fp: ci, pooled_fp: ci}, select: false, sort: null, rows: 5,
})
```

Rare-disease edges are MEDIC's **cleanest** part (${ci(T.by_axis["MONDO rare"].fresh_fp)} fresh;
${ci(T.by_axis["MONDO rare"].pooled_fp)} pooled) — rare-disease labels tend to name one condition
and no symptom list — and HP-phenotype targets its worst (${ci(T.by_axis["HP phenotype"].fresh_fp)}).
MEDIC covers ${fmt(T.rare_diseases_covered)} rare diseases; for scale, dismech (disease-centric by
construction) has drug edges on ~1,360 and DAKP-approved on ~715.

```js
const cell = (t, a) => T.tier_by_axis[t]?.[a];
const matrix = tierOrder.filter((t) => T.tier_by_axis[t]).map((t) => ({tier: t, ...Object.fromEntries(axisOrder.map((a) => [a, cell(t, a)]))}));
Inputs.table(matrix, {
  columns: ["tier", ...axisOrder],
  header: {tier: "Tier \\ disease class", ...Object.fromEntries(axisOrder.map((a) => [a, a]))},
  format: Object.fromEntries(axisOrder.map((a) => [a, (c) => c ? html`<b>${fmt(c.pairs)}</b> <span class="sub">${c.pooled_n ? `${c.pooled_fp[0]}% wrong, n=${c.pooled_n}` : "unmeasured"}</span>` : ""])),
  select: false, sort: null, rows: 6,
})
```

*Pairs per cell, with the pooled-labeled error rate where there are labels.* The rare-disease
blind spot is Japan: ${fmt(R["rare disease, unscreened (no FDA/EMA text; mostly PMDA)"].pairs)} rare-disease
pairs have no FDA/EMA text to check (most are PMDA-only), ${fmt(R["rare disease, unscreened but corroborated"].pairs)}
of them with cross-source agreement.

## Recommendation

```js
const t1 = T.tiers["T1 label-confirmed"], t2 = T.tiers["T2 corroborated, label check inconclusive"], t3 = T.tiers["T3 unscreened (no FDA/EMA text held)"], t5 = T.tiers["T5 flagged/suspect"];
const t3c = R["T3 split: unscreened but corroborated (agreement or >=2 regulators)"];
```

- **Load T1 restricted to MONDO diseases** — ${fmt(R["T1 restricted to MONDO diseases"].pairs)} pairs
  (${fmt(T.t1_rare.pairs)} on ${T.t1_rare.diseases} rare diseases, ${T.t1_rare.drugs} drugs), at ${ci(t1.fresh_fp)} measured
  error for T1 overall and ${ci(R["T1 restricted to MONDO rare diseases"].pooled_fp)} on the rare slice (pooled). This is the only
  MEDIC subset whose precision is at the level of a curated resource, and it is defined by
  evidence a consumer can re-check (the label text), not by MEDIC's own tier.
- **Leave HP-phenotype and UMLS targets out of the disease graph** (${fmt(T.by_axis["HP phenotype"].pairs + T.by_axis["UMLS/other"].pairs)} pairs). The HP
  ones are symptom-relief claims (cough medicine → cough), not disease treatment; if wanted at
  all they belong on a phenotype predicate, and the T1 filter still applies. The UMLS ones need
  a MONDO mapping first (issue 06).
- **Hold T2 and T4** (${fmt(t2.pairs + T.tiers["T4 unconfirmed single-source"].pairs)} pairs) until upstream fixes land: once the label check was
  unsure, cross-source agreement adds little (T2 is ${ci(t2.fresh_fp)}) — MEDIC and DAKP read
  the same labels, so they agree on the same population-as-target and symptom-swap errors.
- **T3 is a blind spot, not a verdict** — ${fmt(t3.pairs)} pairs, mostly PMDA/CDSCO-only, with no
  independent text to judge against; ${fmt(R["rare disease, unscreened (no FDA/EMA text; mostly PMDA)"].pairs)} of them are rare-disease
  edges, which is where Japanese approvals add coverage the FDA/EMA sources don't have. The
  ${fmt(R["rare disease, unscreened but corroborated"].pairs)} with cross-source agreement are the defensible addition (unmeasured, so
  label them as such); checking the rest needs PMDA label text, which the audit doesn't hold.
- **Don't load T5** (${fmt(t5.pairs)} pairs, ${ci(t5.fresh_fp)}): every feature in it is a known MeDIC mechanism
  with a fix path (see the issues list in `medic-feedback/issues/`).
- **Don't use MEDIC's reliability tier as the gate**: HIGH is ${ci(R["reliability HIGH"].fresh_fp)}, the
  same as the whole. A cheap label-entailment screen like the one here (≈ $0.15 for 1,400
  edges) is what separates the tiers, and belongs in the MeDIC pipeline itself.

*Dot size ∝ √pairs. The per-pair tier assignment is in `src/data/medic_tiers.parquet` (canonical
ids) and `experiments/out/v2/medic_load_tiers.tsv` (MeDIC's own subject/object ids), each row
carrying the reasons.*

## Every rule we scored

Single features and their complements, so the tiers above can be read against their parts.
Sorted by the fresh-sample error rate; pooled rate alongside.

```js
const rules = Object.entries(R).map(([rule, s]) => ({rule, ...s})).sort((a, b) => a.fresh_fp[0] - b.fresh_fp[0]);
Inputs.table(rules, {
  columns: ["rule", "pairs", "share", "fresh_fp", "fresh_n", "pooled_fp", "pooled_n"],
  header: {rule: "Rule", pairs: "MEDIC pairs", share: "% of MEDIC", fresh_fp: "error rate (fresh)", fresh_n: "n", pooled_fp: "error rate (pooled)", pooled_n: "n"},
  format: {share: (s) => `${s}%`, fresh_fp: ci, pooled_fp: ci},
  width: {rule: 420}, select: false, sort: null, rows: rules.length,
})
```

## Caveats

- **Precision only.** A tier says how often a kept edge is wrong, not what MEDIC misses.
  ${fmt(T.medic_pairs)} MEDIC pairs is a smaller indication set than medic-ingest shipped; see
  [version changes](./changes).
- **Agreement is not independence.** MEDIC and DAKP both read FDA labels, so an error they
  share survives the T1 rule; dismech (literature) is the more independent witness but
  covers only ~3,000 diseases.
- **Small cells.** Rules that keep few pairs have wide intervals; read the CI, not the point.
- **Carry-over consistency.** ${T.consistency.pairs_judged_twice} pairs were judged in two
  rounds (same evidence); ${T.consistency.same_verdict} got the same verdict both times.
