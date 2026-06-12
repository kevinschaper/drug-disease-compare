"""Build the comparison artifacts consumed by the Observable Framework site."""
from __future__ import annotations

import json
from pathlib import Path

import click

from . import compare, load
from .mondo import MondoGraph
from .nodenorm import NodeNorm
from .reconcile import Reconciler

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "data" / "inputs"
CACHE = ROOT / "data" / "nodenorm_cache.json"
ARTIFACTS = ROOT / "src" / "data"


def _load_edges() -> list[dict]:
    medic = load.load_medic(INPUTS / "medic_edges.tsv")
    dakp = load.load_dakp(INPUTS / "dakp_edges.jsonl")
    dismech = load.load_dismech(INPUTS / "dismech_edges.jsonl")
    return medic + dakp + dismech


def _write(name: str, obj) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / name
    path.write_text(json.dumps(obj, indent=2))
    click.echo(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


def _write_parquet(name: str, rows: list[dict]) -> None:
    """Write a row list as Parquet (queried client-side via DuckDB-WASM)."""
    import pandas as pd

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / name
    pd.DataFrame(rows).to_parquet(path, index=False, compression="zstd")
    click.echo(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB, {len(rows)} rows)")


@click.group()
def cli() -> None:
    """drug-edge-compare pipeline."""


@cli.command()
def normalize() -> None:
    """Resolve every drug/disease CURIE through the Node Normalizer (warms cache)."""
    edges = _load_edges()
    curies = load.all_curies(edges)
    click.echo(f"resolving {len(curies)} distinct CURIEs through the Node Normalizer...")
    nn = NodeNorm(CACHE)
    nn.warm(curies)
    click.echo(f"cache now holds {len(nn._cache)} CURIEs at {CACHE.relative_to(ROOT)}")


@cli.command()
def build() -> None:
    """Load inputs, reconcile via Node Normalizer + MONDO, emit src/data/*.json."""
    click.echo("loading edges...")
    edges = _load_edges()
    n_medic = sum(e["source"] == "medic" for e in edges)
    click.echo(f"  {n_medic} MEDIC + {len(edges) - n_medic} DAKP comparable edges")

    click.echo("warming Node Normalizer cache...")
    nn = NodeNorm(CACHE)
    nn.warm(load.all_curies(edges))

    click.echo("loading MONDO is-a graph (release KGX)...")
    mondo = MondoGraph(INPUTS / "mondo_edges.tsv", INPUTS / "mondo_nodes.tsv")

    node_labels = load.load_dakp_node_labels(INPUTS / "dakp_nodes.jsonl")
    rec = Reconciler(nn, mondo, node_labels)

    click.echo("comparing...")
    # dismech's curated-disease scope (canonicalized), so its absence is only read
    # as a signal where it actually curates. These come from *all* dismech edges, so
    # many aren't in the treats-edge cache — batch-warm them before resolving.
    dismech_disease_curies = load.load_dismech_diseases(INPUTS / "dismech_edges.jsonl")
    nn.warm(dismech_disease_curies)
    dismech_scope = {rec.disease(c).canonical for c in dismech_disease_curies}
    result = compare.compare(edges, rec, mondo, dismech_scope=dismech_scope)

    click.echo("writing artifacts...")
    # One per-pair Parquet holds the whole pair universe with a per-source membership
    # status (exact/related/""); the site slices it by source-combination or entity
    # via DuckDB-WASM. Small coverage rollups and reports stay JSON.
    _write_parquet("pairs.parquet", result["pairs"])
    _write("summary.json", result["summary"])
    _write("dakp_offlabel_top_drugs.json", result["dakp_offlabel_only_top_drugs"])
    _write("by_drug.json", result["by_drug"])
    _write("by_disease.json", result["by_disease"])
    _write("disease_areas.json", result["disease_areas"])
    _write("deconflation.json", result["deconflation"])
    _write("contraindications.json", result["contraindications"])

    s = result["summary"]
    click.echo(
        f"\nsources: {', '.join(f'{k}={v}' for k, v in s['source_pairs'].items())}\n"
        f"universe: {s['universe']} pairs | agree(>=2): {s['agree_2plus']} | all: {s['agree_all']}\n"
        f"combinations: {s['combinations']}\n"
        f"pairwise: {s['pairwise']}\n"
        f"dismech: {s.get('dismech')}\n"
        f"de-conflation: {result['deconflation']['summary'].get('hp_to_mondo', 0)} HP->MONDO, "
        f"{result['deconflation']['summary'].get('kept_hp', 0)} kept HP"
    )


if __name__ == "__main__":
    cli()
