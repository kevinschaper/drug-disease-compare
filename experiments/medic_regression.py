"""Score a MeDIC KGX export against the frozen audit gold sets (stdlib only).

Two modes:

  build   (run from this repo)   writes experiments/out/v2/medic_regression_gold.json
          from the round-3 audit outputs and the issue worklists.
  score   (run anywhere)         python3 medic_regression.py score GOLD.json EXPORT_DIR
          where EXPORT_DIR holds medic_edges.jsonl and medic_nodes.jsonl.

The gold file is self-contained so that the MeDIC maintainers can score a build
they have not published:

  curl -LO https://raw.githubusercontent.com/kevinschaper/drug-disease-compare/main/experiments/medic_regression.py
  curl -LO https://raw.githubusercontent.com/kevinschaper/drug-disease-compare/main/experiments/out/v2/medic_regression_gold.json
  python3 medic_regression.py score medic_regression_gold.json exports/

Each gold pair is matched three ways, loosest last: MeDIC's own subject/object ids
from the 2026-10-13 export; the canonical (Node-Normalizer) ids, which are usually
the same for MONDO/CHEBI; and lower-cased drug + disease labels, so a re-grounded
id still counts. "present" means any of the three matched a `biolink:treats`
edge (or `contraindicated_in` for the contraindication set).
"""
from __future__ import annotations

import csv
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "out" / "v2"
GOLD = OUT / "medic_regression_gold.json"
EXAMPLES_89 = ["eplerenone", "posaconazole", "bosentan", "tirzepatide", "basiliximab", "deferasirox"]  # named in medic #89
JOINABLE = ("UNII:", "RXCUI:", "DRUGBANK:", "PUBCHEM.COMPOUND:", "CHEMBL.COMPOUND:", "CAS:")  # xref prefixes the Node Normalizer resolves


def _tsv(name: str) -> list[dict]:
    with open(OUT / "medic_issues" / name) as f:
        return list(csv.DictReader(f, delimiter="\t"))


def _pair(medic_s, medic_o, canon_s, canon_o, drug, disease, **extra) -> dict:
    return {"medic_subject": medic_s or "", "medic_object": medic_o or "", "canonical_drug": canon_s or "",
            "canonical_disease": canon_o or "", "drug_label": (drug or "").lower(),
            "disease_label": (disease or "").lower(), **extra}


