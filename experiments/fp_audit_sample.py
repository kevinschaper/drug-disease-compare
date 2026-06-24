"""Draw a seeded random sample of asserted drug->disease edges per source and attach the
live FDA label text, so subagents can adjudicate each (target vs false-positive type) and
we can compute a measured false-positive / precision rate instead of eyeballing.

Sources:
  dakp-approved : dakp='exact' AND dakp_status='approved_for_condition'  (all FDA)
  medic         : medic='exact' AND the pair is [FDA]-tagged in medic_evidence
                  (so EU/Japan-only approvals aren't unfairly judged against the FDA label)

Output: experiments/out/fp_sample.jsonl  (one record per sampled edge, with label text)
Run:  uv run python -m experiments.fp_audit_sample --n 120
"""
from __future__ import annotations

import argparse
import json
import random
import time
from pathlib import Path

import httpx
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parent.parent
PAIRS = ROOT / "src" / "data" / "pairs.parquet"
BYDRUG = ROOT / "src" / "data" / "by_drug.json"
MEDEV = ROOT / "src" / "data" / "medic_evidence.parquet"
OUT = Path(__file__).resolve().parent / "out"
CACHE = OUT / "openfda_cache.json"
SEED = 20260623


def fda_tagged_pairs() -> set:
    me = pq.read_table(MEDEV).to_pydict()
    return {(me["drug"][i], me["disease"][i]) for i in range(len(me["drug"]))
            if me["evidence"][i] and '"agency": "FDA"' in me["evidence"][i]}


def medic_fda_snippet() -> dict:
    me = pq.read_table(MEDEV).to_pydict()
    out = {}
    for i in range(len(me["drug"])):
        ev = me["evidence"][i]
        if not ev:
            continue
        try:
            for e in json.loads(ev):
                if e.get("agency") == "FDA":
                    out[(me["drug"][i], me["disease"][i])] = e.get("text", "")
                    break
        except ValueError:
            pass
    return out


def candidates(source: str):
    t = pq.read_table(PAIRS, columns=["drug", "drug_label", "disease", "disease_label",
                                      "medic", "dakp", "dakp_status"]).to_pydict()
    rows = []
    fda = fda_tagged_pairs() if source == "medic" else None
    for i in range(len(t["drug"])):
        k = (t["drug"][i], t["disease"][i])
        if source == "dakp-approved":
            ok = t["dakp"][i] == "exact" and t["dakp_status"][i] == "approved_for_condition"
        else:  # medic, FDA-tagged only
            ok = t["medic"][i] == "exact" and k in fda
        if ok:
            rows.append({"drug": k[0], "drug_label": t["drug_label"][i],
                         "disease": k[1], "disease_label": t["disease_label"][i]})
    return rows


def _pack(d: dict, method: str) -> dict:
    return {
        "indications": " ".join(d.get("indications_and_usage", []) or [])[:2400],
        "contraindications": " ".join(d.get("contraindications", []) or [])[:900],
        "warnings": " ".join(d.get("warnings_and_cautions", d.get("warnings", [])) or [])[:600],
        "brand": (d.get("openfda", {}).get("brand_name") or [""])[0],
        "matched": True, "method": method,
    }


def fetch_label(unii: str, name: str, cache: dict, client: httpx.Client) -> dict:
    """Strict matching: only accept a label we can confirm is the SAME substance.

    1) UNII search (exact substance). 2) name search accepted ONLY if the returned
    label's openfda.unii contains our UNII (when we have one), or — with no UNII — its
    generic/substance name actually contains our drug name. Otherwise reject (the loose
    name fallback was matching wrong/OTC/homeopathic products and inflating "not-in-label").
    """
    key = f"{unii or ''}|{name}"
    if key in cache:
        return cache[key]
    none = {"indications": "", "contraindications": "", "warnings": "", "brand": "", "matched": False, "method": "none"}
    res = none

    def query(term):
        try:
            r = client.get(f"https://api.fda.gov/drug/label.json?search={term}&limit=1")
            if r.status_code == 200:
                return (r.json().get("results") or [None])[0]
        except Exception:
            return None
        return None

    if unii:
        d = query(f'openfda.unii:"{unii}"')
        if d and (d.get("indications_and_usage")):
            res = _pack(d, "unii")
    if not res["matched"]:
        d = query(f'openfda.generic_name:"{name}"')
        if d and d.get("indications_and_usage"):
            of = d.get("openfda", {})
            uniis = [u.upper() for u in of.get("unii", [])]
            names = " ".join(of.get("generic_name", []) + of.get("substance_name", [])).lower()
            if (unii and unii.upper() in uniis) or (not unii and name.lower() in names):
                res = _pack(d, "name-verified")
    cache[key] = res
    time.sleep(0.25)
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120, help="sample size per source")
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() else {}
    unii = {d["drug"]: d.get("drug_unii", "") for d in json.loads(BYDRUG.read_text())}
    msnip = medic_fda_snippet()
    rng = random.Random(SEED)

    records = []
    with httpx.Client(timeout=30, follow_redirects=True, headers={"Accept": "application/json"}) as client:
        for source in ("dakp-approved", "medic"):
            pool = candidates(source)
            sample = rng.sample(pool, min(args.n, len(pool)))
            print(f"{source}: pool={len(pool)} sampled={len(sample)}", flush=True)
            for j, e in enumerate(sample):
                lab = fetch_label(unii.get(e["drug"], ""), e["drug_label"], cache, client)
                records.append({
                    "id": f"{source}-{j}", "source": source,
                    "drug": e["drug"], "drug_label": e["drug_label"],
                    "disease": e["disease"], "disease_label": e["disease_label"],
                    "label_matched": lab["matched"], "label_method": lab.get("method", "none"),
                    "label_brand": lab.get("brand", ""),
                    "indications": lab["indications"], "contraindications": lab["contraindications"],
                    "warnings": lab["warnings"],
                    "medic_fda_snippet": msnip.get((e["drug"], e["disease"]), "") if source == "medic" else "",
                })
                if (j + 1) % 25 == 0:
                    CACHE.write_text(json.dumps(cache))
                    print(f"  {source} {j+1}/{len(sample)}", flush=True)
    CACHE.write_text(json.dumps(cache))
    out = OUT / "fp_sample.jsonl"
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records))
    matched = sum(1 for r in records if r["label_matched"])
    print(f"\nwrote {out} : {len(records)} edges, {matched} with an FDA label "
          f"({len(records)-matched} no-label, excluded from rate denominator)")


if __name__ == "__main__":
    main()
