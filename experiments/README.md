# False-positive audit (DAKP-approved & MEDIC vs FDA label text)

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
