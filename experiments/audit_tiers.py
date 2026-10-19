"""Which MEDIC indication edges are ready to load? Score candidate selection rules.

Joins the audit's reference verdicts (``src/data/fp_audit.json``) to per-pair features of the
latest MeDIC export and to cross-source membership (``src/data/pairs.parquet``), then reports,
for every candidate rule, how many MEDIC pairs it keeps and how often an audited pair it
keeps is wrong. Deterministic; no network / LLM.

Labeled pairs for the latest build = the fresh random sample judged on it, plus every pair
judged on an earlier MEDIC release/build that is still asserted (same canonical pair, same
label evidence) -- those carry over, but they over-represent *kept* pairs, which are cleaner,
so headline rates use the fresh sample and the pooled set only tightens the per-rule
comparison (both are reported).

Features (per canonical pair, from the export):
* regulators asserting it (FDA/EMA/PMDA/CDSCO), assertion count, pair reliability tier
* ``combo_only``  -- every FDA assertion comes from a multi-ingredient DailyMed label
* ``homeopathic`` -- any assertion comes from a homeopathic label
* grounding quality / flags MeDIC itself records on the object and subject
* drug kind: counter-ion, active-metabolite, or an id the Node Normalizer can't resolve
* disease vocabulary of the canonical id (MONDO / HP / UMLS / ...)
Cross-source: DAKP-approved exact, DAKP off-label exact, DAKP related (<=2 MONDO hops),
dismech exact, same-moiety agreement (``n_group``); Jev label-check verdict + confidence.

Writes experiments/out/v2/tiers.json (rule table), src/data/tiers.json (site copy),
src/data/medic_tiers.parquet (tier per MEDIC pair) and
experiments/out/v2/medic_load_tiers.tsv (the same in MeDIC's own subject/object ids).

Run:  PYTHONPATH=pipeline:. uv run python -m experiments.audit_tiers
"""
from __future__ import annotations

import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

from experiments.audit_report import FP, wilson

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "src" / "data"
INP = ROOT / "data" / "inputs"
OUT = Path(__file__).resolve().parent / "out" / "v2"

HOMEOPATHIC = re.compile(r"homeopath|\bHPUS\b", re.I)
ION = re.compile(r"\b(cation|anion|ion|hydroxide|acetate|chloride|sulfate|sulphate|phosphate|"
                 r"carbonate|citrate|bicarbonate|hydrogencarbonate|fluoride)\b$", re.I)
METABOLITE = re.compile(r"prilat$|^4-hydroxycyclophosphamide$", re.I)


def setid_index(setids: set[str]) -> dict:
    """DailyMed set_id -> {n_ingredients, homeopathic} from the openFDA bulk export."""
    idx = {}
    for z in sorted((INP / "labels/openfda").glob("*.zip")):
        with zipfile.ZipFile(z) as zf:
            for member in zf.namelist():
                for lab in json.loads(zf.read(member)).get("results", []):
                    sid = lab.get("set_id")
                    if sid in setids:
                        of = lab.get("openfda") or {}
                        idx[sid] = {"n_ingredients": len(set(of.get("unii") or [])) or len(
                            set(of.get("substance_name") or [])),
                            "homeopathic": bool(HOMEOPATHIC.search(json.dumps(lab)))}
    return idx