def build() -> None:
    tiers = {}
    with open(OUT / "medic_load_tiers.tsv") as f:
        for r in csv.DictReader(f, delimiter="\t"):
            tiers[(r["canonical_drug"], r["canonical_disease"])] = r
    audit = json.load(open(ROOT / "src" / "data" / "fp_audit.json"))
    sets: dict[str, dict] = {}

    def from_audit(verdicts, key, desc, issue):
        rows = []
        for e in audit["edges"]:
            if e["source"] != "medic" or e["release"] != "new" or e["verdict"] not in verdicts:
                continue
            t = tiers.get((e["drug"], e["disease"]), {})
            rows.append(_pair(t.get("medic_subject"), t.get("medic_object"), e["drug"], e["disease"],
                              e["drug_label"], e["disease_label"], verdict=e["verdict"], note=e.get("note", "")[:160]))
        sets[key] = {"issue": issue, "description": desc, "predicate": "biolink:treats",
                     "want": "absent" if key != "audited_correct" else "present", "pairs": rows}

    from_audit({"FP1_setting"}, "setting_as_target", "audited population/setting-as-target errors", "#89")
    from_audit({"FP6_coingredient"}, "coingredient", "audited co-ingredient attributions", "#88")
    from_audit({"FP2_symptom_swap", "FP3_cross_section", "FP4_overbroad", "FP5_negation", "FP7_absent"},
               "other_errors", "other audited errors (symptom swap, cross-section, over-broad, negation, not in label)", "#91")
    from_audit({"TARGET"}, "audited_correct", "audited-correct indications (must survive)", "#98")

    sets["contraindication_wrong"] = {
        "issue": "#97", "description": "audited-wrong contraindications", "predicate": "biolink:contraindicated_in",
        "want": "absent",
        "pairs": [_pair(r["medic_subject"], r["medic_object"], r["drug"], r["disease"], "", "", note=r["note"][:160])
                  for r in _tsv("contraindication_sample_audit.tsv") if r["verdict"].strip().upper() not in ("", "CORRECT", "UNSURE")]}
    sets["negated_or_excluded"] = {
        "issue": "#93", "description": "treats edges MeDIC itself marks negated/EXCLUDED", "predicate": "biolink:treats",
        "want": "absent",
        "pairs": [_pair(r["subject"], r["object"], "", "", r["drug"], r["disease"]) for r in _tsv("negated_or_excluded_treats_edges.tsv")]}
    sets["self_clash"] = {
        "issue": "#93", "description": "pairs both indicated and contraindicated", "predicate": "both",
        "want": "absent",
        "pairs": [_pair(r["subject"], r["object"], "", "", r["drug"], r["disease"]) for r in _tsv("self_clash_pairs.tsv")]}
    sets["ion_or_metabolite_drug"] = {
        "issue": "#95", "description": "pairs whose drug is a bare ion or active metabolite", "predicate": "biolink:treats",
        "want": "absent",
        "pairs": [_pair(r["medic_subject"], r["medic_object"], r["canonical_drug"], r["canonical_disease"], r["drug_label"], r["disease_label"])
                  for r in tiers.values() if r["drug_ion"] == "True" or r["drug_metabolite"] == "True"]}
    sets["vaccine_as_treats"] = {
        "issue": "#99", "description": "vaccine-like products exported as treats", "predicate": "biolink:treats",
        "want": "absent",
        "pairs": [_pair(r["subject"], r["object"], "", "", r["drug"], r["disease"]) for r in _tsv("vaccine_like_treats_edges.tsv")]}
    sets["text_cut_unflagged"] = {
        "issue": "#100", "description": "supporting_text ending in '[see' with truncated=false", "predicate": "any",
        "want": "absent",
        "pairs": [_pair(r["subject"], r["object"], "", "", r["drug"], r["disease"], predicate=r["predicate"])
                  for r in _tsv("text_cut_but_not_flagged_truncated.tsv")]}
    sets["dropped_but_correct"] = {
        "issue": "#98", "description": "medic-ingest pairs judged correct that the redesign dropped", "predicate": "biolink:treats",
        "want": "present",
        "pairs": [_pair("", "", r["drug"], r["disease"], r["drug_label"], r["disease_label"]) for r in _tsv("previous_release_dropped_but_correct.tsv")]}
    nodes = {"unnamed_stub_diseases": {"issue": "#96", "description": "disease nodes used by edges with no name",
                                       "want": "named", "ids": [r["id"] for r in _tsv("unnamed_stub_diseases.tsv")]},
             "drug_ids_unknown_to_nodenorm": {"issue": "#94", "description": "drug ids the SRI Node Normalizer does not know",
                                              "want": "xref_or_gone", "ids": [r["id"] for r in _tsv("drug_ids_unknown_to_node_normalizer.tsv")]}}
    gold = {"built_from": "MeDIC export 2026-10-13 (medic2@47dd0b7); drug-disease-compare round-3 audit",
            "pair_sets": sets, "node_sets": nodes, "examples_89": EXAMPLES_89, "joinable_xref_prefixes": JOINABLE}
    GOLD.write_text(json.dumps(gold, indent=1))
    print(f"wrote {GOLD}")
    for k, s in sets.items():
        print(f"  {k:28s} {len(s['pairs']):4d} pairs  want {s['want']}")
    for k, s in nodes.items():
        print(f"  {k:28s} {len(s['ids']):4d} nodes")


def _load_export(d: Path):
    E = [json.loads(line) for line in open(d / "medic_edges.jsonl")]
    N = {}
    if (d / "medic_nodes.jsonl").exists():
        for line in open(d / "medic_nodes.jsonl"):
            n = json.loads(line)
            N[n["id"]] = n
    return E, N


