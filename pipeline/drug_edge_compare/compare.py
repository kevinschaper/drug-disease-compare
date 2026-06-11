"""Compare MEDIC and DAKP drug->disease edges in canonical space.

Unit of comparison is the **(drug, disease) pair** under the collapsed ``treats``
relation. We bucket pairs into:

* **agree**        -- exact same (canonical drug, canonical disease) on both sides
* **related**      -- same drug, diseases one MONDO is-a hop apart (granularity diff,
                      not a disagreement); recovered before counting "only" sets
* **medic_only**   -- MEDIC asserts it, DAKP does not (potential error / DAKP gap)
* **dakp_only**    -- DAKP asserts it, MEDIC does not, split by clinical_approval_status:
                        on-label (approved_for_condition) -> potential MEDIC gap / DAKP error
                        off-label (off_label_use)         -> expected divergence, not an error

The off-label split is the crux of the "differences as errors" framing: MEDIC is
label-indications only, so DAKP's off-label uses are *expected* to be MEDIC-absent
and should not be read as errors. The fair apples-to-apples overlap is MEDIC vs
DAKP-on-label.
"""
from __future__ import annotations

from collections import defaultdict

from .mondo import MondoGraph
from .reconcile import Reconciler

LINEAGE_HOPS = 2
APPROVED = "approved_for_condition"
OFF_LABEL = "off_label_use"


def _agg_status(prev: str | None, status: str | None) -> str:
    """approved beats off-label beats unspecified when a pair has many edges."""
    rank = {APPROVED: 2, OFF_LABEL: 1, None: 0, "unspecified": 0}
    cur = status or "unspecified"
    if prev is None:
        return cur
    return cur if rank.get(cur, 0) > rank.get(prev, 0) else prev


def build_pairs(edges: list[dict], rec: Reconciler):
    """Reduce raw edges to canonical pair tables keyed by (drug, disease)."""
    medic: dict[tuple[str, str], dict] = {}
    dakp: dict[tuple[str, str], dict] = {}
    contra: dict[tuple[str, str], dict] = {}

    for e in edges:
        drug = rec.drug(e["subject"])
        dis = rec.disease(e["object"])
        key = (drug.canonical, dis.canonical)
        meta = {
            "drug": drug.canonical,
            "drug_label": drug.label,
            "disease": dis.canonical,
            "disease_label": dis.label,
            "disease_prefix": dis.canonical_prefix,
        }
        if e["relation"] == "contraindicated_in":
            if e["source"] == "dakp":
                row = contra.setdefault(key, {**meta, "cases": 0})
                row["cases"] += int(e["number_of_cases"] or 0)
            continue
        # relation == "treats"
        if e["source"] == "medic":
            medic.setdefault(key, meta)
        else:
            row = dakp.setdefault(key, {**meta, "status": None, "cases": 0})
            row["status"] = _agg_status(row["status"], e["clinical_approval_status"])
            row["cases"] += int(e["number_of_cases"] or 0)

    for row in dakp.values():
        row["status"] = row["status"] or "unspecified"
    return medic, dakp, contra


def _lineage_match(key, other: dict, mondo: MondoGraph):
    """Find a same-drug pair in ``other`` whose disease is a MONDO is-a neighbor.

    Returns (matched_key, relation) or None. Only MONDO diseases participate.
    """
    drug, disease = key
    if not disease.startswith("MONDO:"):
        return None
    anc = mondo.ancestors_within(disease, LINEAGE_HOPS) - {disease}
    desc = mondo.descendants_within(disease, LINEAGE_HOPS) - {disease}
    for cand in anc:
        if (drug, cand) in other:
            return (drug, cand), "more_specific"  # our disease is below the match
    for cand in desc:
        if (drug, cand) in other:
            return (drug, cand), "more_general"  # our disease is above the match
    return None