def medic_features() -> dict[tuple[str, str], dict]:
    """Canonical (drug, disease) -> export-derived features for MEDIC treats pairs."""
    from drug_edge_compare import cli
    from drug_edge_compare.mondo import MondoGraph
    from drug_edge_compare.nodenorm import NodeNorm

    raw = [json.loads(line) for line in open(INP / "medic/new/medic_edges.jsonl")]
    treats = [e for e in raw if e["predicate"] == "biolink:treats"]
    nodes = {}
    for line in open(INP / "medic/new/medic_nodes.jsonl"):
        n = json.loads(line)
        nodes[n["id"]] = n
    nn = NodeNorm(cli.CACHE)
    mondo = MondoGraph(cli.INPUTS / "mondo_edges.tsv", cli.INPUTS / "mondo_nodes.tsv")
    rec, _ = cli._reconciler(nn, mondo, cli._load_source("medic"))
    sidx = setid_index({e["medic_setid"] for e in treats if e.get("medic_setid")})

    feats: dict[tuple[str, str], dict] = {}
    for e in treats:
        d, s = rec.drug(e["subject"]), rec.disease(e["object"])
        k = (d.canonical, s.canonical)
        f = feats.setdefault(k, {
            "raw": set(), "regulators": set(), "n_assertions": 0, "reliability": "",
            "fda_assertions": 0, "fda_combo": 0, "homeopathic": False,
            "obj_quality": set(), "subj_quality": set(), "obj_flags": set(), "assertion_flags": set(),
            "negation_detected": False, "diagnostic": False, "drug_names": set(),
            "drug_unresolved": not nn.clique(e["subject"]).resolved,
            "pair_confidence": 0.0})
        f["raw"].add((e["subject"], e["object"]))
        f["regulators"].add(e.get("medic_authority") or "")
        f["n_assertions"] += 1
        f["pair_confidence"] = max(f["pair_confidence"], e.get("medic_pair_confidence") or 0)
        rank = {"EXCLUDED": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3}
        r = e.get("medic_pair_reliability") or ""
        if rank.get(r, -1) > rank.get(f["reliability"], -1):
            f["reliability"] = r
        if e.get("medic_setid"):
            f["fda_assertions"] += 1
            lab = sidx.get(e["medic_setid"], {})
            f["fda_combo"] += lab.get("n_ingredients", 1) > 1
            f["homeopathic"] |= lab.get("homeopathic", False)
        f["obj_quality"].add(e.get("medic_object_grounding_quality") or "")
        f["subj_quality"].add(e.get("medic_subject_grounding_quality") or "")
        f["obj_flags"].update(e.get("medic_object_grounding_flags") or [])
        f["assertion_flags"].update(e.get("medic_assertion_flags") or [])
        f["negation_detected"] |= bool(e.get("medic_negation_detected"))
        f["diagnostic"] |= bool(e.get("medic_is_diagnostic_agent"))
        f["drug_names"].add(nodes.get(e["subject"], {}).get("name", ""))
    for f in feats.values():
        f["combo_only"] = f["fda_assertions"] > 0 and f["fda_combo"] == f["fda_assertions"]
        f["any_combo"] = f["fda_combo"] > 0
        f["n_regulators"] = len(f["regulators"] - {""})
        f["drug_ion"] = any(ION.search(n) and len(n.split()) <= 3 for n in f["drug_names"])
        f["drug_metabolite"] = any(METABOLITE.search(n) for n in f["drug_names"])
    return feats


def mondo_rare() -> set[str]:
    """MONDO ids in the `rare` subset or carrying an Orphanet xref (release KGX nodes)."""
    m = pd.read_csv(INP / "mondo_nodes.tsv", sep="\t", usecols=["id", "subsets", "xref"], dtype=str).fillna("")
    m = m[m.id.str.startswith("MONDO:")]
    return set(m[m.subsets.str.contains("rare", case=False) | m.xref.str.contains("Orphanet:")].id)


