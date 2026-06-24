---
title: Error taxonomy
toc: false
---

# Error taxonomy — label-grounded hits & misses

Cross-source *agreement* is a useful confidence signal, but it encodes **shared** errors
(both sources can be wrong the same way) and can't see what *every* source missed. For the
FDA-scoped subset, the stronger arbiter is the actual label text — the DailyMed
**Indications and Usage** section (now shown live on each [drug page](./drugs) via openFDA).
Every error below is a mismatch between an **asserted edge** and the disease's **role in
that text**.

Two directions: **false positives** (a source asserts a drug→disease that isn't a real
treatment target) and **misses** (a target indication on the label that a source failed to
extract). Examples below are real and link to the detail pages — open one and expand the
**FDA label** panel to check it against the source.

The **examples** below were surfaced by hand-in-the-loop exploration with **Claude Code
(Opus 4.8)** and are illustrative, not counted — a characterization of the error *kinds*.
Separately, the **measured false-positive rate** at the bottom of the page comes from a
seeded random sample independently adjudicated against the FDA label by two reviewers; that
section has the actual numbers.

```js
const byDrug = await FileAttachment("data/by_drug.json").json();
const byDisease = await FileAttachment("data/by_disease.json").json();
const dmap = new Map(byDrug.map((d) => [d.drug_label.toLowerCase(), d.drug]));
const xmap = new Map(byDisease.map((d) => [d.disease_label.toLowerCase(), d.disease]));
const dlink = (l) => { const id = dmap.get(l.toLowerCase()); return id ? html`<a href="drug?id=${encodeURIComponent(id)}">${l}</a>` : html`<span>${l}</span>`; };
const xlink = (l) => { const id = xmap.get(l.toLowerCase()); return id ? html`<a href="disease?id=${encodeURIComponent(id)}">${l}</a>` : html`<span>${l}</span>`; };
const ex = (rows) => html`<ul class="ex">${rows.map(([src, drug, dis, note]) =>
  html`<li><span class="src ${src === "DAKP" ? "dakp" : "medic"}">${src}</span> ${dlink(drug)} → ${xlink(dis)} <span class="muted">— ${note}</span></li>`)}</ul>`;
const section = (groups) => html`<div>${groups.map(([title, def, rows]) =>
  html`<h3>${title}</h3><div class="muted def">${def}</div>${ex(rows)}`)}</div>`;
```

<style>
.src { display: inline-block; min-width: 3.4em; text-align: center; padding: 0 6px; margin-right: 4px;
  border-radius: 5px; font-size: 10px; font-weight: 700; letter-spacing: 0.03em; vertical-align: 1px; }
