"""Experiment: how much does a drug-axis collapse change cross-source agreement,
and what does each grouping authority merge?

This is a bench experiment, NOT part of the site build. It assigns every distinct
canonical drug a ``group_id`` under each authority (active moiety / RxNorm ingredient
/ ChEBI functional parent), then re-scores agreement at (drug_group, disease)
granularity. For each backend it writes:

  out/audit_<backend>.json   -- every multi-member group (eyeball for over-merge)
  out/impact.json            -- strict vs collapsed agreement, new agreements, +examples

Crucially it keeps the disease axis EXACT (same MONDO) so every new agreement is
attributable to the drug collapse alone. Combining with disease is-a "related" would
only add more; we isolate the drug effect here.

Run:  uv run python -m experiments.drug_collapse        (warms caches; resumable)
      uv run python -m experiments.drug_collapse --limit 300   (quick smoke run)
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

import pyarrow.parquet as pq

from drug_edge_compare.drug_groups import make_groupers
from drug_edge_compare.nodenorm import NodeNorm

ROOT = Path(__file__).resolve().parent.parent
PAIRS = ROOT / "src" / "data" / "pairs.parquet"
NN_CACHE = ROOT / "data" / "nodenorm_cache.json"
GROUP_CACHE = ROOT / "data" / "drug_groups_cache.json"
OUT = Path(__file__).resolve().parent / "out"
SOURCES = ["medic", "dakp", "dismech"]
SAVE_EVERY = 50


def load_pairs() -> list[dict]:
    cols = ["drug", "drug_label", "disease", "disease_label", "medic", "dakp", "dismech", "n_exact"]
    t = pq.read_table(PAIRS, columns=cols)
    d = t.to_pydict()
    return [{c: d[c][i] for c in cols} for i in range(t.num_rows)]


def assign_groups(drugs: list[str], nn: NodeNorm, limit: int | None):
    """drug CURIE -> {backend: Grouping} for every distinct drug."""
    drugs = drugs[:limit] if limit else drugs
    nn.warm(drugs)  # ensure cliques are resolvable (cache hit for most)
    clients, groupers = make_groupers(GROUP_CACHE)
    out: dict[str, dict] = {}
    for i, d in enumerate(drugs, 1):
        clique = nn.clique(d)
        out[d] = {g.name: g.group(clique) for g in groupers}
        if i % SAVE_EVERY == 0:
            clients.save()
            print(f"  grouped {i}/{len(drugs)}", flush=True)
    clients.save()
    return out, [g.name for g in groupers]


def score(pairs: list[dict], groups: dict[str, dict], backend: str) -> dict:
    """Re-score agreement at (drug_group, disease) granularity for one backend."""
    def gid(drug: str) -> str:
        g = groups.get(drug, {}).get(backend)
        return g.group_id if g else drug

    # per source: set of (group, disease) it asserts EXACTLY
    src_gd: dict[str, set] = {s: set() for s in SOURCES}
    # strict agreement, lifted to group granularity, so "new" excludes pre-existing
    strict_agree_gd: set = set()
    members_in_play: dict[str, set] = defaultdict(set)  # group -> {drug} (only drugs we saw)
    for p in pairs:
        g = gid(p["drug"])
        members_in_play[g].add(p["drug"])
        for s in SOURCES:
            if p[s] == "exact":
                src_gd[s].add((g, p["disease"]))
        if p["n_exact"] >= 2:
            strict_agree_gd.add((g, p["disease"]))

    # collapsed agreement
    gd_n: dict[tuple, int] = defaultdict(int)
    gd_srcs: dict[tuple, set] = defaultdict(set)
    for s in SOURCES:
        for key in src_gd[s]:
            gd_n[key] += 1
            gd_srcs[key].add(s)
    collapsed_agree = {k for k, n in gd_n.items() if n >= 2}
    new_agree = collapsed_agree - strict_agree_gd

    # break new agreements down by which source set, with examples
    by_combo: dict[str, int] = defaultdict(int)
    examples = []
    label_of_drug = {p["drug"]: p["drug_label"] for p in pairs}
    label_of_dis = {p["disease"]: p["disease_label"] for p in pairs}
    for (g, d) in sorted(new_agree):
        combo = "+".join(s for s in SOURCES if s in gd_srcs[(g, d)])
        by_combo[combo] += 1
        if len(examples) < 60:
            mem = sorted(members_in_play.get(g, {g}))
            examples.append({
                "group": g, "disease": d, "disease_label": label_of_dis.get(d, d),
                "sources": combo,
                "merged_drugs": [f"{label_of_drug.get(m, m)} [{m}]" for m in mem],
            })

    return {
        "backend": backend,
        "strict_agree_gd": len(strict_agree_gd),
        "collapsed_agree_gd": len(collapsed_agree),
        "new_agreements": len(new_agree),
        "new_by_source_combo": dict(sorted(by_combo.items(), key=lambda kv: -kv[1])),
        "examples": examples,
    }


def audit(groups: dict[str, dict], backend: str) -> dict:
    """Every group with >1 distinct member drug — the over-merge eyeball list."""
    by_group: dict[str, dict] = {}
    for drug, per in groups.items():
        g = per.get(backend)
        if not g:
            continue
        slot = by_group.setdefault(g.group_id, {"group_id": g.group_id, "group_label": g.group_label,
                                                "method": g.method, "members": []})
        slot["members"].append({"drug": drug, "label": g.drug_label, "via": g.via})
    multi = [v for v in by_group.values() if len({m["drug"] for m in v["members"]}) > 1]
    multi.sort(key=lambda v: -len(v["members"]))
    grouped_drugs = sum(len(v["members"]) for v in multi)
    return {
        "backend": backend,
        "total_drugs": len(groups),
        "distinct_groups": len(by_group),
        "multi_member_groups": len(multi),
        "drugs_in_multi_groups": grouped_drugs,
        "groups": multi,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="cap distinct drugs (smoke test)")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)

    pairs = load_pairs()
    drugs = sorted({p["drug"] for p in pairs})
    print(f"{len(pairs):,} pairs, {len(drugs):,} distinct drugs", flush=True)

    nn = NodeNorm(NN_CACHE)
    groups, backends = assign_groups(drugs, nn, args.limit)

    if args.limit:  # restrict pairs to the drugs we grouped
        kept = set(groups)
        pairs = [p for p in pairs if p["drug"] in kept]

    impact = []
    for b in backends:
        a = audit(groups, b)
        (OUT / f"audit_{b}.json").write_text(json.dumps(a, indent=2, ensure_ascii=False))
        impact.append(score(pairs, groups, b))
    (OUT / "impact.json").write_text(json.dumps(impact, indent=2, ensure_ascii=False))

    print("\n=== drug-collapse impact (disease held EXACT) ===")
    print(f"{'backend':<26}{'groups':>8}{'merged':>8}{'strict':>9}{'collapsed':>11}{'NEW':>7}")
    audits = {b: json.loads((OUT / f'audit_{b}.json').read_text()) for b in backends}
    for r in impact:
        a = audits[r["backend"]]
        print(f"{r['backend']:<26}{a['distinct_groups']:>8}{a['drugs_in_multi_groups']:>8}"
              f"{r['strict_agree_gd']:>9}{r['collapsed_agree_gd']:>11}{r['new_agreements']:>7}")
    for r in impact:
        print(f"\n{r['backend']} new agreements by source combo: {r['new_by_source_combo']}")
    print(f"\nwrote {OUT}/impact.json + audit_*.json")


if __name__ == "__main__":
    main()