def main() -> None:
    audit = json.load(open(SITE / "fp_audit.json"))
    rare = mondo_rare()
    pairs = pd.read_parquet(SITE / "pairs.parquet")
    mp = pairs[pairs.medic == "exact"].set_index(["drug", "disease"])
    lc = pd.read_parquet(SITE / "label_check.parquet")
    jev = {(r.drug, r.disease): (r.verdict, r.confidence) for r in lc[lc.source == "medic"].itertuples()}
    feats = medic_features()

    # one row per MEDIC pair with every feature + cross-source membership
    rows = []
    for (drug, dis), p in mp.iterrows():
        f = feats.get((drug, dis))
        if not f:
            continue
        jv, jc = jev.get((drug, dis), ("", 0.0))
        rows.append({
            "drug": drug, "disease": dis, "drug_label": p.drug_label, "disease_label": p.disease_label,
            "disease_vocab": dis.split(":")[0],
            # monarch-kg is disease-centric: a MONDO disease (rare or not) vs an HP phenotype
            # (mostly OTC symptom-relief claims) vs a UMLS/other term (often an unnamed stub)
            "axis": ("MONDO rare" if dis in rare else "MONDO other" if dis.startswith("MONDO:")
                     else "HP phenotype" if dis.startswith("HP:") else "UMLS/other"),
            "regulators": "+".join(sorted(f["regulators"] - {""})), "n_regulators": f["n_regulators"],
            "fda": "FDA" in f["regulators"], "ema": "EMA" in f["regulators"],
            "n_assertions": f["n_assertions"], "reliability": f["reliability"],
            "pair_confidence": f["pair_confidence"],
            "combo_only": f["combo_only"], "any_combo": f["any_combo"], "homeopathic": f["homeopathic"],
            "obj_lexical_exact": f["obj_quality"] <= {"lexical_exact"},
            "obj_flagged": bool(f["obj_flags"]), "assertion_flagged": bool(f["assertion_flags"]),
            "negation_detected": f["negation_detected"], "diagnostic": f["diagnostic"],
            "drug_ion": f["drug_ion"], "drug_metabolite": f["drug_metabolite"],
            "drug_unresolved": f["drug_unresolved"],
            "dakp_approved": p.dakp == "exact" and p.dakp_status == "approved_for_condition",
            "dakp_offlabel": p.dakp == "exact" and p.dakp_status != "approved_for_condition",
            "dakp_related": p.dakp == "related",
            "dismech_exact": p.dismech == "exact", "dismech_related": p.dismech == "related",
            "moiety_agree": int(p.n_group or 0) >= 2,
            "jev": jv, "jev_conf": float(jc),
            "jev_confident_target": jv == "TARGET" and jc >= 0.9,
            "jev_confident_flag": jv in FP and jc >= 0.9,
        })
    P = pd.DataFrame(rows).set_index(["drug", "disease"])
    P["any_agreement"] = P.dakp_approved | P.dakp_offlabel | P.dismech_exact | P.moiety_agree
    P["any_support"] = P.any_agreement | P.dakp_related | P.dismech_related
    P["multi_regulator"] = P.n_regulators >= 2
    P["suspect_drug"] = P.drug_ion | P.drug_metabolite | P.homeopathic
    P["suspect"] = P.suspect_drug | P.combo_only | P.negation_detected | P.diagnostic | (P.reliability.isin(["LOW", "EXCLUDED"]))

    # labeled pairs of the latest build: fresh sample + carry-overs still asserted
    lab = defaultdict(dict)
    for e in audit["edges"]:
        if e["source"] != "medic" or e["verdict"] not in FP and e["verdict"] != "TARGET":
            continue
        k = (e["drug"], e["disease"])
        if k not in P.index:
            continue
        lab[k][e["release"]] = e["verdict"]
    L = []
    for k, vs in lab.items():
        v = vs.get("new") or vs.get("b1001") or vs.get("old")
        L.append({"drug": k[0], "disease": k[1], "fp": v in FP, "verdict": v,
                  "fresh": "new" in vs, "agree_across_rounds": len(set(vs.values())) == 1 if len(vs) > 1 else None})
    L = pd.DataFrame(L).set_index(["drug", "disease"])
    L = L.join(P, how="inner")

    def score(mask_pop, mask_lab):
        n_pop = int(mask_pop.sum())
        fresh = L[mask_lab & L.fresh]
        pooled = L[mask_lab]
        return {"pairs": n_pop, "share": round(100 * n_pop / len(P), 1),
                "fresh_n": int(len(fresh)), "fresh_fp": wilson(int(fresh.fp.sum()), len(fresh)),
                "pooled_n": int(len(pooled)), "pooled_fp": wilson(int(pooled.fp.sum()), len(pooled))}

    RULES = {
        "all MEDIC indication pairs": lambda d: d.index == d.index,
        # --- cross-source agreement ---
        "exact in DAKP-approved": lambda d: d.dakp_approved,
        "exact in DAKP (approved or off-label)": lambda d: d.dakp_approved | d.dakp_offlabel,
        "exact in dismech": lambda d: d.dismech_exact,
        "same-moiety agreement with any source": lambda d: d.moiety_agree,
        "any exact/moiety agreement": lambda d: d.any_agreement,
        "any agreement incl. related (<=2 MONDO hops)": lambda d: d.any_support,
        "no agreement of any kind": lambda d: ~d.any_support,
        # --- internal corroboration ---
        ">=2 regulators": lambda d: d.multi_regulator,
        "FDA + EMA both": lambda d: d.fda & d.ema,
        "single regulator": lambda d: ~d.multi_regulator,
        "reliability HIGH": lambda d: d.reliability == "HIGH",
        "reliability MEDIUM": lambda d: d.reliability == "MEDIUM",
        "reliability LOW/EXCLUDED": lambda d: d.reliability.isin(["LOW", "EXCLUDED"]),
        "object grounding lexical_exact only": lambda d: d.obj_lexical_exact,
        "object grounding not lexical_exact": lambda d: ~d.obj_lexical_exact,
        "MeDIC flags on object/assertion": lambda d: d.obj_flagged | d.assertion_flagged,
        # --- known failure mechanisms ---
        "combination-label-only support": lambda d: d.combo_only,
        "any combination-label support": lambda d: d.any_combo,
        "no combination-label support": lambda d: ~d.any_combo,
        "homeopathic label": lambda d: d.homeopathic,
        "drug is a counter-ion / electrolyte": lambda d: d.drug_ion,
        "drug is an active metabolite": lambda d: d.drug_metabolite,
        "drug id unknown to Node Normalizer": lambda d: d.drug_unresolved,
        "negation detected by MeDIC": lambda d: d.negation_detected,
        "disease id is MONDO": lambda d: d.disease_vocab == "MONDO",
        "disease id is HP": lambda d: d.disease_vocab == "HP",
        "disease id is UMLS/other": lambda d: ~d.disease_vocab.isin(["MONDO", "HP"]),
        # --- disease axis (monarch-kg is disease-centric) ---
        "disease axis: MONDO rare disease": lambda d: d.axis == "MONDO rare",
        "disease axis: MONDO other disease": lambda d: d.axis == "MONDO other",
        "disease axis: HP phenotype (symptom-relief claims)": lambda d: d.axis == "HP phenotype",
        "disease axis: UMLS/other": lambda d: d.axis == "UMLS/other",
        "T1 restricted to MONDO diseases": lambda d: d.jev_confident_target & ~d.suspect & d.axis.str.startswith("MONDO"),
        "T1 restricted to MONDO rare diseases": lambda d: d.jev_confident_target & ~d.suspect & (d.axis == "MONDO rare"),
        "rare disease, unscreened (no FDA/EMA text; mostly PMDA)": lambda d: (d.axis == "MONDO rare") & (d.jev == "") & ~d.suspect,
        "rare disease, unscreened but corroborated": lambda d: (d.axis == "MONDO rare") & (d.jev == "") & ~d.suspect & (d.any_agreement | d.multi_regulator),
        # --- label check ---
        "Jev confident TARGET (>=0.9)": lambda d: d.jev_confident_target,
        "Jev confident flag (>=0.9)": lambda d: d.jev_confident_flag,
        "Jev not confident / not screened": lambda d: ~(d.jev_confident_target | d.jev_confident_flag),
        # --- agreement-first tiers (the first design; kept for comparison) ---
        "agreement-first A: any exact/moiety agreement, not suspect": lambda d: d.any_agreement & ~d.suspect,
        "agreement-first B: no agreement; >=2 regulators or Jev confident TARGET; not suspect":
            lambda d: ~d.any_agreement & (d.multi_regulator | d.jev_confident_target) & ~d.suspect,
        "agreement-first C: single regulator, no agreement, no Jev support, not suspect":
            lambda d: ~d.any_agreement & ~d.multi_regulator & ~d.jev_confident_target & ~d.suspect,
        # --- label-check-first tiers (the recommended design) ---
        "T1 label-confirmed: Jev confident TARGET, not suspect": lambda d: d.jev_confident_target & ~d.suspect,
        "T2 corroborated, label check inconclusive (screened <0.9; agreement or >=2 regulators)":
            lambda d: (d.jev != "") & ~d.jev_confident_target & ~d.jev_confident_flag & (d.any_agreement | d.multi_regulator) & ~d.suspect,
        "T3 unscreened: no FDA/EMA label text held for the drug (mostly PMDA/CDSCO-only), so no label check possible":
            lambda d: (d.jev == "") & ~d.suspect,
        "T3 split: unscreened but corroborated (agreement or >=2 regulators)": lambda d: (d.jev == "") & ~d.suspect & (d.any_agreement | d.multi_regulator),
        "T3 split: unscreened, single-source": lambda d: (d.jev == "") & ~d.suspect & ~(d.any_agreement | d.multi_regulator),
        "T4 unconfirmed single-source (screened <0.9; no agreement, one regulator)":
            lambda d: (d.jev != "") & ~d.jev_confident_target & ~d.jev_confident_flag & ~d.any_agreement & ~d.multi_regulator & ~d.suspect,
        "T5 flagged/suspect: Jev confident flag, or combo-only / homeopathic / ion / metabolite / negation / diagnostic / LOW":
            lambda d: d.jev_confident_flag | d.suspect,
        "T1 + T2": lambda d: (d.jev_confident_target | ((d.jev != "") & (d.any_agreement | d.multi_regulator) & ~d.jev_confident_flag)) & ~d.suspect,
        "T1 + T3-corroborated (a load set that includes unscreened PMDA/CDSCO pairs with agreement)":
            lambda d: (d.jev_confident_target | ((d.jev == "") & (d.any_agreement | d.multi_regulator))) & ~d.suspect,
        "T2 split: agreement only (one regulator)": lambda d: (d.jev != "") & ~d.jev_confident_target & ~d.jev_confident_flag & d.any_agreement & ~d.multi_regulator & ~d.suspect,
        "T2 split: >=2 regulators only (no agreement)": lambda d: (d.jev != "") & ~d.jev_confident_target & ~d.jev_confident_flag & ~d.any_agreement & d.multi_regulator & ~d.suspect,
        "T2 split: agreement and >=2 regulators": lambda d: (d.jev != "") & ~d.jev_confident_target & ~d.jev_confident_flag & d.any_agreement & d.multi_regulator & ~d.suspect,
    }
    table = {name: score(rule(P), rule(L)) for name, rule in RULES.items()}

    # tier assignment per pair
    def tier(d):
        if d.jev_confident_flag or d.suspect:
            return "T5 flagged/suspect"
        if d.jev_confident_target:
            return "T1 label-confirmed"
        if d.jev == "":
            return "T3 unscreened (no FDA/EMA text held)"
        if d.any_agreement or d.multi_regulator:
            return "T2 corroborated, label check inconclusive"
        return "T4 unconfirmed single-source"
    P["tier"] = P.apply(tier, axis=1)
    P["jev_flag"] = P.jev_confident_flag

    def why(d):
        r = []
        if d.dakp_approved: r.append("DAKP-approved")
        if d.dakp_offlabel: r.append("DAKP off-label")
        if d.dismech_exact: r.append("dismech")
        if d.moiety_agree and not (d.dakp_approved or d.dakp_offlabel or d.dismech_exact): r.append("same-moiety match")
        if d.multi_regulator: r.append(f"{d.n_regulators} regulators")
        if d.jev_confident_target: r.append("label check: target")
        if d.jev_confident_flag: r.append(f"label check: {d.jev}")
        for k, lbl in (("combo_only", "combination-label only"), ("homeopathic", "homeopathic label"),
                       ("drug_ion", "counter-ion drug"), ("drug_metabolite", "metabolite drug"),
                       ("negation_detected", "negation"), ("diagnostic", "diagnostic agent")):
            if d[k]: r.append(lbl)
        if d.reliability in ("LOW", "EXCLUDED"): r.append(f"reliability {d.reliability}")
        return "; ".join(r)
    P["why"] = P.apply(why, axis=1)

    L["tier"] = P.loc[L.index, "tier"]
    tiers = {t: score(P.tier == t, L.tier == t) for t in sorted(P.tier.unique())}
    # carry-over consistency: pairs judged in two rounds
    both = L[L.agree_across_rounds.notna()]
    consistency = {"pairs_judged_twice": int(len(both)),
                   "same_verdict": int(both.agree_across_rounds.sum())}
    L["axis"] = P.loc[L.index, "axis"]
    axis_order = ["MONDO rare", "MONDO other", "HP phenotype", "UMLS/other"]
    by_axis = {t: {a: {"pairs": int(((P.tier == t) & (P.axis == a)).sum()),
                       "pooled_n": int(((L.tier == t) & (L.axis == a)).sum()),
                       "pooled_fp": wilson(int(L[(L.tier == t) & (L.axis == a)].fp.sum()), int(((L.tier == t) & (L.axis == a)).sum()))}
                   for a in axis_order} for t in sorted(P.tier.unique())}
    axis_tot = {a: {"pairs": int((P.axis == a).sum()), "diseases": int(P[P.axis == a].index.get_level_values("disease").nunique()),
                    "fresh_n": int((L.fresh & (L.axis == a)).sum()), "fresh_fp": wilson(int(L[L.fresh & (L.axis == a)].fp.sum()), int((L.fresh & (L.axis == a)).sum())),
                    "pooled_n": int((L.axis == a).sum()), "pooled_fp": wilson(int(L[L.axis == a].fp.sum()), int((L.axis == a).sum()))}
                for a in axis_order}
    t1r = P[(P.tier == "T1 label-confirmed") & (P.axis == "MONDO rare")]
    summary = {"medic_pairs": int(len(P)), "labeled_fresh": int(L.fresh.sum()), "labeled_pooled": int(len(L)),
               "by_axis": axis_tot, "tier_by_axis": by_axis,
               "t1_rare": {"pairs": int(len(t1r)), "diseases": int(t1r.index.get_level_values("disease").nunique()), "drugs": int(t1r.index.get_level_values("drug").nunique())},
               "rare_diseases_covered": int(P[P.axis == "MONDO rare"].index.get_level_values("disease").nunique()),
               "rules": table, "tiers": tiers, "consistency": consistency,
               "tier_by_regulator": {t: {k: int(v) for k, v in P[P.tier == t].regulators.value_counts().head(8).items()}
                                     for t in tiers},
               "tier_jev_flagged": {t: int((P[P.tier == t].jev_flag).sum()) for t in tiers}}
    (OUT / "tiers.json").write_text(json.dumps(summary, indent=2))
    (SITE / "tiers.json").write_text(json.dumps(summary, indent=1))
    keep = ["drug_label", "disease_label", "tier", "why", "axis", "regulators", "reliability", "disease_vocab",
            "combo_only", "any_combo", "homeopathic", "drug_ion", "drug_metabolite", "drug_unresolved", "jev_flag",
            "dakp_approved", "dakp_offlabel", "dismech_exact", "moiety_agree", "n_regulators",
            "jev", "jev_conf"]
    P.reset_index()[["drug", "disease"] + keep].to_parquet(SITE / "medic_tiers.parquet", index=False, compression="zstd")
    # the same in MeDIC's own ids, one row per raw (subject, object)
    raw_rows = []
    for (drug, dis), d in P.iterrows():
        for s, o in sorted(feats[(drug, dis)]["raw"]):
            raw_rows.append({"medic_subject": s, "medic_object": o, "canonical_drug": drug, "canonical_disease": dis,
                             **{k: d[k] for k in keep}})
    pd.DataFrame(raw_rows).to_csv(OUT / "medic_load_tiers.tsv", sep="\t", index=False)
    for name, s in table.items():
        print(f"{name:75s} {s['pairs']:6d} ({s['share']:5.1f}%)  fresh {s['fresh_fp'][0]:5.1f}% n={s['fresh_n']:3d}  pooled {s['pooled_fp'][0]:5.1f}% n={s['pooled_n']:3d}")
    print(json.dumps({"tiers": tiers, "consistency": consistency}, indent=1))


if __name__ == "__main__":
    main()
