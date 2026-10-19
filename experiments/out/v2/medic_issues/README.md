# Worklists for the MeDIC issues drafted 2026-10-13

Per-issue tables for the 2026-10-13 local MeDIC build (`medic2@47dd0b7`, export sha256
`90f28248…`), in MeDIC's own subject/object ids. Regenerate the export-derived ones with
`uv run python -m experiments.medic_issue_worklists`; the audit-derived ones come from
`audit_report.py` and `audit_tiers.py`.

| file | issue | source |
|---|---|---|
| `../medic_load_tiers.tsv` | 01, 02, 04, 09 — every indication pair with `combo_only`, `homeopathic`, `drug_ion`, `drug_metabolite`, `drug_unresolved`, `jev`/`jev_conf`/`jev_flag`, `tier`, `axis` | `audit_tiers.py` |
| `drug_ids_unknown_to_node_normalizer.tsv` | 03 | export + Node Normalizer cache |
| `self_clash_pairs.tsv`, `negated_or_excluded_treats_edges.tsv` | 05 | export |
| `unnamed_stub_diseases.tsv`, `inverted_or_abbreviated_disease_names.tsv` | 06 | export |
| `text_cut_but_not_flagged_truncated.tsv` | 07 | export |
| `../../../../src/data/fp_audit.json` (`edges`, source `medic`) | 08, 10, 11, 12 — every audited edge with verdicts, quotes, notes | `audit_report.py` |
| `contraindication_sample_audit.tsv` | 10 — 80 contraindication pairs of the 2026-10-01 build, one reviewer | round 2 |
| `recall_gap_candidates.tsv`, `previous_release_dropped_but_correct.tsv` | 11 — computed on the 2026-10-01 build | round 2 (`medic-feedback/scripts/analyze.py`) |
| `vaccine_like_treats_edges.tsv` | 12 | export |
