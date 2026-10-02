# Indication audit

Two rounds, each measuring how often an asserted drug→disease *indication* edge is **not** a
genuine treatment target according to regulator text.

- **v2 (current, 2026-10-02)** — latest releases (MeDIC redesign, DAKP 1.16.0), both
  **evaluated as in-progress work**, so these rates are a snapshot to inform the next
  iteration, not a final verdict on either source; FDA + EMA
  evidence; two Claude reviewers + tie-breaker as a Jev-free reference; Jev (TypeSafe System
  One) validated against it and run over the full population. Below.
- **v1 (2026-06-23)** — previous releases; FDA only. Kept further down for comparison.

## v2 pipeline

| step | script | output (`out/v2/`) |
|---|---|---|
| 1. index regulator text | `label_index.py` (openFDA bulk export + EMA medicines report, homeopathic labels dropped) | `data/inputs/labels/*_index.json.gz` |
| 1b. moieties for label UNIIs | `label_moieties.py` (GSRS, cached in `data/drug_groups_cache.json`) | — |
| 2. evidence + sample | `audit_sample.py --n 300` (latest; seed 20261002, two-stage so it extends the first 150) and `--release old` (previous releases, built from their source files) | `sample.jsonl`, `sample_old.jsonl`, `population*.jsonl`, `evidence*.json.gz` |
| 3. reviewer A, reviewer B (adversarial) | round 1: 16 blind Claude subagents (first 150 latest/source; `blind_key.json`); round 2: 40 more over the other 900 edges, latest and previous shuffled together (`blind_key_2.json`) | `claude_{a,b}_*.json`, `claude2_{a,b}_*.json` |
| 4. tie-break A≠B | 1 + 2 Claude subagents | `tiebreak_0.json`, `tiebreak2_*.json` |
| 5. co-ingredient check | 2 + 4 Claude subagents, every TARGET whose evidence included combination labels, single vs combination text separated | `combo_check_*.json`, `combo2_check_*.json` |
| 6. Jev | `audit_jev.py --sample` / `--population` (`jev-1.13.0`, needs `TYPESAFE_API_KEY`) | `jev_sample.jsonl`, `jev_population.jsonl` |
| 7. report | `audit_report.py` (deterministic): latest rates, like-for-like previous rates and the change, Jev validation on all reference edges | `audit_results.json`, `src/data/fp_audit.json`, `src/data/label_check.parquet` |

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

### v2 results (2026-10-02; 300 edges per source per release)

| source | previous release | latest release | change (95% CI) |
|---|---|---|---|
| MEDIC | 25.8% (n=299) | 25.6% (n=297) | −0.2 pts (−7.1 to +6.8) |
| DAKP-approved | 35.0% (n=300) | 32.6% (n=298) | −2.4 pts (−10.0 to +5.2) |

Neither source's precision changed significantly; the *kinds* of error did:
- **MEDIC** — negated indications nearly eliminated (−5.3 pts, CI −8.6 to −2.5); new
  co-ingredient attribution errors (+5.1, CI 2.7 to 8.2); more setting-as-target (+4.7, CI 0.6
  to 9.0).
- **DAKP** — "not in label" mappings up (+9.4, CI 4.3 to 14.7), concentrated in the newly used
  UMLS disease terms (24% of those edges); setting, symptom-swap and over-broad errors each
  trend down (not individually significant).

Population (Jev screen corrected by its latest-release PPV/NPV): MEDIC 25.7% (22.3–29.2),
DAKP-approved 32.2% (27.8–36.6). (The v1 audit, FDA-only and a different protocol, measured
20.3% / 33.0% on the previous releases; kept for reference.)

**Jev** (validated on all 1,194 reference edges): reviewer A↔B binary agreement 96.3% (κ 0.91);
Jev vs reference 88.3% (κ 0.72) — **does not meet the acceptance bar**. At confidence ≥ 0.9
(55% of edges) agreement is 97.5%, flag precision 92.2%, target precision 98.7%; those
verdicts back the site's "label check" column. Weakest on symptom swaps (50%), over-broad
parents (70%) and co-ingredient cases (19%). Decomposing into yes/no questions did not help
(84.1%). Cost: ≈ $2.10 for the full screen plus all gold edges.

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