.src.dakp { background: color-mix(in srgb, #e15759 22%, transparent); }
.src.medic { background: color-mix(in srgb, #4269d0 20%, transparent); }
.ex { margin: 0.2rem 0 0.9rem; line-height: 1.7; }
.ex .muted { color: var(--theme-foreground-muted, #6b7280); }
.def { font-size: 13px; margin: 0 0 0.1rem; }
h3 { margin-bottom: 0.1rem; }
table { width: 100%; }
ul, ol { max-width: none; }
</style>

## False positives — asserted, but not a real target

| # | Type | Definition | Cue / detector |
|---|------|-----------|----------------|
| FP1 | Setting/context-as-target | disease is the *cause/context* of the treated condition | "associated with / due to / induced by / in patients with" |
| FP2 | Symptom↔disease swap | treats a symptom but mapped to the disease (or vice versa) | symptom vs disease term in the head |
| FP3 | Cross-section bleed | disease taken from Contraindications / Warnings, not Indications | absent from `indications_and_usage` |
| FP4 | Over-broad / wrong granularity | mapped to a parent broader than the actual target | label indicates a narrower term |
| FP5 | Negation / contraindication flip | disease in a "not indicated / contraindicated" context, asserted positive | negation near the mention |
| FP7 | Not-in-text / spurious mapping | disease absent from the label — usually a term-mapping artifact, not an invented claim | term + synonyms absent |
| FP8 | Normalization artifact | right concept, wrong / obsolete CURIE | HP/MONDO conflation, obsolete term |

```js
section([
  ["FP1 — Setting / context-as-target",
   'The disease is the patient population or cause, not what the drug treats — the canonical ondansetron→cancer. Dominant in DAKP-approved supportive-care drugs.',
   [["DAKP", "Ondansetron", "cancer", "nausea/vomiting associated with cancer chemotherapy"],
    ["DAKP", "Aprepitant", "cancer", "antiemetic; cancer is the chemo setting"],
    ["DAKP", "Fentanyl", "cancer", "opioid; cancer pain context"],
    ["MEDIC", "Allopurinol", "leukemia", "manages hyperuricemia in leukemia patients"],
    ["MEDIC", "Dopamine", "myocardial infarction", "treats shock *due to* MI"]]],
  ["FP3 — Cross-section bleed",
   'Disease pulled from a warning/contraindication section rather than Indications.',
   [["DAKP", "Finasteride", "cancer", "prostate cancer only in a PSA/risk warning"],
    ["DAKP", "Acetaminophen", "liver disorder", "boxed hepatotoxicity warning, not an indication"]]],
  ["FP4 — Over-broad / wrong granularity",
   'Mapped to a parent broader than the real, narrower target.',
   [["DAKP", "Pimavanserin", "Parkinson disease", "approval is PD *psychosis*, not PD"],
    ["DAKP", "Rifaximin", "liver disorder", "only overt hepatic-encephalopathy recurrence"],
    ["MEDIC", "Atorvastatin", "stroke disorder", "*reduces risk of* stroke, doesn't treat it"]]],
  ["FP5 — Negation / contraindication flip",
   'Disease appears in a "not indicated / not effective / contraindicated" context.',
   [["MEDIC", "Dapagliflozin", "polycystic kidney disease", '"not recommended… not expected to be effective"'],
    ["DAKP", "Levothyroxine", "hyperthyroidism", "thyrotoxicosis is a contraindication (drug treats hypothyroidism)"]]],
  ["FP7 — Not-in-text / spurious mapping",
   'Disease absent from the label — usually a term-mapping artifact, not a fabricated claim.',
   [["DAKP", "Amoxicillin", "skin neoplasm", "no neoplasm/tumor in label; likely mis-mapped 'skin structure infections'"]]],
  ["FP8 — Normalization artifact",
   'Right concept, wrong or obsolete CURIE from normalization.',
   [["MEDIC", "Estradiol", "obsolete atrophic vulva", "concept is correct (vulvar/vaginal atrophy), CURIE is obsolete"],
    ["MEDIC", "Cyanocobalamin", "diphyllobothriasis", "a listed *cause* of B12 deficiency, not the target"]]],
])
```

## Misses — a real target the source didn't extract

| # | Type | Definition | Detector |
|---|------|-----------|----------|
| M1 | Secondary-indication drop | got the primary, missed another on the label | label target not asserted; siblings caught |
| M2 | List/coordination drop | "indicated for A, B, and C" → only some | coordinated list in the indication sentence |
| M3 | Synonym / normalization miss | label target present, no asserted CURIE | label target with no source CURIE |
| M4 | Granularity miss | specific subtype stated; mapped to parent or dropped | label subtype not asserted |
| M6 | Whole-drug miss | drug absent from the source entirely | drug has a label but 0 source edges |

```js
section([
  ["M2 — List / coordination drop",
   'The label lists several indications; only some were extracted.',
   [["MEDIC", "Sertraline", "obsessive-compulsive disorder", "got 5 of Zoloft's 6 listed indications"],
    ["DAKP", "Lenvatinib", "endometrial carcinoma", "4th of 4 indication blocks dropped"],
    ["DAKP", "Venetoclax", "acute myeloid leukemia", "has the CLL block, missed the AML block"]]],
  ["M4 — Granularity miss",
   'A subtype/parent the source has only as `related`, or not at all.',
   [["MEDIC", "Alectinib", "lung cancer", "has NSCLC exact, parent only related"],
    ["MEDIC", "Alogliptin", "diabetes mellitus", "has T2DM exact, parent only related"],
    ["DAKP", "Amphetamine", "attention deficit hyperactivity disorder", "approved on the inattentive-subtype node, not the plain-label parent"]]],
  ["M6 — Whole-drug miss",
   'A drug with a clear FDA label that the source has no edges for. MEDIC: newer specialty/orphan drugs. DAKP: present but mis-flagged off-label.',
   [["MEDIC", "Pimavanserin", "Parkinson disease", "Nuplazid (2016) — MEDIC has 0 edges; DAKP caught it"],
    ["MEDIC", "Tasimelteon", "sleep-wake disorder", "Hetlioz — absent from MEDIC"],
    ["MEDIC", "Abrocitinib", "atopic eczema", "Cibinqo — absent from MEDIC"],
    ["DAKP", "Memantine", "Alzheimer disease", "78 off-label rows, 0 approved despite a clear label"],
    ["DAKP", "Lecanemab", "Alzheimer disease", "edge exists but stamped off_label_use"]]],
])
```

## Measured false-positive rate

A **seeded random sample** of asserted edges, each independently checked against the FDA
label (UNII-verified match; indications unioned across *all* of a substance's product labels)
and adjudicated by **two independent Opus 4.8 reviewers**. Full method + artifacts:
`experiments/README.md`.

| source | n judged | precision (genuine target) | false-positive rate |
|---|---|---|---|
| DAKP-approved | 94 | 67% (CI 57–76) | **33%** (CI 24–43) |
| MEDIC, FDA-scoped | 64 | 80% (CI 68–88) | **20%** (CI 12–32) |

*Two-reviewer consensus. First-pass (single reviewer) FP was 42% / 22%; the gap is almost
entirely the contested **over-broad/parent** call (e.g. etoposide→"cancer"), where reviewers
reasonably differ — so read 33% / 20% as the conservative floor.*

What the measurement **corrected** vs the casual exploration:
- **Setting-as-target (FP1) is *not* the dominant DAKP error** — that was an artifact of
  *hunting* for cancer / supportive-care cases. In a random sample it's ~3%. DAKP's real
  driver is **not-in-any-label spurious mappings (~19%)** — many acronym/synonym collisions
  (MCL = mast-cell vs mantle-cell leukemia; NSCLC↔SCLC swaps) — plus cross-section bleed (~6%).
- **MEDIC's FP rate is genuinely lower** (~20% vs ~33%), now *measured* rather than asserted —
  but it isn't error-free: its main type is **setting-as-target (~8%)** (risk-reduction edges
  like statins→atherosclerosis), then not-in-label (~9%).
- **Scope & limits:** MEDIC here is the **8,725 / 10,878** FDA-tagged edges; the 2,153
  EU/Japan-only approvals are excluded (judging them against the FDA label would be unfair).
  These are **precision** rates for asserted edges — *not* recall (misses). MEDIC's n is
  smaller because fewer of its drugs resolve to a UNII-matched openFDA label.

### Every edge we checked

The full set of adjudicated edges — first-pass verdict, second-reviewer consensus (struck
through where the skeptic overturned the flag), and the deciding label phrase. Drug/disease
link to their detail pages (expand the **FDA label** panel to check any call yourself).

```js
const auditAll = (await FileAttachment("data/fp_audit.json").json()).edges;
const isFP = (v) => v.startsWith("FP");
const srcSel = view(Inputs.radio(["all", "dakp-approved", "medic"], {label: "Source", value: "all",
  format: (v) => ({all: "All", "dakp-approved": "DAKP", medic: "MEDIC"}[v])}));
const fpOnly = view(Inputs.toggle({label: "False positives only"}));
const search = view(Inputs.text({label: "Search", placeholder: "drug, disease, or note…"}));
```

```js
const rows = auditAll.filter((r) =>
  (srcSel === "all" || r.source === srcSel) &&
  (!fpOnly || isFP(r.verdict)) &&
  (!search || `${r.drug_label} ${r.disease_label} ${r.note}`.toLowerCase().includes(search.toLowerCase())));
const vchip = (v) => html`<span style="font-weight:600;color:${isFP(v) ? "#b4423a" : "#3a7d34"}">${v}</span>`;
display(html`<div style="max-height:560px;overflow:auto;border:1px solid var(--theme-foreground-faintest);border-radius:6px">
<table style="margin:0">
<thead><tr><th>source</th><th>drug</th><th>disease</th><th>consensus</th><th>first pass</th><th>deciding label phrase</th></tr></thead>
<tbody>${rows.map((r) => html`<tr>
<td><span class="src ${r.source === "dakp-approved" ? "dakp" : "medic"}">${r.source === "dakp-approved" ? "DAKP" : "MEDIC"}</span></td>
<td><a href="drug?id=${encodeURIComponent(r.drug)}">${r.drug_label}</a></td>
<td><a href="disease?id=${encodeURIComponent(r.disease)}">${r.disease_label}</a></td>
<td>${vchip(r.verdict)}</td>
<td>${r.overturned ? html`<span class="muted" style="text-decoration:line-through">${r.verdict_firstpass}</span>` : html`<span class="muted">${r.verdict_firstpass === r.verdict ? "·" : r.verdict_firstpass}</span>`}</td>
<td class="muted" style="font-size:12px">${r.note}</td>
</tr>`)}</tbody></table></div>`);
display(html`<div class="muted" style="font-size:12px;margin-top:4px">${rows.length} of ${auditAll.length} adjudicated edges shown · 82 more were sampled but excluded (no independently UNII-matched FDA label)</div>`);
```

## Misses & other observations (not yet counted)

- **Misses we verified** (illustrative, not a survey): DAKP frequently *had* the pair but
  stamped it off-label or approved only a sibling node (a status/normalization issue more than
  a true omission); the MEDIC misses we found were mostly **whole-drug gaps** for newer
  specialty/orphan drugs. A counted recall rate would need a different sampling frame.
- **Cross-source agreement is a lead, not proof.** Because the sources share methods (LLM
  extraction over the same FDA/DailyMed text), they can share the *same* error — so two
  sources agreeing can both be wrong, and the lone source that omitted it may be the one that
  got it right. The arbiter is the **label text**, not the vote.
