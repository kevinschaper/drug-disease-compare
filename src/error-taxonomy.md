---
title: Error taxonomy
toc: true
---

# Error taxonomy — measured against the label

<div class="note">
  <b>In-progress work.</b> The MEDIC (MeDIC redesign, a local, unreleased build) and DAKP
  (1.16.0) updates compared here are both under active development. Treat every number on
  this page as a snapshot of work in progress, to inform the next iteration of each source —
  not as a final characterization of either resource.
</div>

Cross-source *agreement* is a useful confidence signal, but it encodes **shared** errors
(the sources mine the same regulator text with similar methods) and can't see what *every*
source missed. The stronger arbiter is the regulator text itself. This page measures how
often an asserted indication edge is **not** a genuine treatment target according to the
**FDA label** or the **EMA EPAR** indication, on the **latest releases** this site compares.

```js
const audit = await FileAttachment("data/fp_audit.json").json();
const S = audit.summary, A = S.agreement, P = S.population;
const E = audit.edges;
const fmt = (n) => n.toLocaleString();
const ci = ([p, lo, hi]) => `${p}% (CI ${lo}–${hi})`;
const SRC = {medic: "MEDIC", "dakp-approved": "DAKP-approved"};
const isFP = (v) => v.startsWith("FP");
const LABEL = {
  FP1_setting: "setting-as-target", FP2_symptom_swap: "symptom swap",
  FP3_cross_section: "cross-section bleed", FP4_overbroad: "over-broad / granularity",
  FP5_negation: "negation", FP6_coingredient: "co-ingredient's indication",
  FP7_notintext: "not in label / spurious mapping"};
```

<style>
.src { display: inline-block; min-width: 3.4em; text-align: center; padding: 0 6px; margin-right: 4px;
  border-radius: 5px; font-size: 10px; font-weight: 700; letter-spacing: 0.03em; vertical-align: 1px; }
