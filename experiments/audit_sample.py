"""Indication audit (v2): build independent label evidence for every asserted edge, and
draw a seeded random sample per source for gold-standard adjudication.

What is judged
--------------
* **medic**          -- ``medic='exact'`` indication pairs (MeDIC redesign).
* **dakp-approved**  -- ``dakp='exact' AND dakp_status='approved_for_condition'``.

Each pair is checked against regulator text **we fetched ourselves** (label_index.py),
never against a source's own snippet:

* FDA -- union of indication text across every SPL for the drug's substance: labels carrying
  the drug's own UNIIs **plus** every label whose substance shares its FDA/GSRS active moiety
  (salt / hydrate / ester forms -- gemcitabine HCl for gemcitabine, cipro HCl tablets for the
  ciprofloxacin injection). ``fda_method`` records whether any exact-UNII label was found
  (``unii``) or only moiety siblings (``moiety``). Combination-product labels are included
  (Celestone is a two-salt betamethasone combo) and flagged when they're the only source.
  Missing evidence can only ever produce a false "not in label", so matching errs wide.
* EMA -- EPAR therapeutic-indication text for centrally authorised products whose INN (or
  active substance) matches the drug's name or its moiety's name exactly.

Which regulators an edge cites: MEDIC names them per pair (FDA/EMA/PMDA/CDSCO); for DAKP we
read its application numbers (NDA/ANDA/BLA -> FDA, EMEA/H/C -> EMA).

Eligibility & fairness
----------------------
An edge is **eligible** if we hold independent text for at least one regulator it cites.
``absence_ok`` says whether we hold text for *every* cited regulator: only then may a
"not in the label" verdict (FP7) count as an error -- otherwise the indication could live in
text we don't have (e.g. a PMDA-only approval), and an FP7 there is scored unverifiable.

Outputs (experiments/out/v2/)
-----------------------------
* ``evidence.json.gz``   -- per drug: matched FDA/EMA text + match method
* ``population.jsonl``   -- every eligible edge (no text; joins evidence by drug)
* ``sample.jsonl``       -- seeded random sample per source, with text attached

Run:  PYTHONPATH=pipeline:. uv run python -m experiments.audit_sample --n 300 [--release old]
"""
from __future__ import annotations

import argparse
import gzip
import json
import random
import re
from collections import Counter
from pathlib import Path

import pyarrow.parquet as pq

from experiments.label_index import EMA_INDEX, FDA_INDEX, norm_name

APPROVED = "approved_for_condition"

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "src" / "data"
NN_CACHE = ROOT / "data" / "nodenorm_cache.json"
GROUP_CACHE = ROOT / "data" / "drug_groups_cache.json"
OUT = Path(__file__).resolve().parent / "out" / "v2"
SEED = 20261002
SOURCES = ("medic", "dakp-approved")
JUDGEABLE = {"FDA", "EMA"}

# evidence caps (chars). Texts mentioning the disease are packed first so truncation can't
# manufacture a "not in label" call for an indication that was present but cut off.
IND_CAP = 9000
SIDE_CAP = 1500


def _clique_uniis(nn: dict, curie: str) -> list[str]:
    raw = nn.get(curie) or {}
    ids = [raw.get("id", {}).get("identifier", "")] + [
        e["identifier"] for e in raw.get("equivalent_identifiers", [])]
    out = []
    for i in ids:
        if i.startswith("UNII:") and i[5:] not in out:
            out.append(i[5:])
    return out


def _moiety_map(groups: dict) -> dict[str, set[str]]:
    """UNII -> {itself + every active moiety GSRS lists}, bare ions dropped.

    All listed moieties are kept, not just one: GSRS gives gemcitabine's moiety as its
    phosphorylated metabolites while gemcitabine HCl's is gemcitabine, so a single pick would
    never connect the salt label to the parent drug. Ions (<3 heavy atoms: Na+, K+, Cl-) are
    excluded so they can't link every salt of a counter-ion together.
    """
    from drug_edge_compare.drug_groups import heavy_atoms

    def ion(u):
        f = groups.get(f"gsrs:formula:{u}")
        ha = heavy_atoms(f) if isinstance(f, str) else None
        return ha is not None and ha < 3

    m: dict[str, set[str]] = {}
    for k, v in groups.items():
        if k.startswith("gsrs:moiety:"):
            u = k.split(":", 2)[2]
            m[u] = {u} | {p[0] for p in (v if isinstance(v, list) else []) if not ion(p[0])}
    return m


