"""Export-derived worklists for the MeDIC issues (experiments/out/v2/medic_issues/).

Reads the pinned latest MEDIC export directly (no reconciliation), so every row is in
MeDIC's own subject/object ids. The audit-derived worklists (medic_load_tiers.tsv,
fp_audit.json) come from audit_tiers.py / audit_report.py; the round-2 TSVs
(contraindication_sample_audit, recall_gap_candidates, previous_release_dropped_but_correct)
were copied in from the 2026-10-01 analysis.

Run:  uv run python -m experiments.medic_issue_worklists
"""
from __future__ import annotations

import collections
import csv
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INP = ROOT / "data" / "inputs" / "medic" / "new"
OUT = Path(__file__).resolve().parent / "out" / "v2" / "medic_issues"
VACCINE = re.compile(r"vaccine|toxoid|immune globulin|antigen|polysaccharide", re.I)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    E = [json.loads(line) for line in open(INP / "medic_edges.jsonl")]
    N = {}
    for line in open(INP / "medic_nodes.jsonl"):
        n = json.loads(line)
        N[n["id"]] = n
    nm = lambda i: N.get(i, {}).get("name") or ""  # noqa: E731
    T = [e for e in E if e["predicate"] == "biolink:treats"]
    C = [e for e in E if e["predicate"] == "biolink:contraindicated_in"]

    def write(name, rows, cols):
        with open(OUT / name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, delimiter="\t", extrasaction="ignore")
            w.writeheader()
            w.writerows(rows)
        print(f"  {name}: {len(rows)} rows")

    # issue 05: indication/contraindication self-clashes; negated or EXCLUDED edges shipped as treats
    tp = {(e["subject"], e["object"]): e for e in T}
    cp = {(e["subject"], e["object"]): e for e in C}
    write("self_clash_pairs.tsv",
          [{"subject": s, "drug": nm(s), "object": o, "disease": nm(o),
            "treats_text": (tp[(s, o)].get("supporting_text") or "")[:300],
            "contra_text": (cp[(s, o)].get("supporting_text") or "")[:300]}
           for s, o in sorted(set(tp) & set(cp), key=lambda k: nm(k[0]))],
          ["subject", "drug", "object", "disease", "treats_text", "contra_text"])
    write("negated_or_excluded_treats_edges.tsv",
          [{"subject": e["subject"], "drug": nm(e["subject"]), "object": e["object"], "disease": nm(e["object"]),
            "reliability": e.get("medic_pair_reliability"), "flags": ";".join(e.get("medic_assertion_flags") or []),
            "supporting_text": (e.get("supporting_text") or "")[:300]}
           for e in T if e.get("medic_negation_detected") or e.get("medic_pair_reliability") == "EXCLUDED"],
          ["subject", "drug", "object", "disease", "reliability", "flags", "supporting_text"])

    # issue 06: unnamed stubs used by edges; thesaurus-inverted / abbreviated display names
    literals, cnt = collections.defaultdict(set), collections.Counter()
    for e in E:
        literals[e["object"]].add(e.get("original_object", ""))
        cnt[e["object"]] += 1
    write("unnamed_stub_diseases.tsv",
          sorted([{"id": i, "edges": cnt[i], "source_literals": "; ".join(sorted(literals[i])[:5])}
                  for i in N if N[i].get("medic_stub") and not N[i].get("name") and cnt[i]],
                 key=lambda r: -r["edges"]),
          ["id", "edges", "source_literals"])
    write("inverted_or_abbreviated_disease_names.tsv",
          sorted([{"id": i, "name": N[i]["name"], "edges": cnt[i]} for i in N
                  if N[i].get("name") and cnt[i]
                  and (re.match(r"^[A-Z][a-z]+, [A-Z]", N[i]["name"]) or re.fullmatch(r"[A-Z]{2,6}", N[i]["name"]))],
                 key=lambda r: -r["edges"]),
          ["id", "name", "edges"])

    # issue 03: drug ids the Node Normalizer doesn't know
    nn = json.loads((ROOT / "data" / "nodenorm_cache.json").read_text())
    subs = collections.Counter(e["subject"] for e in T)
    write("drug_ids_unknown_to_node_normalizer.tsv",
          sorted([{"id": s, "name": nm(s), "treats_assertions": n, "prefix": s.split(":")[0]}
                  for s, n in subs.items() if not nn.get(s)], key=lambda r: -r["treats_assertions"]),
          ["id", "name", "treats_assertions", "prefix"])

    # issue 07: text cut mid cross-reference but not flagged truncated
    write("text_cut_but_not_flagged_truncated.tsv",
          [{"id": e["id"], "subject": e["subject"], "drug": nm(e["subject"]), "object": e["object"],
            "disease": nm(e["object"]), "predicate": e["predicate"], "text_tail": (e.get("supporting_text") or "")[-120:]}
           for e in E if not e.get("medic_supporting_text_truncated")
           and isinstance(e.get("supporting_text"), str) and e["supporting_text"].rstrip().endswith("[see")],
          ["id", "subject", "drug", "object", "disease", "predicate", "text_tail"])

    # issue 12: vaccine-like products exported as treats
    write("vaccine_like_treats_edges.tsv",
          [{"subject": e["subject"], "drug": nm(e["subject"]), "object": e["object"], "disease": nm(e["object"]),
            "authority": e.get("medic_authority")}
           for e in T if VACCINE.search(nm(e["subject"])) or "J07" in (N[e["subject"]].get("medic_atc_level2") or "")],
          ["subject", "drug", "object", "disease", "authority"])


if __name__ == "__main__":
    main()