.src.dakp { background: color-mix(in srgb, #e15759 22%, transparent); }
.src.medic { background: color-mix(in srgb, #4269d0 20%, transparent); }
.ex { margin: 0.2rem 0 0.9rem; line-height: 1.6; }
.ex li { margin-bottom: 0.25rem; }
.ex .q { color: var(--theme-foreground-muted, #6b7280); font-size: 13px; }
.def { font-size: 13px; margin: 0 0 0.1rem; color: var(--theme-foreground-muted, #6b7280); }
.verdict-fp { font-weight: 600; color: #b4423a; }
.verdict-ok { font-weight: 600; color: #3a7d34; }
@media (prefers-color-scheme: dark) { .verdict-fp { color: #ef8a80; } .verdict-ok { color: #7cc474; } }
table { width: 100%; }
ul, ol { max-width: none; }
</style>

## Measured false-positive rate

A **seeded random sample** of 300 edges per source (MEDIC indications; DAKP
`approved_for_condition`) **from each release** — latest and previous, 1,200 edges in all —
each judged against regulator text **we fetched ourselves** —
never a source's own snippet:

- **FDA**: the openFDA bulk label export, matched by the drug's own UNII *or* any label of
  the same FDA/GSRS active moiety (salt/hydrate forms), with indications unioned across every
  product's label. Homeopathic labels excluded.
- **EMA**: the EPAR therapeutic indication of centrally authorised products, matched by INN.

Each edge was judged blind (no source shown) by **two independent Claude reviewers** (one
instructed to be adversarial), disagreements settled by a third, plus a dedicated
**co-ingredient check** of every edge whose evidence included combination products. A "not in
the label" call only counts where we hold text for **every** regulator the edge cites —
otherwise it might live in text we don't have (e.g. a PMDA-only approval).

```js
const rows = ["medic", "dakp-approved"].flatMap((s) => [
  {source: SRC[s], release: "latest", n: S.sources[s].judged, p: S.sources[s].fp_rate[0], lo: S.sources[s].fp_rate[1], hi: S.sources[s].fp_rate[2]},
  ...(S.previous_release[s] ? [{source: SRC[s], release: "previous", n: S.previous_release[s].n, p: S.previous_release[s].fp_rate[0], lo: S.previous_release[s].fp_rate[1], hi: S.previous_release[s].fp_rate[2]}] : []),
]);
```

<div class="grid grid-cols-2">
  <div class="card">
    <h2>MEDIC — false-positive rate</h2>
    <span class="big">${S.sources.medic.fp_rate[0]}%</span>
    CI ${S.sources.medic.fp_rate[1]}–${S.sources.medic.fp_rate[2]} · n = ${S.sources.medic.judged}
    · previous release ${S.previous_release.medic.fp_rate[0]}% (n = ${S.previous_release.medic.judged}, same protocol)
  </div>
  <div class="card">
    <h2>DAKP-approved — false-positive rate</h2>
    <span class="big">${S.sources["dakp-approved"].fp_rate[0]}%</span>
    CI ${S.sources["dakp-approved"].fp_rate[1]}–${S.sources["dakp-approved"].fp_rate[2]} · n = ${S.sources["dakp-approved"].judged}
    · previous release ${S.previous_release["dakp-approved"].fp_rate[0]}% (n = ${S.previous_release["dakp-approved"].judged}, same protocol)
  </div>
</div>

```js
Plot.plot({
  width, height: 170, marginLeft: 150, marginRight: 40,
  x: {label: "false-positive rate (%) with 95% CI", domain: [0, 60], grid: true},
  y: {label: null, domain: ["MEDIC · latest", "MEDIC · previous", "DAKP-approved · latest", "DAKP-approved · previous"]},
  color: {domain: ["latest", "previous"], range: ["var(--theme-foreground-focus, #2a78d6)", "#9498a0"], legend: true},
  marks: [
    Plot.ruleY(rows, {y: (d) => `${d.source} · ${d.release}`, x1: "lo", x2: "hi", stroke: "release", strokeWidth: 2}),
    Plot.dot(rows, {y: (d) => `${d.source} · ${d.release}`, x: "p", fill: "release", r: 5, tip: true,
      title: (d) => `${d.source}, ${d.release} release\n${d.p}% (CI ${d.lo}–${d.hi}), n = ${d.n}`}),
    Plot.text(rows, {y: (d) => `${d.source} · ${d.release}`, x: "hi", text: (d) => `${d.p}%`, dx: 18, fontSize: 11}),
  ],
})
```

Judged with the identical protocol — and blind to which release an edge came from — the
latest rates are statistically indistinguishable from the previous releases'. What changed
is the **kind** of error; see *Did MEDIC improve?* and *Did DAKP improve?* on
[version changes](./changes). Latest releases, by error type:

```js
const typeRows = ["medic", "dakp-approved"].flatMap((s) =>
  Object.entries(S.sources[s].by_type).map(([t, [n, pct]]) => ({source: SRC[s], type: LABEL[t] ?? t, n, pct})));
display(Plot.plot({
  width, height: 260, marginLeft: 210, marginRight: 50,
  x: {label: "share of judged edges (%)", grid: true},
  y: {label: null, domain: Object.values(LABEL)},
  fx: {label: null, domain: ["MEDIC", "DAKP-approved"]},
  marks: [
    Plot.barX(typeRows, {x: "pct", y: "type", fx: "source", fill: "#b4423a", fillOpacity: 0.75, rx: 2, tip: true,
      title: (d) => `${d.source} · ${d.type}\n${d.n} edges (${d.pct}%)`}),
    Plot.text(typeRows, {x: "pct", y: "type", fx: "source", text: (d) => `${d.n}`, dx: 10, fontSize: 10}),
    Plot.ruleX([0]),
  ],
}));
```

What stands out:

- **MEDIC's errors are mostly about *how* a label is read, not invented claims.** Its largest
  type is **setting-as-target** (the disease is the population, e.g. "reduce the risk of MI
  *in patients with* CHD"), then **co-ingredient attribution** — every one of the
  ${S.sources.medic.by_type.FP6_coingredient?.[0] ?? 0} co-ingredient errors in the sample is MEDIC's: it credits each
  ingredient of a combination product with the whole product's indications
  (atorvastatin → hypertension via amlodipine/atorvastatin; caffeine → back pain via
  analgesic combinations). Its rate of outright "not in any label" mappings is low
  (${S.sources.medic.by_type.FP7_notintext?.[1] ?? 0}%).
- **DAKP's dominant error is still "not in any label"** (${S.sources["dakp-approved"].by_type.FP7_notintext?.[1] ?? 0}%): term-mapping artifacts
  such as acronym/synonym collisions, then **over-broad** parents (label "large B-cell
  lymphoma" → edge "B-cell non-Hodgkin lymphoma").
- **Edges both regulators back look cleaner.** Judged against FDA *and* EMA text, the
  false-positive rate was ${S.sources.medic.by_regulator["FDA + EMA"]?.fp_rate[0]}% for MEDIC (n = ${S.sources.medic.by_regulator["FDA + EMA"]?.n}) and
  ${S.sources["dakp-approved"].by_regulator["FDA + EMA"]?.fp_rate[0]}% for DAKP (n = ${S.sources["dakp-approved"].by_regulator["FDA + EMA"]?.n}) — small n, but consistent with errors
  concentrating in single-regulator extractions.

```js
Inputs.table(["medic", "dakp-approved"].flatMap((s) => [
  ...Object.entries(S.sources[s].by_regulator).map(([k, v]) => ({source: SRC[s], slice: `judged against ${k}`, n: v.n, fp: ci(v.fp_rate)})),
  ...Object.entries(S.sources[s].by_reliability ?? {}).map(([k, v]) => ({source: SRC[s], slice: `MEDIC reliability ${k}`, n: v.n, fp: ci(v.fp_rate)})),
]), {header: {source: "Source", slice: "Slice", n: "n", fp: "false-positive rate"}, select: false, sort: null})
```

**MEDIC's reliability tier** (HIGH / MEDIUM / LOW) is a data-quality score, not a claim of
evidence strength — but it does track errors: across the full population, Jev flags
${P.medic.jev_fp_share_by_reliability.HIGH}% of HIGH, ${P.medic.jev_fp_share_by_reliability.MEDIUM}% of MEDIUM and
${P.medic.jev_fp_share_by_reliability.LOW}% of LOW pairs (the sample alone is too small per tier to say much).

**Population estimate.** Correcting the full-population screen (below) by its measured error
rates gives MEDIC **${ci(P.medic.corrected_fp_rate)}** over ${fmt(P.medic.judged)} edges and DAKP-approved
**${ci(P["dakp-approved"].corrected_fp_rate)}** over ${fmt(P["dakp-approved"].judged)} — consistent with the sample.

## Can a fast decision model do this? (Jev)

[Jev](https://docs.typesafe.ai) (TypeSafe AI's System One model) answers typed multiple-choice
questions with calibrated probabilities at a tiny fraction of an LLM's cost. All
${fmt(A.n)} reference edges (both releases) and all ${fmt(P.medic.screened + P["dakp-approved"].screened)} eligible latest-release edges were sent to `jev-1.13.0` with the same evidence the
reviewers saw, asking the rubric as one 8-way choice plus three atomic yes/no questions. The
full screen cost about **$2**.

Jev was **scored against the Claude reference only** (it played no part in building it), with
an acceptance bar fixed before looking: binary (target vs error) agreement within 5 points of
the reviewers' own agreement, and κ ≥ 0.6.

<div class="grid grid-cols-4">
  <div class="card"><h2>Reviewer ↔ reviewer</h2><span class="big">${(A.claude_ab_binary * 100).toFixed(1)}%</span>
    binary agreement · κ ${A.claude_ab_kappa_binary}</div>
  <div class="card"><h2>Jev ↔ reference</h2><span class="big">${(A.jev_binary * 100).toFixed(1)}%</span>
    binary agreement · κ ${A.jev_kappa_binary}</div>
  <div class="card"><h2>Acceptance</h2><span class="big">${A.jev_accepted ? "passed" : "not met"}</span>
    ${A.acceptance.within_5pts ? "within" : "more than"} 5 pts of the ceiling · κ ${A.acceptance.kappa_ok ? "≥" : "<"} 0.6</div>
  <div class="card"><h2>Jev at confidence ≥ 0.9</h2><span class="big">${(A.jev_high_confidence["0.9"].binary_acc * 100).toFixed(1)}%</span>
    agreement on ${(A.jev_high_confidence["0.9"].coverage * 100).toFixed(0)}% of edges</div>
</div>

**Jev does not meet the bar as a stand-alone adjudicator**, but its confidence is informative:

```js
Plot.plot({
  width: Math.min(width, 640), height: 200, marginLeft: 50,
  x: {label: "Jev confidence", domain: A.jev_calibration.map((d) => d.conf_bin)},
  y: {label: "agreement with reference", domain: [0, 1], grid: true, tickFormat: "%"},
  marks: [
    Plot.barY(A.jev_calibration, {x: "conf_bin", y: "acc", fill: "var(--theme-foreground-focus, #2a78d6)", rx: 2, tip: true,
      title: (d) => `confidence ${d.conf_bin}\n${(d.acc * 100).toFixed(0)}% agreement (n = ${d.n})`}),
    Plot.text(A.jev_calibration, {x: "conf_bin", y: "acc", text: (d) => `${(d.acc * 100).toFixed(0)}% · n=${d.n}`, dy: -8, fontSize: 11}),
    Plot.ruleY([A.claude_ab_binary], {stroke: "currentColor", strokeDasharray: "4,3"}),
    Plot.ruleY([0]),
  ],
})
```

*Dashed line: reviewer ↔ reviewer agreement.* Where Jev falls short is the multi-hop calls
its documentation warns about — **symptom swaps** and **over-broad parents** (it recovers
${(A.jev_per_class.FP2_symptom_swap?.jev_binary * 100).toFixed(0)}% and ${(A.jev_per_class.FP4_overbroad?.jev_binary * 100).toFixed(0)}%), and it flags ${(100 - A.jev_per_class.TARGET.jev_binary * 100).toFixed(0)}% of genuine targets. It caught only
${(A.jev_per_class.FP6_coingredient?.jev_binary * 100).toFixed(0)}% of co-ingredient errors, partly on our setup: its question set had no such
option and its evidence didn't separate combination labels. Asking it to decompose the call into yes/no questions did *not* help
(${(A.decomposed_noul_vs_reference * 100).toFixed(1)}% vs ${(A.jev_binary * 100).toFixed(1)}%).

**How it's used here:** only Jev verdicts at **confidence ≥ 0.9** are shown, as a
**label check** column on the drug and disease pages — measured on the gold sample, its flags
there are right ${(A.jev_high_confidence["0.9"].flag_precision * 100).toFixed(0)}% of the time and its "target" calls
${(A.jev_high_confidence["0.9"].target_precision * 100).toFixed(0)}%. Treat a flag as a lead to check, not a verdict.

## Error types, with current examples

Examples are drawn from the adjudicated sample (latest releases), each with the deciding
label phrase.

| # | Type | Definition |
|---|------|-----------|
| FP1 | Setting-as-target | disease is the population / cause / background, not what the drug treats |
| FP2 | Symptom ↔ disease swap | the label treats a symptom; the edge names the disease (or vice versa) |
| FP3 | Cross-section bleed | disease appears only in contraindications / warnings |
| FP4 | Over-broad | mapped to a whole disease class broader than the indicated condition |
| FP5 | Negation | "not indicated / not established / not recommended for" |
| FP6 | Co-ingredient attribution | indication belongs to the *other* ingredient of a combination product |
| FP7 | Not in label | disease absent from the label — usually a term-mapping artifact |

```js
const byType = d3.group(E.filter((e) => e.release === "new" && isFP(e.verdict)), (e) => e.verdict);
display(html`<div>${[...Object.keys(LABEL)].filter((t) => byType.has(t)).map((t) => html`
  <h3>${t.split("_")[0]} — ${LABEL[t]} <span class="def">· ${byType.get(t).length} in the sample</span></h3>
  <ul class="ex">${byType.get(t).slice(0, 5).map((e) => html`<li>
    <span class="src ${e.source === "medic" ? "medic" : "dakp"}">${SRC[e.source] === "MEDIC" ? "MEDIC" : "DAKP"}</span>
    <a href="drug?id=${encodeURIComponent(e.drug)}">${e.drug_label}</a> →
    <a href="disease?id=${encodeURIComponent(e.disease)}">${e.disease_label}</a>
    <span class="q">— ${e.note}${e.quote ? html` <i>“${e.quote}”</i>` : ""}</span></li>`)}</ul>`)}</div>`);
```

### Every edge we checked

```js
const srcSel = view(Inputs.radio(["all", "medic", "dakp-approved"], {label: "Source", value: "all", format: (v) => v === "all" ? "All" : SRC[v]}));
const relSel = view(Inputs.radio(["new", "old", "both"], {label: "Release", value: "new", format: (v) => ({new: "Latest", old: "Previous", both: "Both"}[v])}));
const fpOnly = view(Inputs.toggle({label: "Errors only"}));
const disagree = view(Inputs.toggle({label: "Jev disagrees"}));
```

```js
const shown = E.filter((r) =>
  (srcSel === "all" || r.source === srcSel) && (relSel === "both" || r.release === relSel) && (!fpOnly || isFP(r.verdict)) &&
  (!disagree || (isFP(r.jev) !== isFP(r.verdict))));
const vchip = (v) => html`<span class="${isFP(v) ? "verdict-fp" : v === "TARGET" ? "verdict-ok" : ""}">${v}</span>`;
display(Inputs.table(shown, {
  columns: ["source", "release", "drug_label", "disease_label", "verdict", "claude", "claude_b", "jev", "jev_confidence", "judged_against", "note"],
  header: {source: "Source", release: "Release", drug_label: "Drug", disease_label: "Disease", verdict: "Reference", claude: "Reviewer A",
           claude_b: "Reviewer B", jev: "Jev", jev_confidence: "Jev conf.", judged_against: "Judged vs", note: "Deciding reason"},
  format: {
    source: (s) => SRC[s], release: (r) => (r === "new" ? "latest" : "previous"),
    drug_label: (l, i, data) => html`<a href="drug?id=${encodeURIComponent(data[i].drug)}">${l}</a>`,
    disease_label: (l, i, data) => html`<a href="disease?id=${encodeURIComponent(data[i].disease)}">${l}</a>`,
    verdict: vchip, claude: vchip, claude_b: vchip, jev: vchip,
    jev_confidence: (c) => c.toFixed(2), judged_against: (a) => a.join(" + "),
  },
  width: {drug_label: 160, disease_label: 200, note: 360},
  rows: 20, select: false,
}));
display(html`<div class="def">${shown.length} of ${E.length} adjudicated edges</div>`);
```

## Misses — a real target the source didn't extract

*Illustrative, from hand exploration of the **previous** releases; not re-measured.* A counted
recall rate needs a different sampling frame (sample label indications, then look for the
edge), which this audit doesn't do.

| # | Type | Definition |
|---|------|-----------|
| M1 | Secondary-indication drop | got the primary, missed another on the label |
| M2 | List/coordination drop | "indicated for A, B, and C" → only some |
| M3 | Synonym / normalization miss | label target present, no asserted CURIE |
| M4 | Granularity miss | specific subtype stated; mapped to parent or dropped |
| M6 | Whole-drug miss | drug absent from the source entirely |

Examples seen then: MEDIC had 5 of Zoloft's 6 listed indications (M2); DAKP had venetoclax's
CLL block but not its AML block (M2); MEDIC lacked newer specialty drugs such as
pimavanserin, tasimelteon and abrocitinib entirely (M6); DAKP stamped memantine and
lecanemab → Alzheimer disease as off-label despite clear labels.

## Method notes & caveats

- **Precision only.** These are false-positive rates of *asserted* edges, not recall.
- **Eligibility.** ${fmt(P.medic.screened)} of 7,237 MEDIC and ${fmt(P["dakp-approved"].screened)} of 14,287 DAKP-approved pairs had
  independently fetchable FDA/EMA text. MEDIC pairs backed only by PMDA or CDSCO (Japan,
  India) can't be judged this way and are excluded.
- **Lenient on generic indications.** A narrower edge counts as a target (label "pain" →
  edge "neck pain"); reviewers flagged a handful of site-specific pain edges that pass only
  on this rule.
- **Two review rounds, one protocol.** The first 150 latest-release edges per source were
  reviewed first; the remaining 150 plus all previous-release edges were then shuffled
  together, so reviewers couldn't tell source or release. Round-1 reviewers applied the
  co-ingredient rule only via the follow-up check; round-2 reviewers saw it in the rubric —
  the same co-ingredient check ran on both rounds.
- **Previous releases** were sampled from pairs built from their own source files with the
  same reconciler, and judged against today's label text (labels drift slowly; a few
  indications added since could count against an older edge).
- **Reviewers are one model family.** Both reviewers and the tie-breaker are Claude, so their
  agreement is an upper bound on independent agreement; correlated blind spots are possible.
- **Evidence breadth matters.** A first round with narrower label matching (exact-UNII only,
  no combination labels, truncated text) produced visibly more "not in label" calls; it is
  archived and excluded. Homeopathic labels are filtered by marker text, and a few
  unmarked multi-ingredient homeopathic labels still slipped through.
- Full method, rubric and artifacts: `experiments/README.md`, `experiments/audit_rubric.md`.
