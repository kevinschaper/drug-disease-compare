"""Deterministic aggregation of the false-positive audit (no network, no LLM).

Reads the archived sample + adjudication verdicts and prints / writes the measured
precision and false-positive rates with Wilson 95% CIs. Re-running this on the committed
artifacts reproduces the published numbers exactly; only the upstream sampling
(fp_audit_sample.py) and the LLM adjudication are non-deterministic, and their outputs are
archived in experiments/out/ so this report is stable.

Independence rule: we only count edges with `label_method != "none"`, i.e. an FDA label we
fetched ourselves and confirmed is the same substance by UNII (or verified generic name).
Edges with no independently-fetched label are EXCLUDED — never judged from a source's own
self-reported snippet. For MEDIC the upstream pool is already restricted to [FDA]-tagged
edges, so EU/Japan-only approvals are not judged against the FDA label.

Run:  uv run python -m experiments.fp_audit_report
"""
from __future__ import annotations

import glob
import json
import math
from collections import Counter
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
SRC_DATA = OUT.parent.parent / "src" / "data"
FP_TYPES = ["FP1_setting", "FP2_symptom_swap", "FP3_cross_section", "FP4_overbroad",
            "FP5_negation", "FP7_notintext", "FP7_confirmed"]
FP_LABEL = {
    "FP7": "not-in-any-label / spurious mapping", "FP4_overbroad": "over-broad / granularity",
    "FP3_cross_section": "cross-section bleed", "FP1_setting": "setting-as-target",
    "FP5_negation": "negation / contraindication", "FP2_symptom_swap": "symptom swap",
}


def wilson(k: int, n: int):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    z = 1.96
    d = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / d
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (round(100 * p, 1), round(100 * (centre - half), 1), round(100 * (centre + half), 1))


def main():
    sample = {r["id"]: r for r in (json.loads(l) for l in open(OUT / "fp_sample.jsonl"))}
    verdict, note = {}, {}
    for f in glob.glob(str(OUT / "verdicts_*.json")):
        if "recheck" in f:
            continue
        for r in json.load(open(f)):
            verdict[r["id"]] = r["verdict"]
            note[r["id"]] = r.get("note", "")
    # multi-SPL recheck overrides the single-label "not in text" calls
    for r in json.load(open(OUT / "verdicts_recheck.json")):
        verdict[r["id"]] = r["verdict"]
        note[r["id"]] = r.get("note", "")
    # second (skeptical) reviewer: ids the verifier overturned from FP -> TARGET
    overturned, review_note = set(), {}
    for f in glob.glob(str(OUT / "verify_*.json")):
        for r in json.load(open(f)):
            review_note[r["id"]] = r.get("note", "")
            if r["verdict"] == "TARGET":
                overturned.add(r["id"])

    results, edges = {}, []
    for src in ("dakp-approved", "medic"):
        judged = [i for i in sample if i.startswith(src)
                  and sample[i]["label_method"] != "none"
                  and verdict.get(i) not in (None, "NO_LABEL", "UNSURE")]
        # consensus verdict: an FP only stands if the second reviewer didn't overturn it
        def consensus(i):
            v = verdict[i]
            return "TARGET" if (v in FP_TYPES and i in overturned) else v
        c = Counter(consensus(i) for i in judged)
        n = len(judged)
        tgt = c["TARGET"]
        fp = sum(c[k] for k in FP_TYPES)
        fp_firstpass = sum(1 for i in judged if verdict[i] in FP_TYPES)
        n_overturned = sum(1 for i in judged if verdict[i] in FP_TYPES and i in overturned)
        for i in sorted(judged):
            r = sample[i]
            edges.append({
                "source": src, "drug": r["drug"], "drug_label": r["drug_label"],
                "disease": r["disease"], "disease_label": r["disease_label"],
                "label_method": r["label_method"], "label_brand": r.get("label_brand", ""),
                "verdict_firstpass": verdict[i], "verdict": consensus(i),
                "overturned": (verdict[i] in FP_TYPES and i in overturned),
                "note": note.get(i, ""), "review_note": review_note.get(i, ""),
            })
        # collapse the two FP7 keys for reporting
        by_type = {}
        for k, v in c.items():
            if k == "TARGET":
                continue
            key = "FP7" if k.startswith("FP7") else k
            by_type[key] = by_type.get(key, 0) + v
        results[src] = {
            "n_judged": n,
            "precision_consensus": wilson(tgt, n), "fp_rate_consensus": wilson(fp, n),
            "fp_rate_firstpass": wilson(fp_firstpass, n), "n_overturned_on_review": n_overturned,
            "by_type_consensus": {k: (v, round(100 * v / n, 1)) for k, v in sorted(by_type.items(), key=lambda x: -x[1])},
        }

    print("# False-positive audit — measured rates\n")
    print("Seeded random sample, UNII-verified FDA label, indications unioned across all SPLs,")
    print("two independent Opus 4.8 adjudications. Wilson 95% CIs. Independent labels only.\n")
    for src, r in results.items():
        pc, pclo, pchi = r["precision_consensus"]
        fc, fclo, fchi = r["fp_rate_consensus"]
        ff, fflo, ffhi = r["fp_rate_firstpass"]
        print(f"## {src}  (n={r['n_judged']} judged)")
        print(f"  FP rate, first pass:        {ff}%  (CI {fflo}-{ffhi})")
        print(f"  FP rate, 2-reviewer consensus: {fc}%  (CI {fclo}-{fchi})   [{r['n_overturned_on_review']} flags overturned on review]")
        print(f"  precision (consensus):      {pc}%  (CI {pclo}-{pchi})")
        for k, (cnt, pct) in r["by_type_consensus"].items():
            print(f"    - {FP_LABEL.get(k, k):32s} {cnt:>3}  ({pct}%)")
        print()
    (OUT / "fp_audit_results.json").write_text(json.dumps(results, indent=2))
    print(f"wrote {OUT / 'fp_audit_results.json'}")
    # per-edge detail for the site (so the actual adjudicated edges are inspectable)
    SRC_DATA.mkdir(parents=True, exist_ok=True)
    (SRC_DATA / "fp_audit.json").write_text(json.dumps({"summary": results, "edges": edges}, indent=2))
    print(f"wrote {SRC_DATA / 'fp_audit.json'} ({len(edges)} edges)")


if __name__ == "__main__":
    main()