_SEG = re.compile(r"(?<=[.;:])\s+(?=[A-Z0-9(•])|\s*[•▪●]\s*|\s+(?=\(\d+(?:\.\d+)?\)\s)")


def _pack(texts: list[str], keywords: set[str], cap: int) -> str:
    """Pack many labels' text into ``cap`` chars without losing distinct content.

    Generic labels repeat each other almost verbatim, so we split every text into
    sentence / bullet segments and keep each distinct segment once. Texts mentioning the
    disease go first, and within the budget every *new* segment of every text is kept in
    its original order, so a list item ("• typhoid fever") still sits under its lead-in.
    """
    def hit(t):
        tl = t.lower()
        return any(k in tl for k in keywords)
    ordered = sorted(texts, key=lambda t: (not hit(t), -len(t)))
    seen, blocks, n = set(), [], 0
    # pass 1: keyword-bearing segments from every text; pass 2: everything else
    for want_hit in (True, False):
        for t in ordered:
            segs = [x.strip() for x in _SEG.split(t) if x and x.strip()]
            new = []
            for sgm in segs:
                k = re.sub(r"[^a-z0-9]", "", sgm.lower())
                if not k or k in seen or hit(sgm) != want_hit:
                    continue
                if n + len(sgm) > cap:
                    break
                seen.add(k)
                new.append(sgm)
                n += len(sgm) + 1
            if new:
                blocks.append(" ".join(new))
            if n >= cap:
                break
    return "\n---\n".join(blocks)


def _keywords(disease_label: str) -> set[str]:
    toks = {t for t in re.split(r"[^a-z0-9]+", disease_label.lower()) if len(t) >= 4}
    return toks - {"disease", "disorder", "syndrome", "type", "chronic", "acute", "with", "infection"}


class Evidence:
    def __init__(self):
        with gzip.open(FDA_INDEX, "rt") as f:
            self.fda = json.load(f)
        with gzip.open(EMA_INDEX, "rt") as f:
            self.ema = json.load(f)
        self.nn = json.loads(NN_CACHE.read_text())
        groups = json.loads(GROUP_CACHE.read_text())
        self.moiety = _moiety_map(groups)
        # reverse: any of a label UNII's {self, moieties} -> that label UNII
        self.by_moiety: dict[str, list[str]] = {}
        for u in self.fda:
            for m in self.moiety.get(u, {u}):
                self.by_moiety.setdefault(m, []).append(u)
        self._cache: dict[str, dict] = {}

    def drug(self, drug: str, drug_label: str, group: str, group_label: str) -> dict:
        if drug in self._cache:
            return self._cache[drug]
        uniis = _clique_uniis(self.nn, drug)
        direct = [u for u in uniis if u in self.fda]
        moieties = {m for u in uniis for m in self.moiety.get(u, {u})}
        if group.startswith("UNII:"):
            moieties.add(group[5:])
        via = sorted({u for m in moieties for u in self.by_moiety.get(m, [])} - set(direct))
        hits = direct + via
        method = "unii" if direct else ("moiety" if via else "none")
        single = [t for u in hits for t in self.fda[u]["single"]]
        combo = [t for u in hits for t in self.fda[u]["combo"]]
        fda = {
            "method": method, "uniis": hits,
            "indications": single + combo, "combo_only": bool(combo and not single),
            "single": single, "combo": combo,
            "contra": [t for u in hits for t in self.fda[u]["contra"]][:6],
            "warn": [t for u in hits for t in self.fda[u]["warn"]][:3],
            "setids": [s for u in hits for s in self.fda[u]["setids"]][:5],
        }
        names = {norm_name(drug_label), norm_name(group_label)} - {""}
        ema_recs = [r for n in names for r in self.ema.get(n, [])]
        seen, ema = set(), []
        for r in ema_recs:
            if r["number"] not in seen:
                seen.add(r["number"])
                ema.append(r)
        ev = {"fda": fda if method != "none" and fda["indications"] else None,
              "ema": {"products": [{"name": r["name"], "number": r["number"]} for r in ema[:8]],
                      "indications": [r["indication"] for r in ema[:8]]} if ema else None}
        self._cache[drug] = ev
        return ev


