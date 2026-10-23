# Indication audit

Two rounds, each measuring how often an asserted drug→disease *indication* edge is **not** a
genuine treatment target according to regulator text.

- **v2 (current; rounds 1–2 on 2026-10-02, round 3 on 2026-10-13, round 4 on 2026-10-23)** — latest releases (MeDIC
  redesign local builds of 2026-10-01 and 2026-10-13, DAKP 1.16.0), both **evaluated as
  in-progress work**, so these rates are a snapshot to inform the next iteration, not a final
  verdict on either source; FDA + EMA evidence; two Claude reviewers + tie-breaker as a
  Jev-free reference; Jev (TypeSafe System One) validated against it and run over the full
  population. Below.
- **v1 (2026-06-23)** — previous releases; FDA only. Kept further down for comparison.

## v2 pipeline

| step | script | output (`out/v2/`) |
|---|---|---|
| 1. index regulator text | `label_index.py` (openFDA bulk export + EMA medicines report, homeopathic labels dropped) | `data/inputs/labels/*_index.json.gz` |
| 1b. moieties for label UNIIs | `label_moieties.py` (GSRS, cached in `data/drug_groups_cache.json`) | — |
| 2. evidence + sample | `audit_sample.py --n 300` (latest; seed 20261002, two-stage so it extends the first 150; `--keep dakp-approved` re-draws only MEDIC when DAKP didn't change) and `--release old` (previous releases, built from their source files) | `sample.jsonl`, `sample_old.jsonl`, `sample_b1001.jsonl` / `sample_b1013.jsonl` (the 2026-10-01 and 2026-10-13 MEDIC builds, archived under sid prefixes `b1001:` / `b1013:` when a later build replaced them; the matching `blind_key_N.json` is re-pointed at the archived sids), `population*.jsonl`, `evidence*.json.gz` |
| 2b. blind + batch | `audit_batches.py prepare/tiebreak/combo --round N` (deterministic; reviewer instructions in `audit_reviewer_instructions.md`) | `blind_key*.json`, `batch<N>_{a,b}_*.json`, `tiebreak<N>_input_*.json`, `combo<N>_input_*.json` |
| 3. reviewer A, reviewer B (adversarial) | round 1: 16 blind Claude subagents (first 150 latest/source; `blind_key.json`); round 2: 40 more over the other 900 edges, latest and previous shuffled together (`blind_key_2.json`); round 3: 16 over a fresh 300-edge sample of the 2026-10-13 MEDIC rebuild (`blind_key_3.json`); round 4: 16 over a fresh 300-edge sample of the 2026-10-23 v2 release candidate (`blind_key_4.json`) | `claude_{a,b}_*.json`, `claude2_{a,b}_*.json`, `claude3_{a,b}_*.json`, `claude4_{a,b}_*.json` |
| 4. tie-break A≠B | 1 + 2 + 1 + 1 Claude subagents | `tiebreak_0.json`, `tiebreak2_*.json`, `tiebreak3_0.json`, `tiebreak4_0.json` |
| 5. co-ingredient check | 2 + 4 + 2 + 2 Claude subagents, every TARGET whose evidence included combination labels, single vs combination text separated | `combo_check_*.json`, `combo2_check_*.json`, `combo3_check_*.json`, `combo4_check_*.json` |
| 6. Jev | `audit_jev.py --sample` / `--population` (`jev-1.13.0`, needs `TYPESAFE_API_KEY`) | `jev_sample.jsonl`, `jev_population.jsonl` |
| 7. report | `audit_report.py` (deterministic): latest rates, like-for-like previous-release and previous-build rates and the changes, Jev validation on all reference edges | `audit_results.json`, `src/data/fp_audit.json`, `src/data/label_check.parquet` |
| 8b. issue worklists | `medic_issue_worklists.py` (export-derived) + the load-tier / audit tables | `medic_issues/*.tsv` (linked from the issues drafted for the medic repo) |
| 8. load tiers | `audit_tiers.py` (deterministic): per-pair MEDIC features + cross-source membership + label check, scored against the reference | `tiers.json`, `medic_load_tiers.tsv`, `src/data/tiers.json`, `src/data/medic_tiers.parquet` |
| 9. regression scorer | `medic_regression.py build` freezes the audit gold sets (38 setting errors, 216 correct, 18 wrong contraindications, negated, self-clash, ion/metabolite, vaccine, cut-text, 121 dropped-but-correct, stub and unresolvable-id nodes) into one file; `medic_regression.py score GOLD EXPORT_DIR` is stdlib-only and scores any MeDIC export against them by id or by label, so the medic maintainers can run it on an unpublished build | `medic_regression_gold.json`; `<export_dir>/medic_regression_score.json` |
| 10. build-over-build diff | `medic_build_diff.py [OLD] [NEW]`: pair-level diff of two local MeDIC builds (default `b1013` → `new`) with the same reconciler, moiety grouping and change reasons as `just changes`, which only diffs the published medic-ingest release | `build_diff_<OLD>_<NEW>.json` / `.tsv` |

Run steps 1–2 and 6–7 with `PYTHONPATH=pipeline:. uv run [--with openpyxl|typesafe-sdk] python -m experiments.<script>`.

**Evidence.** FDA: every label carrying the drug's UNII *or* sharing any GSRS active moiety
with it (bare-ion moieties excluded), single-ingredient and combination labels, indications
deduplicated at sentence level and packed disease-mentioning-first (9k chars). EMA: EPAR
indication of authorised products matched by INN. **Scoping:** an edge is judged against
the regulators it cites (MEDIC names them; DAKP via NDA/ANDA/BLA vs EMEA numbers) that we hold
text for; an FP7 "not in label" only counts where we hold text for *every* cited regulator.

**Reference & acceptance (fixed before results).** Reference = A and B agree, else the
tie-breaker; co-ingredient overrides applied to TARGETs. Jev is scored against it and is
accepted for stand-alone use only if binary agreement is within 5 pts of the A↔B ceiling and
κ ≥ 0.6. Otherwise only its confidence ≥ 0.9 verdicts are used.

### v2 results (round 4, 2026-10-23; the MeDIC v2 release candidate, 300 fresh edges)

| source | previous release | build 2026-10-01 | build 2026-10-13 | latest (2026-10-23 RC) | change vs 2026-10-13 build (95% CI) |
|---|---|---|---|---|---|
| MEDIC | 25.8% (n=299) | 25.6% (n=297) | 25.8% (n=291) | **25.3%** (n=297) | −0.5 pts (−7.6 to +6.5) |
| DAKP-approved | 35.0% (n=300) | — | — | 32.6% (n=298) | not re-sampled |

The headline did not move, but the error mix did, and for the first time MEDIC's own tier does:
- **setting-as-target 13.1% → 1.0%** (−12.1 pts, CI −16.5 to −8.2): the structured extraction
  with context qualifiers (#89/#90) removed the largest error type of the last two builds;
- **co-ingredient +4.6 pts** (CI 0.8 to 8.7; now 8.4%) and **not-in-label +5.3 pts** (CI 0.7 to
  9.9; now 11.1%), both concentrated in LOW-tier edges from OTC, excipient and combination labels;
- **reliability now discriminates**: HIGH 10.5% wrong (n=200), MEDIUM 23.5% (n=17), LOW 62.5%
  (n=80); the 2026-10-13 build's HIGH tier was 26.7%, the same as the whole;
- `preventative_for_condition` edges (49 of the 300 sampled; vaccines, risk reduction,
  prophylaxis, split out of `treats` in this build) are 38% wrong vs 21% for `treats`.

Population (Jev screen, corrected): MEDIC 24.6% (20.9–28.3) over 7,331 screened edges; Jev
agreement with the reference is unchanged (binary 88.7%, κ 0.72; ≥0.9 confidence: 97.5% on 57%
coverage). Reviewer A↔B binary agreement 96.3% (κ 0.91), 17 of 300 tie-broken; 30 pairs were
drawn in two rounds, 27 got the same verdict.

**Build over build** (`medic_build_diff.py b1013 new`): the candidate kept 4,396 of the
2026-10-13 build's 7,837 indication pairs, dropped 3,441 (716 with the drug gone; 2,078 same
drug, different diseases) and added 5,301 (9,697 now). Of the 291 pairs judged in round 3 it
dropped 60 of the 76 errors and 40 of the 215 correct ones. The regression scorer on the
export: 37 of 38 audited setting errors gone, 15 of 18 wrong contraindications gone, 171 of
216 audited-correct pairs still present (10 of them as `preventative_for_condition`), 46 of 46
vaccine-as-treats edges gone — but 41 of those because the vaccine has no edge at all.

Three mechanisms behind the losses were traced in the candidate's working tree and drafted as
issues (`../medic-redesign/medic-feedback/issues/14–16`): the DailyMed document-type allowlist
never fetches VACCINE LABEL / plasma-derivative / cell-therapy labels; 22.6% of extracted
claims are `sssom:NoTermFound` at disease grounding and 1,167 labels with claims mine to
nothing; `activeMoiety` under inactive ingredients makes excipients drug subjects (162 pairs).
Worklists: `medic_issues/labels_outside_human_doctype_filter.tsv`,
`labels_lost_to_disease_grounding.tsv`, `unplaceable_extracted_targets.tsv`,
`inactive_ingredient_subjects.tsv`.

**Load tiers** (`audit_tiers.py`, now over `treats` + `preventative_for_condition` pairs):
label-confirmed **3,256 pairs (33.6%) at 0.8%** (CI 0.1–4.2, n=130; was 2,641 at 0.7%);
corroborated but inconclusive 837 at 19%; unscreened 1,874; single-source 841 at 23%;
flagged/suspect 2,889 at 62%. T1 ∩ MONDO = 2,440 pairs, ∩ rare = 1,414 on 451 rare diseases
(was 2,138 / 1,286 / 449). MEDIC HIGH alone: 5,771 pairs at 10.5% (n=200) — usable as a
second-choice gate now, which it was not before.

### v2 results (round 3, 2026-10-13; 300 edges per source per release/build)

| source | previous release | build 2026-10-01 | latest (2026-10-13) | change vs previous release (95% CI) | change vs 2026-10-01 build |
|---|---|---|---|---|---|
| MEDIC | 25.8% (n=299) | 25.6% (n=297) | **25.8%** (n=291) | 0.0 pts (−7.0 to +7.1) | +0.2 pts (−6.8 to +7.2) |
| DAKP-approved | 35.0% (n=300) | — | 32.6% (n=298) | −2.4 pts (−10.0 to +5.2) | — |

Neither source's precision changed; MEDIC's rebuild (negation-scoping fix + verbatim
re-extraction) did not move it either. The *kinds* of MEDIC error, latest vs medic-ingest:
- **setting-as-target** is now the largest type at 13.1% of edges (+8.4 pts, CI 3.9 to 13.1);
- **negated indications** are gone (−6.0 pts, CI −9.3 to −3.4; none in the latest sample);
- **co-ingredient attribution** is new (+3.8 pts, CI 1.7 to 6.6; 11 edges, all MEDIC's);
- not-in-label 5.8%, symptom swap 2.1%; nothing else moved significantly.
Versus the 2026-10-01 build nothing is significant (setting +3.7, CI −1.5 to 8.8; co-ingredient
−1.3, CI −4.8 to 2.1). 56 of the 76 errors found in the 2026-10-01 sample are still asserted
by the rebuild (184 of 221 correct pairs are).
- **DAKP** — "not in label" mappings up (+9.4, CI 4.3 to 14.7), concentrated in the newly used
  UMLS disease terms; setting, symptom-swap and over-broad errors each trend down (not
  individually significant). (Unchanged from round 2; DAKP 1.16.0 was not re-sampled.)

Population (Jev screen corrected by its latest PPV/NPV): MEDIC 27.6% (24.5–30.9) over 5,579
screened edges, DAKP-approved 32.2% (27.8–36.6).

**Load tiers** (`audit_tiers.py`, fresh-sample error rate; details on the site's *What to
load* page): label-confirmed (Jev ≥ 0.9 TARGET, no suspect feature) **2,641 pairs at 0.7%**
(CI 0.1–3.6, n=152); corroborated but label check inconclusive 824 at 35%; unscreened (no
FDA/EMA text held, mostly PMDA/CDSCO-only) 1,797, unmeasured; unconfirmed single-source 694 at
47%; flagged/suspect 1,834 at 68%. MEDIC's HIGH reliability tier is 26.7% wrong, the same as
the whole; cross-source agreement alone 15% (n=166). By disease class (monarch-kg is
disease-centric): MONDO rare-disease pairs 2,718 at 18.7% fresh (the cleanest slice), other
MONDO 2,989 at 29.7%, HP-phenotype targets (OTC symptom relief) 827 at 39.3%, UMLS/other
1,256 at 23.7%; label-confirmed ∩ MONDO = 2,138 pairs, ∩ rare = 1,286 (449 rare diseases).

**Jev** (validated on all 1,485 reference edges): reviewer A↔B binary agreement 96.3% (κ 0.91);
Jev vs reference 88.9% (κ 0.73) — **does not meet the acceptance bar**. At confidence ≥ 0.9
(57% of edges) agreement is 97.7%, flag precision 93.6%, target precision 98.6%; those
verdicts back the site's "label check" column. Weakest on symptom swaps (50%), over-broad
parents (70%) and co-ingredient cases (19%). Decomposing into yes/no questions did not help
(84.1%). Cost: ≈ $2.10 for the full screen plus all gold edges; the round-3 top-up (300 sample
+ 1,421 new population edges) cost $0.18.

**Round 0** (`round0_narrow_evidence/`): a first reviewer pass on narrower evidence
(exact-UNII labels only, no combination labels, whole-text truncation) produced visibly more
"not in label" calls (gemcitabine judged on an intravesical product only, etc.); superseded.

**Caveats.** Precision only, not recall. Reviewers are one model family (agreement is an
upper bound). Lenient on generic indications (label "pain" → edge "neck pain" counts).
Homeopathic labels are filtered by marker text; a few unmarked ones slipped through. openFDA
labels drift — `sample.jsonl` archives the exact text judged.

---

# v1: False-positive audit (DAKP-approved & MEDIC vs FDA label text)

A reproducible, sampled measurement of how often an asserted drug→disease *indication* edge
is **not** a genuine treatment target according to the FDA label — i.e. a measured
false-positive rate, replacing eyeballed exemplars.

## Scoping (what is checked, and why)
- **DAKP-approved** = `dakp='exact' AND dakp_status='approved_for_condition'` (5,030 pairs; all FDA).
- **MEDIC** = `medic='exact' AND` the pair is **`[FDA]`-tagged** in `medic_evidence.parquet`
  (8,725 of 10,878 MEDIC pairs). The other **2,153 MEDIC pairs are EU/Japan-only (EMA/PMDA)
  approvals and are *excluded*** — judging them against the FDA label would be unfair. To
  audit those we'd have to fetch EMA/PMDA source text and compare the same way (not done here).
- **Independence rule:** an edge is only *judged* if we **fetched the FDA label ourselves and
  confirmed it is the same substance** (`label_method != "none"`: UNII match, or generic-name
  match verified by UNII). Edges with no independently-fetched label are **excluded** — never
  scored from a source's own self-reported snippet. (MEDIC's snippet is shown to adjudicators
  as context only; snippet-only edges fall out via the independence rule.)

## Pipeline
1. **Sample + fetch labels** (seeded, network) →
   `uv run python -m experiments.fp_audit_sample --n 120`
   - `SEED = 20260623`; draws `n` random edges per source from `pairs.parquet`.
   - Strict openFDA matching (UNII first; name fallback only if the returned label's
     `openfda.unii` contains our UNII). Writes `out/fp_sample.jsonl` and caches every label
     in `out/openfda_cache.json` (so labels don't drift on re-run).
2. **Adjudicate** (LLM, non-deterministic; outputs archived) — 6 `general-purpose` subagents
   (Opus 4.8), 40 edges each, classify every edge against the record's `indications`
   (contraindications/warnings only to confirm FP3/FP5). Verdicts → `out/verdicts_<src>_<k>.json`.
   Rubric per edge: `TARGET` | `FP1_setting` | `FP2_symptom_swap` | `FP3_cross_section` |
   `FP4_overbroad` | `FP5_negation` | `FP7_notintext` | `NO_LABEL` | `UNSURE`.
3. **Multi-SPL recheck** of `FP7_notintext` (network) — a drug's indications span many SPLs,
   but step 1 fetched one. `out/fp7_recheck.jsonl` unions `indications_and_usage` across up to
   10 SPLs per UNII; one subagent re-judges → `out/verdicts_recheck.json` (rescues edges whose
   indication lived on another SPL; confirms the rest as `FP7_confirmed`).
4. **Report** (deterministic, no network/LLM) →
   `uv run python -m experiments.fp_audit_report`
   - Merges verdicts (recheck overrides FP7), keeps only independent labels, computes
     precision + FP rate with Wilson 95% CIs and a per-type breakdown. Writes
     `out/fp_audit_results.json`. Re-running on the archived verdicts reproduces the numbers.

## Reproducibility notes
- The **edge sample** is fully reproducible (fixed seed + deterministic row order).
- **Label text** can drift as FDA updates labels; `openfda_cache.json` archives what we fetched.
- **Adjudication is LLM-based** (Opus 4.8) and not bit-reproducible; the verdict files are
  archived so `fp_audit_report.py` is stable. Re-running the agents may shift counts slightly.

## Results snapshot (2026-06-23)
| source | n judged | precision (CI) | FP rate (CI) |
|---|---|---|---|
| DAKP-approved | 94 | 58.5% (48–68) | 41.5% (32–52) |
| MEDIC (FDA-scoped) | 64 | 78.1% (67–87) | 21.9% (14–33) |

DAKP FP is driven by not-in-any-label spurious mappings (~20%, many acronym/synonym
collisions) and over-broad mappings (~9%); MEDIC's main FP type is setting-as-target (~8%).

## Caveats
- **Single adjudicator per edge** (no second-rater/adversarial check yet).
- **MEDIC n=64**: openFDA UNII coverage is lower for MEDIC (many CHEBI structural / EU-Japan
  drugs don't resolve), so the MEDIC estimate is on a smaller, UNII-matchable subset.
- These are **precision** (false-positive) rates for asserted edges — **not recall** (misses).

## Artifacts (`out/`)
`fp_sample.jsonl` · `openfda_cache.json` · `verdicts_dakp_{0,1,2}.json` ·
`verdicts_medic_{0,1,2}.json` · `fp7_recheck.jsonl` · `verdicts_recheck.json` ·
`fp_audit_results.json`