def score(gold_path: Path, export_dir: Path) -> dict:
    gold = json.load(open(gold_path))
    E, N = _load_export(export_dir)
    name = lambda i: (N.get(i, {}).get("name") or "").lower()  # noqa: E731
    by_id, by_label = {}, {}
    for e in E:
        p = e["predicate"]
        by_id.setdefault((e["subject"], e["object"], p), []).append(e)
        by_label.setdefault((name(e["subject"]), name(e["object"]), p), []).append(e)
    # a drug counts as "gone" only when it has no edge under any predicate
    drug_edges = Counter(name(e["subject"]) for e in E)
    OTHER_INDICATION = ("biolink:preventative_for_condition", "biolink:diagnoses")  # split out of treats since 2026-10-23

    def find(pair, pred):
        preds = ["biolink:treats", "biolink:contraindicated_in"] if pred == "both" else \
                sorted({e["predicate"] for e in E}) if pred == "any" else [pred]
        for p in preds:
            for key in ((pair["medic_subject"], pair["medic_object"]), (pair["canonical_drug"], pair["canonical_disease"])):
                if key[0] and key[1] and (key[0], key[1], p) in by_id:
                    return "id", by_id[(key[0], key[1], p)]
            if pair["drug_label"] and pair["disease_label"] and (pair["drug_label"], pair["disease_label"], p) in by_label:
                return "label", by_label[(pair["drug_label"], pair["disease_label"], p)]
        return None, []

    result = {"export": str(export_dir), "edges": len(E), "nodes": len(N),
              "predicates": dict(Counter(e["predicate"] for e in E)),
              "reliability": dict(Counter(e.get("medic_pair_reliability") or e.get("medic_reliability") or "?" for e in E)),
              "qualifier_slots": {k: sum(1 for e in E if e.get(k)) for k in
                                  ("disease_context_qualifier", "population_context_qualifier", "sex_qualifier",
                                   "temporal_context_qualifier", "anatomical_context_qualifier", "qualified_predicate",
                                   "medic_co_administered_with")},
              "sets": {}, "examples_89": {}}
    for k, s in gold["pair_sets"].items():
        rows = []
        for pair in s["pairs"]:
            how, hits = find(pair, s.get("predicate", "biolink:treats"))
            if k == "self_clash":  # present only if BOTH predicates still exist
                _, h1 = find(pair, "biolink:treats"); _, h2 = find(pair, "biolink:contraindicated_in")
                how = "id" if h1 and h2 else None
            if k == "text_cut_unflagged":  # present only if the text is still cut and unflagged
                how = how if any((e.get("supporting_text") or "").rstrip().endswith("[see") and not e.get("medic_supporting_text_truncated") for e in hits) else None
            # a treats pair that is absent may have moved to another indication predicate
            other = ""
            if not how and s.get("predicate", "biolink:treats") in ("biolink:treats", "both"):
                other = next((p.split(":")[1] for p in OTHER_INDICATION if find(pair, p)[0]), "")
            rows.append({**{x: pair[x] for x in ("drug_label", "disease_label", "medic_subject", "medic_object")},
                         "present": bool(how), "matched_by": how, "present_other_predicate": other,
                         "drug_still_has_edges": drug_edges.get(pair["drug_label"], 0) > 0})
        n = len(rows); present = sum(r["present"] for r in rows)
        good = present if s["want"] == "present" else n - present
        lost_drugs = sum(1 for r in rows if not r["present"] and not r["drug_still_has_edges"])
        moved = dict(Counter(r["present_other_predicate"] for r in rows if r["present_other_predicate"]))
        result["sets"][k] = {"issue": s["issue"], "description": s["description"], "want": s["want"], "n": n,
                             "present": present, "as_wanted": good, "pairs_absent_with_drug_gone": lost_drugs,
                             "moved_to_other_predicate": moved, "rows": rows}
    for k, s in gold["node_sets"].items():
        ids = s["ids"]
        if k == "unnamed_stub_diseases":
            still = [i for i in ids if i in N and not N[i].get("name")]
            result["sets"][k] = {"issue": s["issue"], "description": s["description"], "n": len(ids),
                                 "still_unnamed": len(still), "gone": sum(1 for i in ids if i not in N)}
        else:
            pref = tuple(gold.get("joinable_xref_prefixes", JOINABLE))
            with_xref = [i for i in ids if i in N and any(str(x).startswith(pref) for x in (N[i].get("xref") or []))]
            result["sets"][k] = {"issue": s["issue"], "description": s["description"], "n": len(ids),
                                 "still_present": sum(1 for i in ids if i in N), "now_with_xref": len(with_xref),
                                 "gone": sum(1 for i in ids if i not in N)}
    for drug in gold["examples_89"]:
        rows = [r for r in result["sets"]["setting_as_target"]["rows"] if r["drug_label"] == drug]
        objs = sorted({name(e["object"]) for e in E if e["predicate"] == "biolink:treats" and name(e["subject"]) == drug})
        result["examples_89"][drug] = {"wrong_pairs": [(r["disease_label"], r["present"]) for r in rows],
                                       "n_objects": len(objs), "objects": objs[:12]}
    if not N:
        result["warning"] = "no medic_nodes.jsonl: label matching and the node sets are unavailable; only id matches count"
    return result