def _dakp_regulators(ev_json: str) -> set[str]:
    if not ev_json:
        return set()
    regs = set()
    for a in json.loads(ev_json).get("fda", []):
        if a.startswith(("NDA", "ANDA", "BLA")):
            regs.add("FDA")
        elif a.startswith("EMEA/"):
            regs.add("EMA")
    return regs


def candidates() -> list[dict]:
    t = pq.read_table(DATA / "pairs.parquet", columns=[
        "drug", "drug_label", "disease", "disease_label", "disease_prefix", "medic", "dakp",
        "dakp_status", "dakp_evidence", "drug_group", "drug_group_label",
        "medic_reliability"]).to_pylist()
    me = {(r["drug"], r["disease"]): [e["agency"] for e in json.loads(r["evidence"])]
          for r in pq.read_table(DATA / "medic_evidence.parquet").to_pylist()}
    rows = []
    for r in t:
        base = {k: r[k] for k in ("drug", "drug_label", "disease", "disease_label",
                                  "disease_prefix", "drug_group", "drug_group_label")}
        if r["medic"] == "exact":
            rows.append({**base, "source": "medic", "cited": sorted(me.get((r["drug"], r["disease"]), [])),
                         "medic_reliability": r["medic_reliability"]})
        if r["dakp"] == "exact" and r["dakp_status"] == "approved_for_condition":
            rows.append({**base, "source": "dakp-approved",
                         "cited": sorted(_dakp_regulators(r["dakp_evidence"]))})
    return rows


