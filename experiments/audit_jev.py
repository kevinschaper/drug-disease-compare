"""Indication audit (v2): Jev (TypeSafe System One) adjudication.

Jev answers typed questions about a ``state`` with calibrated probabilities. For every edge
we send the same independently-fetched regulator text the Claude adjudicators see, and ask,
in parallel within one request:

* ``verdict`` -- a Choice over the full audit rubric (TARGET / FP1..FP7 / UNSURE)
* three atomic Nouls (Jev's docs recommend decomposing judgments into literal questions):
    - ``mentioned``  : is DISEASE (or a synonym / subtype) mentioned in the indication text?
    - ``indicated``  : does the indication text state the drug treats/prevents DISEASE?
    - ``negated``    : does the text say the drug is NOT indicated / not established for it?

Two passes:
* ``--sample``     -- the 300-edge gold sample (compared with the Claude adjudication)
* ``--population`` -- every eligible edge (~15k), the full-population screen

Results append to experiments/out/v2/jev_<pass>.jsonl and resume on rerun. Needs
TYPESAFE_API_KEY. Model pinned to a versioned id so a moving alias can't shift answers.

Run:  uv run --with typesafe-sdk python -m experiments.audit_jev --sample
"""
from __future__ import annotations

import argparse
import asyncio
import gzip
import json
from pathlib import Path

from experiments.audit_sample import OUT, attach_text

MODEL = "jev-1.13.0"
CONCURRENCY = 16

VERDICT_CRITERIA = {
    "TARGET": "The indication text names `disease` (or an exact synonym, or a more specific "
              "subtype of an indicated condition, or an item in a list of indicated "
              "conditions) as something `drug` treats, prevents, or manages.",
    "FP1_setting": "`disease` appears in the indication only as the setting, population, or "
                   "background (e.g. 'reduce risk of MI in patients with coronary heart "
                   "disease', a diagnostic use, or supportive care for an underlying illness), "
                   "not as the condition treated.",
    "FP2_symptom_swap": "The text treats a symptom or manifestation, and `disease` is the "
                        "underlying disease rather than what is treated (or the reverse).",
    "FP3_cross_section": "`disease` appears only in contraindications or warnings, not in the "
                         "indications.",
    "FP4_overbroad": "`disease` is a whole disease class or organ-system category much broader "
                     "than the specific condition indicated (e.g. label 'metastatic breast "
                     "cancer', disease 'cancer').",
    "FP5_negation": "The text explicitly says `drug` is not indicated, not established, or not "
                    "recommended for `disease`.",
    "FP7_notintext": "`disease`, its synonyms, subtypes, and close parents are not mentioned "
                     "anywhere in the text; nothing supports the claim.",
    "UNSURE": "The text is empty, fragmentary, or about an unrelated product, so no judgment "
              "is possible.",
}


def questions():
    from typesafe_sdk import Choice, Noul

    return {
        "verdict": Choice(
            instructions="According only to the regulator text (`fda_indications`, "
                         "`ema_indications`, and for cross-section checks "
                         "`fda_contraindications` / `fda_warnings`), is `disease` a genuine "
                         "indication of `drug`? Pick the single best category.",
            criteria=VERDICT_CRITERIA,
        ),
        "mentioned": Noul(
            instructions="Is `disease`, or a synonym or more specific subtype of it, mentioned "
                         "in `fda_indications` or `ema_indications`?"),
        "indicated": Noul(
            instructions="Do `fda_indications` or `ema_indications` state that `drug` is used to "
                         "treat, prevent, or manage `disease` (or a synonym or more specific "
                         "subtype of it)?"),
        "negated": Noul(
            instructions="Does the text explicitly say `drug` is not indicated, not established, "
                         "or not recommended for `disease`?"),
    }


def state_of(r: dict) -> dict:
    s = {"drug": r["drug_label"], "disease": r["disease_label"],
         "fda_indications": r["fda_indications"], "ema_indications": r["ema_indications"],
         "fda_contraindications": r["fda_contraindications"], "fda_warnings": r["fda_warnings"]}
    if r.get("fda_combo_only"):
        s["note"] = "fda_indications come only from combination products"
    return {k: v for k, v in s.items() if v}


async def run(records: list[dict], out_path: Path) -> None:
    from typesafe_sdk import AsyncTypeSafeClient

    done = set()
    if out_path.exists():
        done = {json.loads(line)["id"] for line in out_path.open()}
    todo = [r for r in records if r["id"] not in done]
    print(f"{len(done)} already done, {len(todo)} to go", flush=True)
    sem = asyncio.Semaphore(CONCURRENCY)
    qs = questions()
    lock = asyncio.Lock()
    n = 0
    usage = 0
    async with AsyncTypeSafeClient(model=MODEL) as client:
        async def one(r):
            nonlocal n, usage
            async with sem:
                try:
                    resp = await client.system_one(state=state_of(r), questions=qs)
                except Exception as e:  # keep going; failures are retried on rerun
                    print(f"  fail {r['id']}: {e}", flush=True)
                    return
            v = resp.choices["verdict"]
            row = {"id": r["id"], "model": resp.model,
                   "verdict": v.choice, "confidence": round(v.confidence, 4),
                   "probs": {k: round(p, 4) for k, p in v.probabilities.items()},
                   **{k: round(resp.nouls[k].noul, 4) for k in ("mentioned", "indicated", "negated")}}
            async with lock:
                with out_path.open("a") as f:
                    f.write(json.dumps(row) + "\n")
                n += 1
                usage += getattr(resp.usage, "input_tokens", 0) or 0
                if n % 500 == 0:
                    print(f"  {n}/{len(todo)}  ({usage/1e6:.1f}M input tokens)", flush=True)
        await asyncio.gather(*(one(r) for r in todo))
    print(f"done: {n} new, {usage/1e6:.2f}M input tokens (~${usage * 0.042 / 1e6:.2f})")


def main() -> None:
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--sample", action="store_true")
    g.add_argument("--population", action="store_true")
    args = ap.parse_args()
    if args.sample:
        recs = [json.loads(line) for line in open(OUT / "sample.jsonl")]
        out = OUT / "jev_sample.jsonl"
    else:
        with gzip.open(OUT / "evidence.json.gz", "rt") as f:
            ev = json.load(f)
        recs = []
        for line in open(OUT / "population.jsonl"):
            r = json.loads(line)
            recs.append({**r, **attach_text(r, ev[r["drug"]])})
        out = OUT / "jev_population.jsonl"
    asyncio.run(run(recs, out))


if __name__ == "__main__":
    main()
