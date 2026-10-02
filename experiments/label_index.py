"""Build local, independently-sourced label indexes for the indication audit.

Two regulators, fetched by us (never from a source's own snippet):

* **FDA** -- the openFDA drug-label bulk export (every SPL on DailyMed). Indexed by UNII
  (``openfda.unii``). Per UNII we keep the *deduplicated union* of indication text across
  every label, so an indication that only lives on one product's SPL isn't missed (the v1
  audit needed a separate multi-SPL recheck for this). Single-ingredient labels are kept
  apart from combination products so a drug isn't credited with a combo's indication
  unless that's all there is.
  Homeopathic labels are excluded.
* **EMA** -- the EMA "medicines output" report: centrally authorised human medicines with
  their EPAR therapeutic-indication text, indexed by normalized INN / active substance.

Run (after downloading the inputs, see experiments/README.md):
    uv run python -m experiments.label_index
Writes data/inputs/labels/fda_index.json.gz and ema_index.json.gz.
"""
from __future__ import annotations

import gzip
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "data" / "inputs" / "labels"
FDA_INDEX = LABELS / "fda_index.json.gz"
EMA_INDEX = LABELS / "ema_index.json.gz"

_WS = re.compile(r"\s+")
_HOMEOPATHIC = re.compile(r"homeopath|\bHPUS\b", re.IGNORECASE)


def _clean(parts) -> str:
    return _WS.sub(" ", " ".join(parts or [])).strip()


def _norm_para(t: str) -> str:
    """Dedup key for a paragraph: case/space/punctuation-insensitive, brand-agnostic-ish."""
    return re.sub(r"[^a-z0-9 ]", "", t.lower())[:400]


def norm_name(s: str) -> str:
    return _WS.sub(" ", re.sub(r"[^a-z0-9 ]", " ", (s or "").lower())).strip()


def build_fda() -> dict:
    """{UNII: {"single": [...texts], "combo": [...texts], "contra": [...], "warn": [...],
    "names": [...], "n_labels": int}} -- texts deduplicated."""
    idx: dict[str, dict] = defaultdict(lambda: {"single": {}, "combo": {}, "contra": {},
                                               "warn": {}, "names": set(), "n_labels": 0,
                                               "setids": []})
    zips = sorted((LABELS / "openfda").glob("*.zip"))
    n = skipped = 0
    for z in zips:
        with zipfile.ZipFile(z) as zf:
            for member in zf.namelist():
                data = json.loads(zf.read(member))
                for lab in data.get("results", []):
                    of = lab.get("openfda") or {}
                    uniis = sorted(set(of.get("unii") or []))
                    ind = _clean(lab.get("indications_and_usage"))
                    if not uniis or not ind:
                        continue
                    if _HOMEOPATHIC.search(json.dumps(lab)):
                        # homeopathic dilutions share UNIIs with real substances and make
                        # sweeping "temporarily relieves..." claims; never evidence here
                        skipped += 1
                        continue
                    n += 1
                    contra = _clean(lab.get("contraindications"))
                    warn = _clean(lab.get("warnings_and_cautions") or lab.get("warnings")
                                  or lab.get("boxed_warning"))
                    kind = "single" if len(uniis) == 1 else "combo"
                    names = set(of.get("generic_name") or []) | set(of.get("substance_name") or [])
                    for u in uniis:
                        e = idx[u]
                        e[kind].setdefault(_norm_para(ind), ind)
                        if contra:
                            e["contra"].setdefault(_norm_para(contra), contra)
                        if warn:
                            e["warn"].setdefault(_norm_para(warn), warn)
                        e["names"] |= {x.lower() for x in names}
                        e["n_labels"] += 1
                        if len(e["setids"]) < 5 and lab.get("set_id"):
                            e["setids"].append(lab["set_id"])
        print(f"  {z.name}: {n} labels indexed so far ({skipped} homeopathic skipped)", flush=True)
    out = {}
    for u, e in idx.items():
        out[u] = {"single": list(e["single"].values()), "combo": list(e["combo"].values()),
                  "contra": list(e["contra"].values())[:6], "warn": list(e["warn"].values())[:4],
                  "names": sorted(e["names"])[:20], "n_labels": e["n_labels"],
                  "setids": e["setids"]}
    return out


def build_ema() -> dict:
    """{normalized INN/substance: [{"name", "inn", "indication", "number", "area"}]}"""
    import openpyxl

    path = LABELS / "ema" / "medicines_output_medicines_report_en.xlsx"
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb.active
    rows = ws.iter_rows(values_only=True)
    header = None
    for r in rows:  # the report has a preamble; the header row names the INN column
        if r and any(isinstance(c, str) and "International non-proprietary name" in c for c in r):
            header = [str(c or "").strip() for c in r]
            break
    if header is None:
        raise SystemExit("EMA report: header row not found")
    col = {h: i for i, h in enumerate(header)}

    def find(*keys):
        for h, i in col.items():
            if all(k.lower() in h.lower() for k in keys):
                return i
        raise KeyError(keys)

    c_cat, c_name = find("Category"), find("Name of medicine")
    c_inn, c_sub = find("International non-proprietary name"), find("Active substance")
    c_ind, c_status = find("Therapeutic indication"), find("Medicine status")
    c_num, c_area = find("EMA product number"), find("Therapeutic area")
    out: dict[str, list] = defaultdict(list)
    for r in rows:
        if not r or (r[c_cat] or "").strip().lower() != "human":
            continue
        if (r[c_status] or "").strip().lower() != "authorised":
            continue
        ind = _WS.sub(" ", str(r[c_ind] or "")).strip()
        if not ind:
            continue
        rec = {"name": r[c_name], "inn": r[c_inn], "indication": ind[:6000],
               "number": r[c_num], "area": r[c_area]}
        keys = {norm_name(r[c_inn])} | {norm_name(s) for s in re.split(r"[,/;]| and ", str(r[c_sub] or ""))}
        for k in keys - {""}:
            out[k].append(rec)
    return dict(out)


def main() -> None:
    print("indexing openFDA bulk labels...")
    fda = build_fda()
    with gzip.open(FDA_INDEX, "wt") as f:
        json.dump(fda, f)
    print(f"wrote {FDA_INDEX} ({len(fda)} UNIIs)")
    print("indexing EMA medicines report...")
    ema = build_ema()
    with gzip.open(EMA_INDEX, "wt") as f:
        json.dump(ema, f)
    print(f"wrote {EMA_INDEX} ({len(ema)} substance keys)")


if __name__ == "__main__":
    main()