def compare(edges: list[dict], rec: Reconciler, mondo: MondoGraph) -> dict:
    medic, dakp, contra = build_pairs(edges, rec)
    medic_keys, dakp_keys = set(medic), set(dakp)

    agree_keys = medic_keys & dakp_keys
    medic_only_keys = medic_keys - dakp_keys
    dakp_only_keys = dakp_keys - medic_keys

    # --- hierarchy recovery: pull is-a-neighbor pairs out of the "only" sets ---
    # Symmetric: a MEDIC-only pair is "related" if DAKP has the same drug on a
    # MONDO-neighbor disease, and vice versa. We match against the *full* other
    # feed (not just its "only" set), so a finer-grained DAKP edge whose parent
    # MEDIC already agrees on is recovered as granularity, not counted as a
    # disagreement. Each related pair is emitted once.
    related: list[dict] = []
    recovered_medic: set = set()
    recovered_dakp: set = set()

    def _emit(drug, drug_label, medic_disease, medic_label, dakp_key, rel):
        related.append({
            "drug": drug,
            "drug_label": drug_label,
            "medic_disease": medic_disease,
            "medic_disease_label": medic_label,
            "dakp_disease": dakp_key[1],
            "dakp_disease_label": dakp[dakp_key]["disease_label"],
            "relation": rel,  # MEDIC disease relative to DAKP's: more_specific/more_general
            "dakp_status": dakp[dakp_key]["status"],
        })

    for key in sorted(medic_only_keys):
        m = _lineage_match(key, dakp, mondo)
        if not m:
            continue
        matched, rel = m
        _emit(medic[key]["drug"], medic[key]["drug_label"], key[1],
              medic[key]["disease_label"], matched, rel)
        recovered_medic.add(key)
        if matched in dakp_only_keys:
            recovered_dakp.add(matched)
    for key in sorted(dakp_only_keys - recovered_dakp):
        m = _lineage_match(key, medic, mondo)
        if not m:
            continue
        matched, rel = m  # matched is a MEDIC key; rel is DAKP-disease-relative-to-MEDIC
        # flip the relation so it stays "MEDIC relative to DAKP"
        flipped = "more_general" if rel == "more_specific" else "more_specific"
        _emit(medic[matched]["drug"], medic[matched]["drug_label"], matched[1],
              medic[matched]["disease_label"], key, flipped)
        recovered_dakp.add(key)
    medic_only_keys -= recovered_medic
    dakp_only_keys -= recovered_dakp

    # --- dakp_only split by approval status ---
    dakp_only_onlabel = {k for k in dakp_only_keys if dakp[k]["status"] == APPROVED}
    dakp_only_offlabel = dakp_only_keys - dakp_only_onlabel

    # --- on-label-only fair overlap (MEDIC vs DAKP-approved) ---
    dakp_onlabel_keys = {k for k in dakp_keys if dakp[k]["status"] == APPROVED}
    onlabel_agree = medic_keys & dakp_onlabel_keys
    onlabel_union = medic_keys | dakp_onlabel_keys

    def jaccard(inter, union):
        return round(len(inter) / len(union), 4) if union else 0.0

    summary = {
        "medic_pairs": len(medic_keys),
        "dakp_pairs": len(dakp_keys),
        "dakp_onlabel_pairs": len(dakp_onlabel_keys),
        "dakp_offlabel_pairs": len(dakp_keys - dakp_onlabel_keys),
        "agree_exact": len(agree_keys),
        "related_hierarchy": len(related),
        "medic_only": len(medic_only_keys),
        "dakp_only": len(dakp_only_keys),
        "dakp_only_onlabel": len(dakp_only_onlabel),
        "dakp_only_offlabel": len(dakp_only_offlabel),
        "jaccard_all": jaccard(agree_keys, medic_keys | dakp_keys),
        "jaccard_onlabel": jaccard(onlabel_agree, onlabel_union),
        "onlabel_agree": len(onlabel_agree),
        "medic_share_in_dakp": round(len(agree_keys) / len(medic_keys), 4) if medic_keys else 0.0,
        "dakp_onlabel_share_in_medic": (
            round(len(onlabel_agree) / len(dakp_onlabel_keys), 4) if dakp_onlabel_keys else 0.0
        ),
        "contraindication_pairs": len(contra),
    }

    # --- per-pair rows for the browser (disagreements get the full lists) ---
    def medic_row(k):
        return {
            "drug": medic[k]["drug"], "drug_label": medic[k]["drug_label"],
            "disease": k[1], "disease_label": medic[k]["disease_label"],
            "disease_prefix": medic[k]["disease_prefix"],
        }

    def dakp_row(k):
        return {
            "drug": dakp[k]["drug"], "drug_label": dakp[k]["drug_label"],
            "disease": k[1], "disease_label": dakp[k]["disease_label"],
            "disease_prefix": dakp[k]["disease_prefix"],
            "status": dakp[k]["status"], "cases": dakp[k]["cases"],
        }

    agree_rows = sorted(
        ({**medic_row(k), "dakp_status": dakp[k]["status"], "dakp_cases": dakp[k]["cases"]}
         for k in agree_keys),
        key=lambda r: (r["drug_label"], r["disease_label"]),
    )
    medic_only_rows = sorted(
        (medic_row(k) for k in medic_only_keys),
        key=lambda r: (r["drug_label"], r["disease_label"]),
    )
    dakp_onlabel_only_rows = sorted(
        (dakp_row(k) for k in dakp_only_onlabel),
        key=lambda r: (-r["cases"], r["drug_label"], r["disease_label"]),
    )

    # off-label-only is expected divergence (60k+ pairs): summarize by drug, don't dump
    offlabel_by_drug: dict[str, dict] = {}
    for k in dakp_only_offlabel:
        d = offlabel_by_drug.setdefault(
            dakp[k]["drug"], {"drug": dakp[k]["drug"], "drug_label": dakp[k]["drug_label"], "n": 0, "cases": 0}
        )
        d["n"] += 1
        d["cases"] += dakp[k]["cases"]
    offlabel_top_drugs = sorted(offlabel_by_drug.values(), key=lambda r: -r["n"])[:200]

    # --- by-drug / by-disease rollups across both feeds (browsable coverage) ---
    by_drug = _by_drug(medic, dakp, agree_keys)
    by_disease = _by_disease(medic, dakp, agree_keys)
    # adds a `categories` field to each by_disease row and returns the area rollup
    disease_areas = _by_disease_area(by_disease, mondo)

    # off-label-only pair counts per entity, for the detail panels (those pairs
    # are not listed individually, only summarized)
    offlabel_disease_count: dict[str, int] = defaultdict(int)
    for k in dakp_only_offlabel:
        offlabel_disease_count[k[1]] += 1
    for d in by_drug:
        d["offlabel_only"] = offlabel_by_drug.get(d["drug"], {}).get("n", 0)
    for d in by_disease:
        d["offlabel_only"] = offlabel_disease_count.get(d["disease"], 0)

    # --- per-pair long table for the click-through detail panels ---
    # Covers the actionable buckets (agree / related / MEDIC-only / DAKP-on-label-only);
    # off-label-only pairs are excluded here and surfaced as a per-entity count instead.
    pairs: list[dict] = []
    for r in agree_rows:
        pairs.append({"drug": r["drug"], "drug_label": r["drug_label"], "disease": r["disease"],
                      "disease_label": r["disease_label"], "disease_prefix": r["disease_prefix"],
                      "bucket": "agree", "status": r["dakp_status"], "cases": r["dakp_cases"], "note": ""})
    for r in medic_only_rows:
        pairs.append({"drug": r["drug"], "drug_label": r["drug_label"], "disease": r["disease"],
                      "disease_label": r["disease_label"], "disease_prefix": r["disease_prefix"],
                      "bucket": "medic_only", "status": "", "cases": 0, "note": ""})
    for r in dakp_onlabel_only_rows:
        pairs.append({"drug": r["drug"], "drug_label": r["drug_label"], "disease": r["disease"],
                      "disease_label": r["disease_label"], "disease_prefix": r["disease_prefix"],
                      "bucket": "dakp_onlabel_only", "status": "approved_for_condition",
                      "cases": r["cases"], "note": ""})
    for r in related:
        pairs.append({"drug": r["drug"], "drug_label": r["drug_label"], "disease": r["medic_disease"],
                      "disease_label": r["medic_disease_label"], "disease_prefix": "MONDO",
                      "bucket": "related", "status": r["dakp_status"], "cases": 0,
                      "note": f"≈ DAKP {r['relation']}: {r['dakp_disease_label']} ({r['dakp_disease']})"})

    # --- de-conflation report from the disease resolutions actually used ---
    deconflation = _deconflation_report(rec)

    # --- contraindications (DAKP only; no MEDIC counterpart yet) ---
    contra_rows = sorted(
        ({"drug": v["drug"], "drug_label": v["drug_label"], "disease": k[1],
          "disease_label": v["disease_label"], "cases": v["cases"]}
         for k, v in contra.items()),
        key=lambda r: (-r["cases"], r["drug_label"]),
    )

    return {
        "summary": summary,
        "agree": agree_rows,
        "related": sorted(related, key=lambda r: (r["drug_label"], r["medic_disease_label"])),
        "medic_only": medic_only_rows,
        "dakp_onlabel_only": dakp_onlabel_only_rows,
        "dakp_offlabel_only_top_drugs": offlabel_top_drugs,
        "by_drug": by_drug,
        "by_disease": by_disease,
        "disease_areas": disease_areas,
        "pairs": pairs,
        "deconflation": deconflation,
        "contraindications": {"summary": {"pairs": len(contra)}, "rows": contra_rows[:1000]},
    }


