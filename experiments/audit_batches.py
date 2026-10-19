"""Indication audit (v2): blind, batch and collect one review round.

Each round judges a set of sampled edges with two independent reviewers (A, B: different
batchings so a reviewer can't learn an edge's source or release from its neighbours), a
tie-breaker on every A<->B disagreement, and a co-ingredient check on every TARGET whose
evidence included combination-product labels. The reviewers are Claude subagents driven from
a session with ``audit_rubric.md``; this script only prepares their inputs and stays
deterministic, so a round can be rebuilt from ``sample*.jsonl`` + ``blind_key_<round>.json``.

    # 1. blind + batch (writes blind_key_<round>.json, batch<round>_{a,b}_<k>.json)
    uv run python -m experiments.audit_batches prepare --round 3 --prefix g --sids medic- --release new
    # 2. after reviewers A and B wrote claude<round>_{a,b}_<k>.json: tie-break inputs
    uv run python -m experiments.audit_batches tiebreak --round 3
    # 3. after the tie-breaker: co-ingredient check inputs
    uv run python -m experiments.audit_batches combo --round 3

Round history: round 1 = ``blind_key.json`` (e000-e299, first 150 latest edges/source, no
round number in file names); round 2 = ``blind_key_2.json`` (f000-f899); round 3 =
``blind_key_3.json`` (g000-g299, the 2026-10-13 MeDIC rebuild's fresh sample).
"""
from __future__ import annotations

import argparse
import glob
import gzip
import json
import random
from pathlib import Path

from experiments.audit_sample import OUT, _keywords, _pack, IND_CAP

TEXT = ("fda_indications", "fda_combo_only", "fda_contraindications", "fda_warnings",
        "ema_indications")


def load_sample(release: str) -> dict[str, dict]:
    fname = {"new": "sample.jsonl", "old": "sample_old.jsonl"}.get(release, f"sample_{release}.jsonl")
    return {r["sid"]: r for r in (json.loads(line) for line in open(OUT / fname))}


def key_file(rnd: int) -> Path:
    return OUT / ("blind_key.json" if rnd == 1 else f"blind_key_{rnd}.json")


def tag(rnd: int) -> str:
    return "" if rnd == 1 else str(rnd)


def prepare(args) -> None:
    sample = load_sample(args.release)
    rows = [r for sid, r in sample.items() if sid.startswith(args.sids)]
    rng = random.Random(f"blind-{args.round}")
    rng.shuffle(rows)
    key = {f"{args.prefix}{i:03d}": r["sid"] for i, r in enumerate(rows)}
    assert not key_file(args.round).exists(), f"{key_file(args.round)} exists"
    json.dump(key, open(key_file(args.round), "w"), indent=0)
    items = [{"id": bid, "drug": r["drug_label"], "disease": r["disease_label"],
              **{k: r[k] for k in TEXT}} for bid, r in zip(key, rows)]
    n = args.batches
    for rev, seed in (("a", "A"), ("b", "B")):
        order = items[:]
        random.Random(f"batch-{args.round}-{seed}").shuffle(order)
        for k in range(n):
            chunk = order[k::n]
            json.dump(chunk, open(OUT / f"batch{tag(args.round)}_{rev}_{k}.json", "w"),
                      ensure_ascii=False, indent=0)
    print(f"{len(items)} edges -> {key_file(args.round).name}, {n} batches x 2 reviewers")


def verdicts(rnd: int, rev: str) -> dict[str, dict]:
    out = {}
    for f in sorted(glob.glob(str(OUT / f"claude{tag(rnd)}_{rev}_*.json"))):
        for r in json.load(open(f)):
            out[r["id"]] = r
    return out


def batch_items(rnd: int) -> dict[str, dict]:
    out = {}
    for f in sorted(glob.glob(str(OUT / f"batch{tag(rnd)}_a_*.json"))):
        for r in json.load(open(f)):
            out[r["id"]] = r
    return out


def tiebreak(args) -> None:
    a, b, items = verdicts(args.round, "a"), verdicts(args.round, "b"), batch_items(args.round)
    missing = sorted(set(items) - set(a)) + sorted(set(items) - set(b))
    if missing:
        print(f"WARNING {len(missing)} edges lack a verdict: {missing[:10]}")
    dis = [{"id": i, "drug": items[i]["drug"], "disease": items[i]["disease"],
            "reviewer_1": {k: a[i].get(k, "") for k in ("verdict", "quote", "note")},
            "reviewer_2": {k: b[i].get(k, "") for k in ("verdict", "quote", "note")},
            **{k: items[i][k] for k in TEXT if k != "fda_combo_only"}}
           for i in items if i in a and i in b and a[i]["verdict"] != b[i]["verdict"]]
    n = max(1, (len(dis) + 24) // 25)
    for k in range(n):
        json.dump(dis[k::n], open(OUT / f"tiebreak{tag(args.round)}_input_{k}.json", "w"),
                  ensure_ascii=False, indent=0)
    print(f"{len(dis)} disagreements of {len(items)} -> {n} tie-break batch(es)")


def combo(args) -> None:
    """Every reference TARGET whose FDA evidence included combination labels, with the
    single-ingredient and combination text separated (rubric FP6)."""
    key = json.load(open(key_file(args.round)))
    sample = load_sample(args.release)
    a, b = verdicts(args.round, "a"), verdicts(args.round, "b")
    tb = {}
    for f in sorted(glob.glob(str(OUT / f"tiebreak{tag(args.round)}_[0-9]*.json"))):
        for r in json.load(open(f)):
            tb[r["id"]] = r
    with gzip.open(OUT / "evidence.json.gz", "rt") as f:
        ev = json.load(f)
    rows = []
    for bid, sid in key.items():
        if bid not in a or bid not in b:
            continue
        v = a[bid]["verdict"] if a[bid]["verdict"] == b[bid]["verdict"] else tb.get(bid, a[bid])["verdict"]
        r = sample[sid]
        e = ev.get(r["drug"], {}).get("fda")
        if v != "TARGET" or not e or not e["combo"] or "FDA" not in r["judge_against"]:
            continue
        kw = _keywords(r["disease_label"])
        rows.append({"id": bid, "drug": r["drug_label"], "disease": r["disease_label"],
                     "single_ingredient_indications": _pack(e["single"], kw, IND_CAP),
                     "combination_product_indications": _pack(e["combo"], kw, IND_CAP),
                     "ema_indications": r["ema_indications"]})
    n = max(1, (len(rows) + 39) // 40)
    for k in range(n):
        json.dump(rows[k::n], open(OUT / f"combo{tag(args.round)}_input_{k}.json", "w"),
                  ensure_ascii=False, indent=0)
    print(f"{len(rows)} TARGETs with combination-label evidence -> {n} batch(es)")


def main() -> None:
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("prepare")
    p.add_argument("--round", type=int, required=True)
    p.add_argument("--prefix", required=True, help="blind id prefix, unique per round")
    p.add_argument("--sids", required=True, help="sid prefix of the rows to review, e.g. medic-")
    p.add_argument("--release", default="new")
    p.add_argument("--batches", type=int, default=8)
    p.set_defaults(fn=prepare)
    for name, fn in (("tiebreak", tiebreak), ("combo", combo)):
        q = sub.add_parser(name)
        q.add_argument("--round", type=int, required=True)
        q.add_argument("--release", default="new")
        q.set_defaults(fn=fn)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
