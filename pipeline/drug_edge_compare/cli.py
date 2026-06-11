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
    return medic + dakp


def _write(name: str, obj) -> None:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    path = ARTIFACTS / name
    path.write_text(json.dumps(obj, indent=2))
    click.echo(f"  wrote {path.relative_to(ROOT)} ({path.stat().st_size // 1024} KB)")


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
    result = compare.compare(edges, rec, mondo)

    click.echo("writing artifacts...")
    _write("summary.json", result["summary"])
    _write("agree.json", result["agree"])
    _write("related.json", result["related"])
    _write("medic_only.json", result["medic_only"])
    _write("dakp_onlabel_only.json", result["dakp_onlabel_only"])
    _write("dakp_offlabel_top_drugs.json", result["dakp_offlabel_only_top_drugs"])
    _write("by_drug.json", result["by_drug"])
    _write("deconflation.json", result["deconflation"])
    _write("contraindications.json", result["contraindications"])

    s = result["summary"]
    click.echo(
        f"\npairs: {s['agree_exact']} agree + {s['related_hierarchy']} hierarchy-related | "
        f"{s['medic_only']} MEDIC-only | {s['dakp_only']} DAKP-only "
        f"({s['dakp_only_onlabel']} on-label, {s['dakp_only_offlabel']} off-label)\n"
        f"overlap: all-treats Jaccard {s['jaccard_all']} | "
        f"on-label-only Jaccard {s['jaccard_onlabel']}\n"
        f"de-conflation: {result['deconflation']['summary'].get('hp_to_mondo', 0)} HP->MONDO, "
        f"{result['deconflation']['summary'].get('kept_hp', 0)} kept HP"
    )


if __name__ == "__main__":
    cli()
