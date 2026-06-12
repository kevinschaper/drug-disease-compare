"""Compare drug->disease edges from N feeds in canonical MONDO-centric space.

Unit of comparison is the **(drug, disease) pair** under the collapsed ``treats``
relation. Rather than a fixed MEDIC-vs-DAKP split, each pair records, per source, a
membership status:

* **exact**   -- the source asserts this exact (canonical drug, canonical disease)
* **related** -- the source asserts the same drug on a disease one-to-two MONDO is-a
                 hops away (a granularity difference, not a disagreement)
* **""**      -- absent

Adding a feed is a one-line change to ``SOURCE_ORDER`` (+ ``DRUG_FILTERED`` if its
"treatment" subjects mix drugs with non-drug modalities, like dismech's MAXO/NCIT).
DAKP additionally carries ``clinical_approval_status`` (approved vs off-label) and
``number_of_cases``; dismech carries a per-edge publication count.

Reading the overlap: "agreement" is a pair exact in >=2 sources. The DAKP off-label
split still matters -- MEDIC/dismech are (approved) indications, so a DAKP off-label
pair absent from them is expected, not an error.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from .mondo import MondoGraph
from .reconcile import Reconciler

LINEAGE_HOPS = 2
APPROVED = "approved_for_condition"
OFF_LABEL = "off_label_use"

# Source registry. Order drives column order on the site; add a feed here (and to
# the CLI loader) to bring it in. DRUG_FILTERED feeds get their non-drug treatment
# subjects (procedures, medical actions) dropped via the reconciler's is_drug check.
SOURCE_ORDER = ["medic", "dakp", "dismech"]
DRUG_FILTERED = {"dismech"}


def _agg_status(prev: str | None, status: str | None) -> str:
    """approved beats off-label beats unspecified when a pair has many edges."""
    rank = {APPROVED: 2, OFF_LABEL: 1, None: 0, "unspecified": 0}
    cur = status or "unspecified"
    if prev is None:
        return cur
    return cur if rank.get(cur, 0) > rank.get(prev, 0) else prev


def build_pairs(edges: list[dict], rec: Reconciler):
    """Reduce raw edges to per-source canonical pair tables keyed by (drug, disease).

    Returns ``(treat, contra)`` where ``treat[source]`` maps (drug, disease) -> meta
    and ``contra`` holds DAKP contraindications.
    """
    treat: dict[str, dict[tuple[str, str], dict]] = {s: {} for s in SOURCE_ORDER}
    contra: dict[tuple[str, str], dict] = {}

    for e in edges:
        src = e["source"]
        if e["relation"] == "contraindicated_in":
            if src == "dakp":
                drug = rec.drug(e["subject"])
                dis = rec.disease(e["object"])
                row = contra.setdefault(
                    (drug.canonical, dis.canonical),
                    {"drug": drug.canonical, "drug_label": drug.label,
                     "disease": dis.canonical, "disease_label": dis.label, "cases": 0},
                )
                row["cases"] += int(e["number_of_cases"] or 0)
            continue
        # treats: drop non-drug subjects for feeds that mix modalities
        if src in DRUG_FILTERED and not rec.is_drug(e["subject"]):
            continue
        drug = rec.drug(e["subject"])
        dis = rec.disease(e["object"])
        key = (drug.canonical, dis.canonical)
        row = treat.setdefault(src, {}).setdefault(
            key,
            {"drug": drug.canonical, "drug_label": drug.label,
             "disease": dis.canonical, "disease_label": dis.label,
             "disease_prefix": dis.canonical_prefix, "status": None, "cases": 0, "pubs": 0},
        )
        if src == "dakp":
            row["status"] = _agg_status(row["status"], e["clinical_approval_status"])
            row["cases"] += int(e["number_of_cases"] or 0)
        elif src == "dismech":
            row["pubs"] = max(row["pubs"], len(e.get("publications") or []))

    for row in treat.get("dakp", {}).values():
        row["status"] = row["status"] or "unspecified"
    return treat, contra


def compare(edges: list[dict], rec: Reconciler, mondo: MondoGraph,
            dismech_scope: set | None = None) -> dict:
    treat, contra = build_pairs(edges, rec)
    present = [s for s in SOURCE_ORDER if treat.get(s)]

    # canonical labels for each pair (first source that has it wins)
    meta_of: dict[tuple[str, str], dict] = {}
    for s in present:
        for k, v in treat[s].items():
            meta_of.setdefault(k, {
                "drug": v["drug"], "drug_label": v["drug_label"], "disease": v["disease"],
                "disease_label": v["disease_label"], "disease_prefix": v["disease_prefix"],
            })
    universe = sorted(meta_of)

    # per source: drug -> {diseases}, for the is-a-neighbor ("related") lookup
    src_dd: dict[str, dict[str, set]] = {s: defaultdict(set) for s in present}
    for s in present:
        for (g, d) in treat[s]:
            src_dd[s][g].add(d)
    neigh_cache: dict[str, set] = {}

    # disease scope per source: where the source's *absence* is a real signal.
    # broad feeds (MEDIC/DAKP) cover the diseases they assert drugs for; dismech is
    # disease-centric, so its scope is every disease it curates (passed in), which
    # is wider than the diseases it has drug edges for.
    scope: dict[str, set] = {s: {d for (_g, d) in treat[s]} for s in present}
    if dismech_scope and "dismech" in present:
        scope["dismech"] = scope["dismech"] | set(dismech_scope)

    def neighbors(disease: str) -> set:
        if disease not in neigh_cache:
            neigh_cache[disease] = (
                mondo.lineage_within(disease, LINEAGE_HOPS) - {disease}
                if disease.startswith("MONDO:") else set()
            )
        return neigh_cache[disease]

    def status_for(s: str, key) -> tuple[str, str]:
        """(status, neighbor_label) for source ``s`` on pair ``key``."""
        g, d = key
        if key in treat[s]:
            return "exact", ""
        nb = neighbors(d) & src_dd[s].get(g, set())
        if nb:
            cand = sorted(nb)[0]
            return "related", mondo.label(cand)
        return "", ""

    # --- per-pair rows with per-source membership ---
    pairs: list[dict] = []
    for key in universe:
        m = meta_of[key]
        row = {**m}
        n_exact = 0
        notes = []
        for s in present:
            st, nb_label = status_for(s, key)
            row[s] = st
            if st == "exact":
                n_exact += 1
            elif st == "related" and nb_label:
                notes.append(f"{s}≈{nb_label}")
        row["n_exact"] = n_exact
        # in_scope flag per source: is this disease one the source actually covers?
        # lets the UI tell "absent because disagrees" from "absent because uncurated".
        for s in present:
            row[f"{s}_scope"] = key[1] in scope[s]
        dk = treat["dakp"].get(key) if "dakp" in present else None
        row["dakp_status"] = dk["status"] if dk else ""
        row["dakp_cases"] = dk["cases"] if dk else 0
        dm = treat["dismech"].get(key) if "dismech" in present else None
        row["dismech_pubs"] = dm["pubs"] if dm else 0
        row["note"] = "; ".join(notes)
        pairs.append(row)
    pairs.sort(key=lambda r: (-r["n_exact"], r["drug_label"], r["disease_label"]))

    # --- summary: per-source counts, exact-set combinations, pairwise overlap ---
    src_counts = {s: len(treat[s]) for s in present}
    combo = Counter(frozenset(s for s in present if p[s] == "exact") for p in pairs)

    def comboname(fs):
        return "+".join(s for s in present if s in fs) or "(none)"

    combinations = {comboname(fs): n for fs, n in
                    sorted(combo.items(), key=lambda kv: -kv[1]) if fs}

    def exact_set(s):
        return {k for k in treat[s]}

    def jac(a, b):
        u = len(a | b)
        return round(len(a & b) / u, 4) if u else 0.0

    pairwise = {}
    for i, a in enumerate(present):
        for b in present[i + 1:]:
            pairwise[f"{a}+{b}"] = {
                "shared": len(exact_set(a) & exact_set(b)),
                "jaccard": jac(exact_set(a), exact_set(b)),
            }
    all_exact = set.intersection(*[exact_set(s) for s in present]) if len(present) > 1 else set()

    dakp_onlabel = ({k for k, v in treat["dakp"].items() if v["status"] == APPROVED}
                    if "dakp" in present else set())
    medic_set = exact_set("medic") if "medic" in present else set()
    onlabel_agree = medic_set & dakp_onlabel

    summary = {
        "sources": present,
        "source_pairs": src_counts,
        "universe": len(universe),
        "agree_2plus": sum(1 for p in pairs if p["n_exact"] >= 2),
        "agree_all": len(all_exact),
        "combinations": combinations,
        "pairwise": pairwise,
        "dakp_onlabel_pairs": len(dakp_onlabel),
        "dakp_offlabel_pairs": (src_counts.get("dakp", 0) - len(dakp_onlabel)),
        "medic_vs_dakp_onlabel": {
            "shared": len(onlabel_agree),
            "jaccard": jac(medic_set, dakp_onlabel),
            "of_dakp_onlabel_in_medic": (
                round(len(onlabel_agree) / len(dakp_onlabel), 4) if dakp_onlabel else 0.0),
        },
        "contraindication_pairs": len(contra),
        "scope_diseases": {s: len(scope[s]) for s in present},
    }

    # --- dismech-specific lens (scope-aware) ---
    # dismech is disease-centric and narrow, so it's read on its own terms: of its
    # drug→disease edges, how many do MEDIC/DAKP corroborate (exact OR is-a-related),
    # and how many are novel-to-dismech (worth a look: new+good, or wrong). The flip
    # side is dismech *gaps* — within its curated diseases, edges the broad feeds
    # carry that dismech lacks.
    if "dismech" in present:
        def backed(p, s):
            return p[s] in ("exact", "related")
        others = [s for s in present if s != "dismech"]
        dpairs = [p for p in pairs if p["dismech"] == "exact"]
        supported = [p for p in dpairs if any(backed(p, s) for s in others)]
        summary["dismech"] = {
            "edges": len(dpairs),
            "supported": len(supported),
            "novel": len(dpairs) - len(supported),
            "by_medic": sum(1 for p in dpairs if "medic" in others and backed(p, "medic")),
            "by_dakp": sum(1 for p in dpairs if "dakp" in others and backed(p, "dakp")),
            "scope_diseases": len(scope["dismech"]),
            # gaps: dismech curates the disease but lacks the edge a broad feed has
            "gaps_in_scope": sum(
                1 for p in pairs
                if p["dismech"] == "" and p["dismech_scope"]
                and any(p[s] == "exact" for s in others)
            ),
        }

    # --- rollups + reports ---
    by_drug = _rollup(pairs, present, "drug", "drug_label")
    by_disease = _rollup(pairs, present, "disease", "disease_label", prefix_key="disease_prefix")
    disease_areas = _by_disease_area(by_disease, present, mondo)

    # off-label-only (DAKP off-label, not exact in any other source): summarize by drug
    offlabel_top_drugs = _offlabel_top_drugs(pairs, present)

    deconflation = _deconflation_report(rec)
    contra_rows = sorted(
        ({"drug": v["drug"], "drug_label": v["drug_label"], "disease": k[1],
          "disease_label": v["disease_label"], "cases": v["cases"]}
         for k, v in contra.items()),
        key=lambda r: (-r["cases"], r["drug_label"]),
    )

    return {
        "summary": summary,
        "pairs": pairs,
        "by_drug": by_drug,
        "by_disease": by_disease,
        "disease_areas": disease_areas,
        "dakp_offlabel_only_top_drugs": offlabel_top_drugs,
        "deconflation": deconflation,
        "contraindications": {"summary": {"pairs": len(contra)}, "rows": contra_rows[:1000]},
    }


def _rollup(pairs, present, key, label_key, prefix_key=None) -> list[dict]:
    """Per-entity coverage: exact pair counts per source, shared (>=2), off-label."""
    agg: dict[str, dict] = {}
    for p in pairs:
        k = p[key]
        a = agg.get(k)
        if a is None:
            a = {key: k, label_key: p[label_key], **({prefix_key: p[prefix_key]} if prefix_key else {})}
            for s in present:
                a[s] = 0
            a.update(shared=0, offlabel=0, _md=0)
            agg[k] = a
        for s in present:
            if p[s] == "exact":
                a[s] += 1
        if p["n_exact"] >= 2:
            a["shared"] += 1
        if "medic" in present and "dakp" in present and p["medic"] == "exact" and p["dakp"] == "exact":
            a["_md"] += 1
        if p.get("dakp") == "exact" and p["dakp_status"] == OFF_LABEL:
            a["offlabel"] += 1
    for a in agg.values():
        m, d = a.get("medic", 0), a.get("dakp", 0)
        union = m + d - a["_md"]
        a["jaccard"] = round(a["_md"] / union, 4) if union else 0.0
        del a["_md"]
    total = lambda a: sum(a[s] for s in present)  # noqa: E731
    return sorted(agg.values(), key=lambda a: (-total(a), a[label_key]))


def _offlabel_top_drugs(pairs, present) -> list[dict]:
    by_drug: dict[str, dict] = {}
    for p in pairs:
        others = [s for s in present if s != "dakp"]
        if p.get("dakp") == "exact" and p["dakp_status"] == OFF_LABEL and all(p[s] != "exact" for s in others):
            d = by_drug.setdefault(
                p["drug"], {"drug": p["drug"], "drug_label": p["drug_label"], "n": 0, "cases": 0})
            d["n"] += 1
            d["cases"] += p["dakp_cases"]
    return sorted(by_drug.values(), key=lambda r: -r["n"])[:200]


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


def _by_disease_area(by_disease: list[dict], present: list[str], mondo: MondoGraph) -> list[dict]:
    """Roll disease coverage up to recognizable MONDO disease areas.

    Mutates each ``by_disease`` row to add ``categories`` (the area labels it
    belongs to) so the site can drill the per-disease table down by area. A
    disease can sit under several areas (MONDO multiple-inheritance); it is
    counted under each, so area totals can exceed the global pair counts.
    """
    top = _area_terms(mondo)
    areas: dict[str, dict] = {}

    def slot(cid, label):
        if cid not in areas:
            a = {"area": cid, "label": label, "shared": 0, "diseases": 0}
            for s in present:
                a[s] = 0
            areas[cid] = a
        return areas[cid]

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
            for s in present:
                a[s] += d[s]
            a["shared"] += d["shared"]
            a["diseases"] += 1

    for a in areas.values():
        total = sum(a[s] for s in present)
        a["jaccard"] = round(a["shared"] / total, 4) if total else 0.0
    return sorted(areas.values(), key=lambda a: -sum(a[s] for s in present))


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