def drug_has_any(r: dict, drug: str) -> bool:
    return any(row["drug_still_has_edges"] for row in r["sets"]["setting_as_target"]["rows"] if row["drug_label"] == drug)


def report(r: dict) -> str:
    L = [f"MeDIC export: {r['export']}  edges {r['edges']}  nodes {r['nodes']}",
         "predicates: " + ", ".join(f"{k.split(':')[1]} {v}" for k, v in sorted(r["predicates"].items())),
         "reliability: " + ", ".join(f"{k} {v}" for k, v in sorted(r["reliability"].items())),
         "qualifier slots: " + ", ".join(f"{k} {v}" for k, v in r["qualifier_slots"].items() if v) or "qualifier slots: none", "",
         f"{'set':30s} {'issue':6s} {'n':>4s} {'present':>8s} {'as wanted':>10s}  note"]
    for k, s in r["sets"].items():
        if "present" in s:
            notes = []
            if s["want"] == "absent" and s["pairs_absent_with_drug_gone"]:
                notes.append(f"{s['pairs_absent_with_drug_gone']} absent because the drug has no edges under any predicate")
            if s["want"] == "present" and s["pairs_absent_with_drug_gone"]:
                notes.append(f"{s['pairs_absent_with_drug_gone']} missing with the drug gone entirely")
            for pred, c in s.get("moved_to_other_predicate", {}).items():
                notes.append(f"{c} now under {pred}")
            L.append(f"{k:30s} {s['issue']:6s} {s['n']:4d} {s['present']:8d} {s['as_wanted']:10d}  {'; '.join(notes)}")
        elif "still_unnamed" in s:
            L.append(f"{k:30s} {s['issue']:6s} {s['n']:4d} {'':8s} {s['n']-s['still_unnamed']:10d}  {s['still_unnamed']} still unnamed, {s['gone']} gone")
        else:
            L.append(f"{k:30s} {s['issue']:6s} {s['n']:4d} {'':8s} {s['now_with_xref']+s['gone']:10d}  {s['now_with_xref']} now carry xref, {s['gone']} gone, {s['still_present']-s['now_with_xref']} unchanged")
    L.append("")
    L.append("the six #89 examples (audited setting-as-target pairs for these drugs):")
    for d, x in r["examples_89"].items():
        if x["n_objects"] == 0:
            state = "drug has no treats edges" + ("" if drug_has_any(r, d) else " (no edges at all)")
        elif any(p for _, p in x["wrong_pairs"]):
            state = "still present: " + ", ".join(dis for dis, p in x["wrong_pairs"] if p)
        else:
            state = "fixed"
        L.append(f"  {d:14s} {state:50s} objects now: {', '.join(x['objects'][:5])}{' …' if x['n_objects'] > 5 else ''}")
    if r.get("warning"):
        L.append("\nWARNING: " + r["warning"])
    return "\n".join(L)


def main(argv: list[str]) -> None:
    if argv[:1] == ["build"]:
        build()
    elif argv[:1] == ["score"] and len(argv) == 3:
        r = score(Path(argv[1]), Path(argv[2]))
        print(report(r))
        out = Path(argv[2]) / "medic_regression_score.json"
        out.write_text(json.dumps(r, indent=1))
        print(f"\nper-pair detail: {out}")
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
