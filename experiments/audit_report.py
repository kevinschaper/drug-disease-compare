"""Indication audit (v2) report: deterministic aggregation, no network / LLM.

Inputs (experiments/out/v2/): sample.jsonl, blind_key.json, claude_a_*.json and
claude_b_*.json (two independent, blind Claude adjudications with different batchings; B is
instructed to be adversarial), tiebreak_*.json (a third Claude pass on every A<->B
disagreement), jev_sample.jsonl, jev_population.jsonl (Jev over every eligible edge).

**The reference is Jev-free**: A and B agree -> that verdict; otherwise the tie-breaker's.
Jev is then *scored* against it, so its validation can't be circular. Acceptance criteria,
fixed before looking at results: Jev's binary (TARGET vs FP) agreement with the reference is
within 5 points of the Claude A<->B agreement (the inter-rater ceiling), and its binary
Cohen's kappa is >= 0.6. If it fails, the population screen is reported only for Jev's
high-confidence subset (or not at all) -- see ``jev_accepted``.
Absence rule: an FP7 ("not in the label") only counts where we hold text for every regulator
the edge cites (``absence_ok``); elsewhere it is "unverifiable" and leaves the denominator,
as do UNSURE calls.

Releases: every number under ``sources`` is the latest release (300 edges/source); the
previous releases were sampled and judged with the identical protocol (``previous_release``)
and ``change`` gives latest minus previous with Newcombe 95% CIs. Jev is validated against
the reference on all edges of both releases.

Population estimate: Jev's verdict on all eligible edges, corrected with its measured error
on the gold sample: FP_hat = P(Jev=FP)*PPV + P(Jev=TARGET)*(1-NPV), PPV/NPV from the gold
sample, 95% CI by bootstrap over gold edges.

Run:  uv run python -m experiments.audit_report
"""
from __future__ import annotations

import glob
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out" / "v2"
V1 = Path(__file__).resolve().parent / "out" / "fp_audit_results.json"
SITE = OUT.parent.parent.parent / "src" / "data"
SOURCES = ("medic", "dakp-approved")
FP = ("FP1_setting", "FP2_symptom_swap", "FP3_cross_section", "FP4_overbroad",
      "FP5_negation", "FP6_coingredient", "FP7_notintext")
LABEL = {"FP1_setting": "setting-as-target", "FP2_symptom_swap": "symptom swap",
         "FP3_cross_section": "cross-section bleed", "FP4_overbroad": "over-broad / granularity",
         "FP5_negation": "negation", "FP6_coingredient": "co-ingredient's indication",
         "FP7_notintext": "not in label / spurious mapping"}


def wilson(k: int, n: int):
    if n == 0:
        return [0.0, 0.0, 0.0]
    p, z = k / n, 1.96
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return [round(100 * p, 1), round(100 * (c - h), 1), round(100 * (c + h), 1)]


def kappa(pairs: list[tuple[str, str]]) -> float:
    n = len(pairs)
    if not n:
        return 0.0
    po = sum(a == b for a, b in pairs) / n
    ca, cb = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    pe = sum(ca[k] * cb[k] for k in ca) / (n * n)
    return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0


def binary(v: str) -> str:
    return "FP" if v in FP else ("TARGET" if v == "TARGET" else "other")


def load_json_list(pattern: str) -> dict:
    out = {}
    for f in sorted(glob.glob(str(OUT / pattern))):
        for r in json.load(open(f)):
            out[r["id"]] = r
    return out


def newcombe(k1: int, n1: int, k2: int, n2: int):
    """Difference p2 - p1 in percentage points, with Newcombe's hybrid-score 95% CI."""
    if not n1 or not n2:
        return [0.0, 0.0, 0.0]
    p1, l1, u1 = (x / 100 for x in wilson(k1, n1))
    p2, l2, u2 = (x / 100 for x in wilson(k2, n2))
    d = p2 - p1
    lo = d - math.sqrt((p2 - l2) ** 2 + (u1 - p1) ** 2)
    hi = d + math.sqrt((u2 - p2) ** 2 + (p1 - l1) ** 2)
    return [round(100 * d, 1), round(100 * lo, 1), round(100 * hi, 1)]