def _by_drug(medic, dakp, agree_keys) -> list[dict]:
    drugs: dict[str, dict] = {}

    def slot(drug, label):
        return drugs.setdefault(
            drug,
            {"drug": drug, "drug_label": label, "medic": 0, "dakp": 0, "shared": 0},
        )

    for (drug, _), v in medic.items():
        slot(drug, v["drug_label"])["medic"] += 1
    for (drug, _), v in dakp.items():
        slot(drug, v["drug_label"])["dakp"] += 1
    for drug, _ in agree_keys:
        drugs[drug]["shared"] += 1
    for d in drugs.values():
        union = d["medic"] + d["dakp"] - d["shared"]
        d["jaccard"] = round(d["shared"] / union, 4) if union else 0.0
    return sorted(drugs.values(), key=lambda d: (-(d["medic"] + d["dakp"]), d["drug_label"]))


def _by_disease(medic, dakp, agree_keys) -> list[dict]:
    diseases: dict[str, dict] = {}

    def slot(disease, label, prefix):
        return diseases.setdefault(
            disease,
            {"disease": disease, "disease_label": label, "disease_prefix": prefix,
             "medic": 0, "dakp": 0, "shared": 0},
        )

    for (_, disease), v in medic.items():
        slot(disease, v["disease_label"], v["disease_prefix"])["medic"] += 1
    for (_, disease), v in dakp.items():
        slot(disease, v["disease_label"], v["disease_prefix"])["dakp"] += 1
    for _, disease in agree_keys:
        diseases[disease]["shared"] += 1
    for d in diseases.values():
        union = d["medic"] + d["dakp"] - d["shared"]
        d["jaccard"] = round(d["shared"] / union, 4) if union else 0.0
    return sorted(diseases.values(), key=lambda d: (-(d["medic"] + d["dakp"]), d["disease_label"]))