def candidates_from_release(version: str) -> list[dict]:
    """Indication pairs of a release, built straight from its source files.

    Used for the *previous* releases (the site's pairs.parquet only holds the latest): the
    same loaders, reconciler (incl. exact-name drug repair) and moiety grouping as the build,
    so a pair here is keyed exactly as it would be in pairs.parquet.
    """
    from drug_edge_compare import cli, compare
    from drug_edge_compare.drug_groups import moiety_grouper
    from drug_edge_compare.mondo import MondoGraph
    from drug_edge_compare.nodenorm import NodeNorm

    edges = cli._load_edges(version)
    nn = NodeNorm(cli.CACHE)
    nn.warm(e["subject"] for e in edges)
    nn.warm(e["object"] for e in edges)
    mondo = MondoGraph(cli.INPUTS / "mondo_edges.tsv", cli.INPUTS / "mondo_nodes.tsv")
    rec, _ = cli._reconciler(nn, mondo, edges)
    treat, _ = compare.build_pairs(edges, rec)
    clients, grouper = moiety_grouper(cli.DRUG_GROUP_CACHE)

    def base(drug, dis, m):
        g = grouper.group(compare.named_clique(rec, drug))
        return {"drug": drug, "drug_label": m["drug_label"], "disease": dis,
                "disease_label": m["disease_label"], "disease_prefix": m["disease_prefix"],
                "drug_group": g.group_id, "drug_group_label": g.group_label}

    rows = []
    for (drug, dis), m in treat["medic"].items():
        rows.append({**base(drug, dis, m), "source": "medic",
                     "cited": sorted(m.get("medic_evidence", {})),
                     "medic_reliability": m.get("reliability") or ""})
    for (drug, dis), m in treat["dakp"].items():
        if m["status"] != APPROVED:
            continue
        ev = json.dumps({"fda": m.get("fda_approvals", [])})
        rows.append({**base(drug, dis, m), "source": "dakp-approved",
                     "cited": sorted(_dakp_regulators(ev))})
    clients.save()
    return rows


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=150, help="gold sample size per source")
    ap.add_argument("--release", choices=("new", "old"), default="new",
                    help="latest releases (site pairs) or the previous releases (source files)")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    old = args.release == "old"
    sfx, idp, seed = ("_old", "old:", SEED + 1) if old else ("", "", SEED)
    ev = Evidence()
    pop, stats = [], Counter()
    for r in (candidates_from_release("old") if old else candidates()):
        e = ev.drug(r["drug"], r["drug_label"], r["drug_group"] or "", r["drug_group_label"] or "")
        have = {k.upper() for k in ("fda", "ema") if e[k]}
        cited = set(r["cited"])
        # DAKP doesn't always carry application numbers; its approvals come only from
        # FDA/EMA, so with none cited we judge against whatever we hold
        judge_against = (cited & have) if cited else have
        stats[(r["source"], "total")] += 1
        if not judge_against:
            stats[(r["source"], "no_text" if not have else "cited_unavailable")] += 1
            continue
        absence_ok = bool(cited) and cited <= have
        stats[(r["source"], "eligible")] += 1
        stats[(r["source"], "absence_ok")] += absence_ok
        pop.append({**r, "judge_against": sorted(judge_against), "absence_ok": absence_ok,
                    "fda_method": e["fda"]["method"] if e["fda"] else "none"})

    with gzip.open(OUT / f"evidence{sfx}.json.gz", "wt") as f:
        json.dump(ev._cache, f)
    with open(OUT / f"population{sfx}.jsonl", "w") as f:
        for i, r in enumerate(pop):
            r["id"] = f"{idp}{r['source']}:{r['drug']}|{r['disease']}"
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    # Two-stage draw so a larger --n *extends* an earlier sample instead of redrawing it:
    # stage 1 reproduces the original 150-per-source draw (one stream across sources, as
    # first run); stage 2 tops each source up from its remaining pool with its own stream.
    BASE = 150
    rng = random.Random(seed)
    pools = {src: sorted((r for r in pop if r["source"] == src), key=lambda r: r["id"])
             for src in SOURCES}
    drawn = {src: rng.sample(pools[src], min(BASE, args.n, len(pools[src]))) for src in SOURCES}
    for src in SOURCES:
        taken = {r["id"] for r in drawn[src]}
        rest = [r for r in pools[src] if r["id"] not in taken]
        extra = max(0, min(args.n, len(pools[src])) - len(drawn[src]))
        drawn[src] += random.Random(f"{seed}-extend-{src}").sample(rest, extra)
    sample = []
    for src in SOURCES:
        for j, r in enumerate(drawn[src]):
            sample.append({**r, "sid": f"{idp}{src}-{j}", "release": args.release,
                           **attach_text(r, ev._cache[r["drug"]])})
    with open(OUT / f"sample{sfx}.jsonl", "w") as f:
        for r in sample:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    for src in SOURCES:
        print(f"{src}: " + ", ".join(f"{k}={stats[(src, k)]}" for k in
              ("total", "eligible", "absence_ok", "no_text", "cited_unavailable")))
    print(f"wrote population ({len(pop)}) + sample ({len(sample)}) to {OUT}")


def attach_text(r: dict, e: dict) -> dict:
    """The label evidence an adjudicator sees for one edge (only the regulators judged)."""
    kw = _keywords(r["disease_label"])
    out = {"fda_indications": "", "fda_contraindications": "", "fda_warnings": "",
           "fda_combo_only": False, "ema_indications": ""}
    if "FDA" in r["judge_against"] and e["fda"]:
        f = e["fda"]
        out["fda_indications"] = _pack(f["indications"], kw, IND_CAP)
        out["fda_contraindications"] = _pack(f["contra"], kw, SIDE_CAP)
        out["fda_warnings"] = _pack(f["warn"], kw, SIDE_CAP)
        out["fda_combo_only"] = f["combo_only"]
    if "EMA" in r["judge_against"] and e["ema"]:
        out["ema_indications"] = _pack(e["ema"]["indications"], kw, IND_CAP // 2)
    return out


if __name__ == "__main__":
    main()