def _source_result(E: list[dict], src: str) -> dict:
    """FP rate, type mix and slices for one source's adjudicated edges."""
    judged = [e for e in E if e["verdict"] in FP or e["verdict"] == "TARGET"]
    n, k = len(judged), sum(e["verdict"] in FP for e in judged)
    by_type = Counter(e["verdict"] for e in judged if e["verdict"] in FP)
    res = {
        "sampled": len(E), "judged": n, "fp": k,
        "excluded": dict(Counter(e["verdict"] for e in E if e not in judged)),
        "fp_rate": wilson(k, n), "precision": wilson(n - k, n),
        "by_type": {t: [by_type[t], round(100 * by_type[t] / n, 1) if n else 0] for t in FP if by_type[t]},
        "by_regulator": {},
    }
    for lab, pred in (("FDA only", lambda e: e["judged_against"] == ["FDA"]),
                      ("EMA only", lambda e: e["judged_against"] == ["EMA"]),
                      ("FDA + EMA", lambda e: e["judged_against"] == ["EMA", "FDA"])):
        S = [e for e in judged if pred(e)]
        if S:
            res["by_regulator"][lab] = {"n": len(S), "fp_rate": wilson(sum(e["verdict"] in FP for e in S), len(S))}
    # error rates by the disease vocabulary the edge uses (MONDO / HP / UMLS / NCIT ...)
    res["by_disease_vocab"] = {}
    for pre, grp in sorted(Counter(e["disease_prefix"] for e in judged).items(), key=lambda x: -x[1]):
        S = [e for e in judged if e["disease_prefix"] == pre]
        if len(S) >= 10:
            res["by_disease_vocab"][pre] = {
                "n": len(S), "fp_rate": wilson(sum(e["verdict"] in FP for e in S), len(S)),
                "not_in_label": wilson(sum(e["verdict"] == "FP7_notintext" for e in S), len(S))}
    if src == "medic":
        res["by_reliability"] = {}
        for tier in ("HIGH", "MEDIUM", "LOW"):
            S = [e for e in judged if e["medic_reliability"] == tier]
            if S:
                res["by_reliability"][tier] = {"n": len(S), "fp_rate": wilson(sum(e["verdict"] in FP for e in S), len(S))}
    return res