# MONDO's upper level is axis-based ("disease by body system / process / etiology"),
# so the recognizable disease areas (nervous system, cancer, infectious, ...) sit one
# level below these three axes. A few of those children are themselves abstract
# sub-axes (disease by molecular/genetic/extrinsic mechanism); we expand those one
# more level so e.g. "infectious disease" and "hereditary disease" surface as areas.
_AREA_AXES = {"MONDO:7770006", "MONDO:7770007", "MONDO:7770008"}
_ABSTRACT_SUBAXES = {"MONDO:7770009", "MONDO:7770010", "MONDO:7770011"}
NON_MONDO_AREA = "(non-MONDO disease)"
UNCLASSIFIED_AREA = "(unclassified)"


def _area_terms(mondo: MondoGraph) -> set[str]:
    areas: set[str] = set()
    for axis in _AREA_AXES:
        for child in mondo.children_of(axis):
            if child in _ABSTRACT_SUBAXES:
                areas |= mondo.children_of(child)
            else:
                areas.add(child)
    return areas


def _by_disease_area(by_disease: list[dict], mondo: MondoGraph) -> list[dict]:
    """Roll disease coverage up to recognizable MONDO disease areas.

    Mutates each ``by_disease`` row to add ``categories`` (the area labels it
    belongs to) so the site can drill the per-disease table down by area. A
    disease can sit under several areas (MONDO multiple-inheritance); it is
    counted under each, so area totals can exceed the global pair counts.
    """
    top = _area_terms(mondo)
    areas: dict[str, dict] = {}

    def slot(cid, label):
        return areas.setdefault(
            cid, {"area": cid, "label": label, "medic": 0, "dakp": 0, "shared": 0, "diseases": 0}
        )

    for d in by_disease:
        if d["disease_prefix"] != "MONDO":
            members = [(NON_MONDO_AREA, NON_MONDO_AREA)]
        else:
            ancestors = mondo.ancestors(d["disease"]) & top
            if d["disease"] in top:
                ancestors = ancestors | {d["disease"]}
            members = (
                [(c, mondo.label(c)) for c in sorted(ancestors)]
                if ancestors else [(UNCLASSIFIED_AREA, UNCLASSIFIED_AREA)]
            )
        d["categories"] = [label for _, label in members]
        for cid, label in members:
            a = slot(cid, label)
            a["medic"] += d["medic"]
            a["dakp"] += d["dakp"]
            a["shared"] += d["shared"]
            a["diseases"] += 1

    for a in areas.values():
        union = a["medic"] + a["dakp"] - a["shared"]
        a["jaccard"] = round(a["shared"] / union, 4) if union else 0.0
    return sorted(areas.values(), key=lambda a: -(a["medic"] + a["dakp"]))


