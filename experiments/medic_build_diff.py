"""Pair-level diff of two local MeDIC builds, with the same reconciler, moiety grouping and
change reasons as ``just changes`` (which only diffs the published medic-ingest release against
the latest build).

    PYTHONPATH=pipeline:. uv run python -m experiments.medic_build_diff [OLD] [NEW]

OLD / NEW are folders under data/inputs/medic/ (default: b1013 -> new, i.e. the 2026-10-13 build
against the 2026-10-23 release candidate). Writes experiments/out/v2/build_diff_<OLD>_<NEW>.json
(lens summaries) and .tsv (one row per changed pair with its reason).
"""
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from drug_edge_compare import changes, cli, compare, load
from drug_edge_compare.drug_groups import moiety_grouper
from drug_edge_compare.mondo import MondoGraph
from drug_edge_compare.nodenorm import NodeNorm

OUT = Path(__file__).resolve().parent / "out" / "v2"


def main(old: str = "b1013", new: str = "new") -> None:
    e_old = load.load_medic(cli.INPUTS / "medic" / old / "medic_edges.jsonl")
    e_new = load.load_medic(cli.INPUTS / "medic" / new / "medic_edges.jsonl")
    nn = NodeNorm(cli.CACHE)
    nn.warm(load.all_curies(e_old) | load.all_curies(e_new))
    mondo = MondoGraph(cli.INPUTS / "mondo_edges.tsv", cli.INPUTS / "mondo_nodes.tsv")
    rec, _ = cli._reconciler(nn, mondo, e_old + e_new)
    gclients, grouper = moiety_grouper(cli.DRUG_GROUP_CACHE)
    gmemo: dict[str, str] = {}

    def group(drug: str) -> str:
        if drug not in gmemo:
            gmemo[drug] = grouper.group(compare.named_clique(rec, drug)).group_id
        return gmemo[drug]

    summ, rows, _ = changes.source_changes("medic", e_old, e_new, rec, mondo, {"old": old, "new": new}, group)
    gclients.save()
    for lens, L in summ["lenses"].items():
        print(f"{lens}: {L['old']} -> {L['new']} (kept {L['kept']}, +{L['added']}, -{L['removed']}) {L['reasons']}")
    (OUT / f"build_diff_{old}_{new}.json").write_text(json.dumps(summ, indent=1))
    if rows:
        with open(OUT / f"build_diff_{old}_{new}.tsv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t")
            w.writeheader()
            w.writerows(rows)
    print(f"wrote {OUT / f'build_diff_{old}_{new}.json'} and .tsv ({len(rows)} rows)")


if __name__ == "__main__":
    main(*sys.argv[1:3])