def main() -> None:
    # latest-release sample (300/source) + previous-release sample (300/source); two review
    # rounds (round 1: the first 150 latest edges per source; round 2: everything else,
    # shuffled together across releases so reviewers never saw source or release)
    sample = {}
    for fname, rel in (("sample.jsonl", "new"), ("sample_old.jsonl", "old")):
        if (OUT / fname).exists():
            for line in open(OUT / fname):
                r = json.loads(line)
                r["release"] = rel
                sample[r["sid"]] = r
    key = json.load(open(OUT / "blind_key.json"))           # blind id -> sid
    if (OUT / "blind_key_2.json").exists():
        key.update(json.load(open(OUT / "blind_key_2.json")))

    def by_sid(*patterns):
        out = {}
        for pat in patterns:
            out.update({key[i]: r for i, r in load_json_list(pat).items()})
        return out

    claude = by_sid("claude_a_*.json", "claude2_a_*.json")
    claude_b = by_sid("claude_b_*.json", "claude2_b_*.json")
    tiebreak = by_sid("tiebreak_[0-9]*.json", "tiebreak2_[0-9].json")
    # co-ingredient check: every reference TARGET whose evidence included combination labels
    # was re-judged with single-ingredient and combination text separated (rubric FP6)
    combo = by_sid("combo_check_*.json", "combo2_check_*.json")
    jev_by_pid = {r["id"]: r for r in (json.loads(line) for line in open(OUT / "jev_sample.jsonl"))}
    jev = {sid: jev_by_pid[r["id"]] for sid, r in sample.items() if r["id"] in jev_by_pid}

    edges = []
    for sid, r in sample.items():
        c, b, j = claude.get(sid), claude_b.get(sid), jev.get(sid)
        if not c or not b or not j:
            continue
        if c["verdict"] == b["verdict"]:
            cons, how = c["verdict"], "agree"
        elif sid in tiebreak:
            cons, how = tiebreak[sid]["verdict"], "tiebreak"
        else:
            cons, how = c["verdict"], "unresolved (no tiebreak yet)"
        if cons == "TARGET" and combo.get(sid, {}).get("verdict") == "FP6_coingredient":
            cons, how = "FP6_coingredient", how + "+coingredient-check"
        final = cons
        if cons == "FP7_notintext" and not r["absence_ok"]:
            final = "UNVERIFIABLE"
        edges.append({
            "sid": sid, "release": r["release"], "source": r["source"], "drug": r["drug"], "drug_label": r["drug_label"],
            "disease": r["disease"], "disease_label": r["disease_label"],
            "disease_prefix": r.get("disease_prefix", r["disease"].split(":", 1)[0]),
            "cited": r["cited"], "judged_against": r["judge_against"], "fda_method": r["fda_method"],
            "medic_reliability": r.get("medic_reliability") or "",
            "claude": c["verdict"], "claude_b": b["verdict"],
            "jev": j["verdict"], "jev_confidence": j["confidence"],
            "jev_indicated": j["indicated"], "jev_mentioned": j["mentioned"],
            "tiebreak": tiebreak.get(sid, {}).get("verdict", ""), "how": how,
            "verdict": final,
            "quote": (src_of := (combo[sid] if "coingredient-check" in how
                                 else tiebreak.get(sid) or c)).get("quote", ""),
            "note": src_of.get("note", ""),
        })

    # --- per-source measured rates (gold sample, consensus) ---
    def source_results(release):
        return {src: _source_result([e for e in edges if e["source"] == src
                                     and e["release"] == release], src)
                for src in SOURCES}

    results = source_results("new")
    previous = source_results("old")
    change = {src: {
        "fp_rate_pts": newcombe(previous[src]["fp"], previous[src]["judged"],
                                results[src]["fp"], results[src]["judged"]),
        "by_type_pts": {t: newcombe(previous[src]["by_type"].get(t, [0])[0], previous[src]["judged"],
                                    results[src]["by_type"].get(t, [0])[0], results[src]["judged"])
                        for t in FP if t in results[src]["by_type"] or t in previous[src]["by_type"]},
    } for src in SOURCES if previous[src]["judged"]}


    # --- inter-rater ceiling (Claude A<->B), then Jev scored against the reference ---
    both = [e for e in edges]
    ab8 = [(e["claude"], e["claude_b"]) for e in both]
    abbin = [(binary(e["claude"]), binary(e["claude_b"])) for e in both]
    gold = [e for e in both if e["verdict"] in FP or e["verdict"] == "TARGET"]
    cats8 = [(e["verdict"], e["jev"]) for e in gold]
    bin_ = [(binary(e["verdict"]), binary(e["jev"])) for e in gold]
    abbin_gold = [(binary(e["claude"]), binary(e["claude_b"])) for e in gold]
    per_class = {}
    for t in ("TARGET",) + FP:
        ref = [e for e in gold if e["verdict"] == t]
        if ref:
            per_class[t] = {"n": len(ref), "jev_exact": round(sum(e["jev"] == t for e in ref) / len(ref), 3),
                            "jev_binary": round(sum(binary(e["jev"]) == binary(t) for e in ref) / len(ref), 3)}
    conf = defaultdict(lambda: [0, 0])
    for e in gold:
        b = min(int(e["jev_confidence"] * 5), 4)  # 5 bins of width 0.2
        conf[b][0] += binary(e["jev"]) == binary(e["verdict"])
        conf[b][1] += 1
    confusion = Counter((binary(e["verdict"]), binary(e["jev"])) for e in gold)
    decomposed = [("TARGET" if e["jev_indicated"] >= 0.5 else "FP", binary(e["verdict"])) for e in gold]
    def frac(pairs):
        return round(sum(a == b for a, b in pairs) / len(pairs), 3) if pairs else 0
    ceiling = frac(abbin_gold)
    jev_bin = frac(bin_)
    agreement = {
        "n": len(both), "n_reference": len(gold),
        "claude_ab_exact_8way": frac(ab8), "claude_ab_kappa_8way": kappa(ab8),
        "claude_ab_binary": frac(abbin), "claude_ab_kappa_binary": kappa(abbin),
        "tiebroken": sum(e["how"] == "tiebreak" for e in both),
        "jev_exact_8way": frac(cats8), "jev_kappa_8way": kappa(cats8),
        "jev_binary": jev_bin, "jev_kappa_binary": kappa(bin_),
        "jev_per_class": per_class,
        "claude_a_vs_reference_binary": frac([(binary(e["claude"]), binary(e["verdict"])) for e in gold]),
        "claude_b_vs_reference_binary": frac([(binary(e["claude_b"]), binary(e["verdict"])) for e in gold]),
        "acceptance": {"ceiling_binary": ceiling, "jev_binary": jev_bin,
                       "within_5pts": jev_bin >= ceiling - 0.05,
                       "kappa_ok": kappa(bin_) >= 0.6},
        "decomposed_noul_vs_reference": round(sum(a == b for a, b in decomposed) / len(decomposed), 3) if decomposed else 0,
        "jev_calibration": [{"conf_bin": f"{b/5:.1f}-{(b+1)/5:.1f}", "n": v[1],
                             "acc": round(v[0] / v[1], 3)} for b, v in sorted(conf.items())],
        "confusion_binary": {f"{t}|jev:{p}": n for (t, p), n in sorted(confusion.items())},
    }
    agreement["jev_accepted"] = agreement["acceptance"]["within_5pts"] and agreement["acceptance"]["kappa_ok"]
    agreement["jev_high_confidence"] = {}
    for th in (0.6, 0.8, 0.9):
        H = [e for e in gold if e["jev_confidence"] >= th]
        agreement["jev_high_confidence"][str(th)] = {
            "coverage": round(len(H) / len(gold), 3) if gold else 0,
            "binary_acc": frac([(binary(e["verdict"]), binary(e["jev"])) for e in H]),
            # of Jev's confident error flags / target calls, the share the reference agrees with
            "flag_precision": frac([("FP", binary(e["verdict"])) for e in H if binary(e["jev"]) == "FP"]),
            "target_precision": frac([("TARGET", binary(e["verdict"])) for e in H if binary(e["jev"]) == "TARGET"])}

    # --- population screen, corrected by the gold sample ---
    population = {}
    pop_rows = []
    pfile = OUT / "jev_population.jsonl"
    if pfile.exists():
        meta = {r["id"]: r for r in (json.loads(line) for line in open(OUT / "population.jsonl"))}
        jp = [json.loads(line) for line in open(pfile)]
        for r in jp:
            m = meta.get(r["id"])
            if not m:
                continue
            v = r["verdict"]
            if v == "FP7_notintext" and not m["absence_ok"]:
                v = "UNVERIFIABLE"
            pop_rows.append({"source": m["source"], "drug": m["drug"], "disease": m["disease"],
                             "verdict": v, "confidence": r["confidence"],
                             "indicated": r["indicated"], "medic_reliability": m.get("medic_reliability") or ""})
        rng = random.Random(1)
        for src in SOURCES:
            P = [p for p in pop_rows if p["source"] == src and binary(p["verdict"]) != "other"]
            G = [e for e in gold if e["source"] == src and e["release"] == "new"]

            def est(G):
                jfp = [e for e in G if binary(e["jev"]) == "FP"]
                jt = [e for e in G if binary(e["jev"]) == "TARGET"]
                ppv = sum(e["verdict"] in FP for e in jfp) / len(jfp) if jfp else 0
                fnr = sum(e["verdict"] in FP for e in jt) / len(jt) if jt else 0
                share = sum(binary(p["verdict"]) == "FP" for p in P) / len(P) if P else 0
                return share * ppv + (1 - share) * fnr

            point = est(G)
            boots = sorted(est([rng.choice(G) for _ in G]) for _ in range(2000)) if G else [0]
            population[src] = {
                "screened": len([p for p in pop_rows if p["source"] == src]),
                "judged": len(P),
                "jev_fp_share": round(100 * sum(binary(p["verdict"]) == "FP" for p in P) / len(P), 1) if P else 0,
                "corrected_fp_rate": [round(100 * point, 1), round(100 * boots[50], 1), round(100 * boots[1949], 1)],
                "jev_by_type": dict(Counter(p["verdict"] for p in P if p["verdict"] in FP).most_common()),
            }
            if src == "medic":
                population[src]["jev_fp_share_by_reliability"] = {
                    t: round(100 * sum(binary(p["verdict"]) == "FP" for p in P if p["medic_reliability"] == t)
                             / max(1, sum(p["medic_reliability"] == t for p in P)), 1)
                    for t in ("HIGH", "MEDIUM", "LOW")}

    v1 = json.load(open(V1)) if V1.exists() else {}
    summary = {"sources": results, "agreement": agreement, "population": population,
               # like-for-like: the previous releases judged with this exact protocol
               "previous_release": previous, "change": change,
               # the earlier (v1, FDA-only, different protocol) audit, for reference only
               "v1_audit": {s: {"n": v1[s]["n_judged"], "fp_rate": v1[s]["fp_rate_consensus"]}
                            for s in v1}}
    (OUT / "audit_results.json").write_text(json.dumps(summary, indent=2))
    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "fp_audit.json").write_text(json.dumps({"summary": summary, "edges": edges}, indent=1))
    if pop_rows:
        import pandas as pd
        pd.DataFrame(pop_rows).to_parquet(SITE / "label_check.parquet", index=False, compression="zstd")

    print(json.dumps({s: {k: results[s][k] for k in ("sampled", "judged", "fp_rate", "by_type")} for s in results}, indent=1))
    print(json.dumps(agreement, indent=1))
    print(json.dumps(population, indent=1))


if __name__ == "__main__":
    main()