def _deconflation_report(rec: Reconciler) -> dict:
    """Categorize every disease CURIE we resolved by its normalization outcome."""
    by_outcome: dict[str, int] = defaultdict(int)
    hp_to_mondo: list[dict] = []
    kept_hp: list[dict] = []
    unresolved: list[dict] = []
    for orig, res in rec._disease.items():
        op = orig.split(":", 1)[0]
        if res.deconflated_from_hp:
            by_outcome["hp_to_mondo"] += 1
            hp_to_mondo.append({"original": orig, "mondo": res.canonical, "label": res.label})
        elif res.kept_hp:
            by_outcome["kept_hp"] += 1
            kept_hp.append({"original": orig, "label": res.label})
        elif res.canonical_prefix == "MONDO":
            by_outcome["lifted_to_mondo" if op != "MONDO" else "already_mondo"] += 1
        elif not res.resolved:
            by_outcome["unresolved"] += 1
            unresolved.append({"original": orig, "label": res.label})
        else:
            by_outcome[f"kept_{res.canonical_prefix.lower()}"] += 1
    return {
        "summary": dict(sorted(by_outcome.items(), key=lambda kv: -kv[1])),
        "hp_to_mondo": sorted(hp_to_mondo, key=lambda r: r["original"]),
        "kept_hp": sorted(kept_hp, key=lambda r: r["original"]),
        "unresolved": sorted(unresolved, key=lambda r: r["original"])[:500],
    }
