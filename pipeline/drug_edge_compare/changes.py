"""Characterize how each source changed between two of its releases.

Both releases are re-resolved through the *same* Node Normalizer + MONDO graph, so a
difference here is a change in what the source asserts (or in how it grounds its own
identifiers), not drift in our reconciliation. Each source is read through the same
"lenses" the head-to-head uses:

* medic   -- treats, contraindicated
* dakp    -- approved (approved_for_condition), off-label (FAERS), contraindicated
* dismech -- treats (drug-typed subset)

Per lens we report kept / added / removed canonical pairs, and explain each churned
pair where we can:

* **re-grounded**             -- the other release has the same pair under a different
                                 CURIE for the same drug (same FDA/GSRS active moiety:
                                 salt <-> parent, brand <-> ingredient, a re-minted id)
* **drug new / drug dropped** -- the drug isn't in the other release at all (for that lens)
* **re-grained**              -- the other release has the same drug on a disease 1-2
                                 MONDO is-a hops away (a granularity change, not a loss)
* **status flip** (DAKP)      -- the pair moved between approved and off-label
* otherwise **changed**       -- same drug, unrelated disease set

Finally, a 2x2 *agreement trajectory* for each source pair (old/new x old/new) attributes a
change in head-to-head overlap to whichever source moved.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Callable

from .compare import APPROVED, LINEAGE_HOPS, OFF_LABEL, build_pairs
from .mondo import MondoGraph
from .reconcile import Reconciler

# lens name -> (source, selector over build_pairs output)
LENSES: dict[str, list[str]] = {
    "medic": ["treats", "contraindicated"],
    "dakp": ["approved", "off-label", "contraindicated"],
    "dismech": ["treats"],
}

# indication-grade sets compared head to head (mirrors summary.indication)
IND = {"MEDIC": ("medic", "treats"), "DAKP-approved": ("dakp", "approved"),
       "dismech": ("dismech", "treats")}


def lens_sets(source: str, edges: list[dict], rec: Reconciler) -> dict[str, dict]:
    """source edges -> {lens: {(drug, disease): meta}} in canonical space."""
    treat, contra = build_pairs(edges, rec)
    t = treat.get(source, {})
    out: dict[str, dict] = {}
    if source == "dakp":
        out["approved"] = {k: v for k, v in t.items() if v["status"] == APPROVED}
        out["off-label"] = {k: v for k, v in t.items() if v["status"] == OFF_LABEL}
    else:
        out["treats"] = t
    if source in contra:
        out["contraindicated"] = contra[source]
    return {k: v for k, v in out.items() if k in LENSES[source]}


def _raw_profile(edges: list[dict]) -> dict:
    """Pre-normalization shape of one release: predicates, id prefixes, statuses."""
    pred = Counter(e["predicate"] for e in edges)
    sp = Counter(e["subject"].split(":", 1)[0] for e in edges)
    op = Counter(e["object"].split(":", 1)[0] for e in edges)
    status = Counter(e["clinical_approval_status"] or "unspecified"
                     for e in edges if e["relation"] == "treats")
    agencies = Counter(a for e in edges for a in (e.get("agencies") or []))
    reliability = Counter(e.get("reliability") for e in edges if e.get("reliability"))
    return {
        "edges": len(edges),
        # MEDIC 1.x emits one edge per regulator assertion; distinct triples compare
        # like-for-like with per-pair exports
        "triples": len({(e["subject"], e["predicate"], e["object"]) for e in edges}),
        "predicates": dict(pred.most_common()),
        "subjects": len({e["subject"] for e in edges}),
        "objects": len({e["object"] for e in edges}),
        "subject_prefixes": dict(sp.most_common()),
        "object_prefixes": dict(op.most_common()),
        "approval_status": dict(status.most_common()) if any(
            e["clinical_approval_status"] for e in edges) else {},
        "agencies": dict(agencies.most_common()),
        "reliability": dict(reliability.most_common()),
    }


def _diff_lens(old: dict, new: dict, mondo: MondoGraph, neigh_cache: dict,
               status_of_other: dict | None = None,
               group: Callable[[str], str] | None = None) -> tuple[dict, list[dict]]:
    """Diff one lens; returns (summary, churned pair rows).

    ``group`` maps a canonical drug to its moiety group; when given, a drug absent from
    the other release is first looked for under a sibling CURIE of the same moiety.
    """
    group = group or (lambda d: d)

    def neighbors(d: str) -> set:
        if d not in neigh_cache:
            neigh_cache[d] = (mondo.lineage_within(d, LINEAGE_HOPS) - {d}
                              if d.startswith("MONDO:") else set())
        return neigh_cache[d]

    def by_drug(pairs) -> dict[str, set]:
        m: dict[str, set] = defaultdict(set)
        for g, d in pairs:
            m[g].add(d)
        return m

    o, n = set(old), set(new)
    o_dd, n_dd = by_drug(o), by_drug(n)
    o_gd, n_gd = by_drug({(group(g), d) for g, d in o}), by_drug({(group(g), d) for g, d in n})
    rows: list[dict] = []
    reasons: dict[str, Counter] = {"added": Counter(), "removed": Counter()}

    for change, keys, here, other_dd, other_gd in (("added", n - o, new, o_dd, o_gd),
                                                   ("removed", o - n, old, n_dd, n_gd)):
        for key in keys:
            g, d = key
            grp = group(g)
            # the drug's diseases in the other release, under this CURIE or a sibling's
            other = other_dd.get(g) or other_gd.get(grp)
            if status_of_other is not None and key in status_of_other.get(change, set()):
                reason = "status flip"
            elif g not in other_dd and d in other_gd.get(grp, ()):
                reason = "re-grounded"
            elif not other:
                reason = "drug new" if change == "added" else "drug dropped"
            elif neighbors(d) & other:
                reason = "re-grained"
            else:
                reason = "changed"
            reasons[change][reason] += 1
            m = here[key]
            rows.append({
                "drug": g, "drug_label": m["drug_label"],
                "disease": d, "disease_label": m["disease_label"],
                "change": change, "reason": reason,
            })

    def prefix_mix(pairs):
        return dict(Counter(d.split(":", 1)[0] for _g, d in pairs).most_common())

    od, nd = {g for g, _ in o}, {g for g, _ in n}
    ods, nds = {d for _, d in o}, {d for _, d in n}
    union = len(o | n)
    summary = {
        "old": len(o), "new": len(n), "kept": len(o & n),
        "added": len(n - o), "removed": len(o - n),
        "jaccard": round(len(o & n) / union, 4) if union else 0.0,
        "reasons": {k: dict(v.most_common()) for k, v in reasons.items()},
        "drugs": {"old": len(od), "new": len(nd), "kept": len(od & nd),
                  "added": len(nd - od), "removed": len(od - nd)},
        "diseases": {"old": len(ods), "new": len(nds), "kept": len(ods & nds),
                     "added": len(nds - ods), "removed": len(ods - nds)},
        "disease_prefixes": {"old": prefix_mix(o), "new": prefix_mix(n)},
    }
    return summary, rows


def _top_churn(rows: list[dict], k: int = 30) -> list[dict]:
    agg: dict[str, dict] = {}
    for r in rows:
        a = agg.setdefault(r["drug"], {"drug": r["drug"], "drug_label": r["drug_label"],
                                       "added": 0, "removed": 0})
        a[r["change"]] += 1
    return sorted(agg.values(), key=lambda a: -(a["added"] + a["removed"]))[:k]


def source_changes(source: str, old_edges: list[dict], new_edges: list[dict],
                   rec: Reconciler, mondo: MondoGraph, versions: dict,
                   group: Callable[[str], str] | None = None) -> tuple[dict, list[dict], dict]:
    """Full old->new characterization for one source.

    Returns (summary, pair rows for the parquet, {"old": lens_sets, "new": lens_sets}).
    """
    old_sets = lens_sets(source, old_edges, rec)
    new_sets = lens_sets(source, new_edges, rec)
    neigh: dict = {}

    # DAKP approved <-> off-label flips are their own churn reason
    flips = None
    if source == "dakp":
        flips = {
            "approved": {"added": set(new_sets["approved"]) & set(old_sets["off-label"]),
                         "removed": set(old_sets["approved"]) & set(new_sets["off-label"])},
            "off-label": {"added": set(new_sets["off-label"]) & set(old_sets["approved"]),
                          "removed": set(old_sets["off-label"]) & set(new_sets["approved"])},
        }

    lenses: dict[str, dict] = {}
    all_rows: list[dict] = []
    for lens in LENSES[source]:
        o, n = old_sets.get(lens, {}), new_sets.get(lens, {})
        if not o and not n:
            continue
        summ, rows = _diff_lens(o, n, mondo, neigh, (flips or {}).get(lens), group)
        summ["top_churn_drugs"] = _top_churn(rows)
        lenses[lens] = summ
        for r in rows:
            r.update(source=source, lens=lens)
        all_rows.extend(rows)

    summary = {
        "source": source,
        "versions": versions,
        "raw": {"old": _raw_profile(old_edges), "new": _raw_profile(new_edges)},
        "lenses": lenses,
    }
    return summary, all_rows, {"old": old_sets, "new": new_sets}


def agreement_trajectory(sets: dict[str, dict]) -> list[dict]:
    """2x2 per indication source pair: overlap with each side at old vs new release.

    ``sets[source]["old"|"new"][lens]`` as returned by ``source_changes``. Reading across
    a row: old/old -> new/new is the total shift; the mixed cells say which source's
    release moved it.
    """
    def ind(name, ver):
        src, lens = IND[name]
        return set(sets[src][ver].get(lens, {}))

    out = []
    names = list(IND)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            row = {"pair": f"{a} + {b}", "a": a, "b": b}
            for va in ("old", "new"):
                for vb in ("old", "new"):
                    A, B = ind(a, va), ind(b, vb)
                    u = len(A | B)
                    row[f"{va}_{vb}"] = {"shared": len(A & B),
                                         "jaccard": round(len(A & B) / u, 4) if u else 0.0}
            out.append(row)
    return out
