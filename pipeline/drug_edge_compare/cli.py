"""Build the comparison artifacts consumed by the Observable Framework site."""
from __future__ import annotations

import json
from pathlib import Path

import click

from . import changes, compare, load
from .drug_groups import moiety_grouper
from .mondo import MondoGraph
from .nodenorm import NodeNorm
from .reconcile import Reconciler

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "data" / "inputs"
CACHE = ROOT / "data" / "nodenorm_cache.json"
DRUG_GROUP_CACHE = ROOT / "data" / "drug_groups_cache.json"
ARTIFACTS = ROOT / "src" / "data"


# Inputs are versioned per source: data/inputs/<source>/{old,new}/. "new" drives the
# head-to-head; "old" is the release the previous site was built from, kept so each
# source's change can be characterized (data/MANIFEST.yaml pins both).
LOADERS = {"medic": load.load_medic, "dakp": load.load_dakp, "dismech": load.load_dismech}
VERSIONS = ("old", "new")


def _edges_path(source: str, version: str = "new") -> Path:
    return INPUTS / source / version / f"{source}_edges.jsonl"


def _load_source(source: str, version: str = "new") -> list[dict]:
    return LOADERS[source](_edges_path(source, version))


def _load_edges(version: str = "new") -> list[dict]:
    return [e for s in LOADERS for e in _load_source(s, version)]


def _node_labels() -> dict[str, str]:
    """Source node names (DAKP + MEDIC nodes files), new release winning over old.

    Labels nodes the Node Normalizer can't name, and feeds the exact-name drug repair.
    """
    labels: dict[str, str] = {}
    for v in VERSIONS:
        for s in ("medic", "dakp"):
            path = INPUTS / s / v / f"{s}_nodes.jsonl"
            if path.exists():
                labels.update(load.load_node_labels(path))
    return labels


def _reconciler(nn: NodeNorm, mondo: MondoGraph, edges: list[dict]):
    """Reconciler with exact-name RxNorm repair for unresolved drug CURIEs.

    Returns ``(rec, clients)``; ``clients.save()`` persists the RxNorm lookups. The
    repair lookups are prefetched concurrently and their RXCUIs batch-normalized.
    """
    from concurrent.futures import ThreadPoolExecutor

    from .drug_groups import _Cache, _Clients

    labels = _node_labels()
    clients = _Clients(_Cache(DRUG_GROUP_CACHE))
    unresolved = {e["subject"] for e in edges if not nn.clique(e["subject"]).resolved}
    names = sorted({labels[c] for c in unresolved if labels.get(c)})
    with ThreadPoolExecutor(16) as ex:
        rxcuis = [r for r in ex.map(clients.rxnorm_by_name, names) if r]
    nn.warm(f"RXCUI:{r}" for r in rxcuis)
    clients.save()
    click.echo(f"  {len(unresolved)} drug CURIEs unknown to the Node Normalizer; "
               f"{len(rxcuis)} have an exact RxNorm name match")
    return Reconciler(nn, mondo, labels, name_to_rxcui=clients.rxnorm_by_name), clients


def _manifest_versions() -> dict:
    """{source: {old: release, new: release}} from data/MANIFEST.yaml."""
    import yaml

    m = yaml.safe_load((ROOT / "data" / "MANIFEST.yaml").read_text())["inputs"]
    return {s: {v: m[f"{s}_edges"][v]["release"] for v in VERSIONS} for s in LOADERS}


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
    """Resolve every drug/disease CURIE (old + new releases) through the Node Normalizer."""
    curies = set()
    for v in VERSIONS:
        curies |= load.all_curies(_load_edges(v))
        curies |= load.load_dismech_diseases(_edges_path("dismech", v))
    click.echo(f"resolving {len(curies)} distinct CURIEs through the Node Normalizer...")
    nn = NodeNorm(CACHE)
    nn.warm(curies)
    click.echo(f"cache now holds {len(nn._cache)} CURIEs at {CACHE.relative_to(ROOT)}")


@cli.command()
@click.option("--drug-collapse/--no-drug-collapse", default=True,
              help="bridge same-drug variants (active moiety, ion-guarded) as a flagged "
                   "drug-axis signal; never folded into exact agreement")
def build(drug_collapse: bool) -> None:
    """Load inputs, reconcile via Node Normalizer + MONDO, emit src/data/*.json."""
    click.echo("loading edges...")
    edges = _load_edges()
    n = {s: sum(e["source"] == s for e in edges) for s in LOADERS}
    click.echo("  " + ", ".join(f"{s}={c}" for s, c in n.items()) + " comparable edges")

    click.echo("warming Node Normalizer cache...")
    nn = NodeNorm(CACHE)
    nn.warm(load.all_curies(edges))

    click.echo("loading MONDO is-a graph (release KGX)...")
    mondo = MondoGraph(INPUTS / "mondo_edges.tsv", INPUTS / "mondo_nodes.tsv")

    rec, _ = _reconciler(nn, mondo, edges)

    click.echo("comparing...")
    # dismech's curated-disease scope (canonicalized), so its absence is only read
    # as a signal where it actually curates. These come from *all* dismech edges, so
    # many aren't in the treats-edge cache — batch-warm them before resolving.
    dismech_disease_curies = load.load_dismech_diseases(_edges_path("dismech"))
    nn.warm(dismech_disease_curies)
    dismech_scope = {rec.disease(c).canonical for c in dismech_disease_curies}

    grouper = None
    clients = None
    if drug_collapse:
        click.echo("resolving drug-axis groups (active moiety, ion-guarded; cached)...")
        clients, grouper = moiety_grouper(DRUG_GROUP_CACHE)
    result = compare.compare(edges, rec, mondo, dismech_scope=dismech_scope, drug_grouper=grouper)
    if clients is not None:
        clients.save()

    click.echo("writing artifacts...")
    # One per-pair Parquet holds the whole pair universe with a per-source membership
    # status (exact/related/""); the site slices it by source-combination or entity
    # via DuckDB-WASM. Small coverage rollups and reports stay JSON.
    _write_parquet("pairs.parquet", result["pairs"])
    # MEDIC verbatim agency indication text, kept out of pairs.parquet (~14 MB of prose);
    # the detail pages join it on (drug, disease) on demand.
    _write_parquet("medic_evidence.parquet", result["medic_evidence"])
    _write("dakp_offlabel_top_drugs.json", result["dakp_offlabel_only_top_drugs"])
    _write("by_drug.json", result["by_drug"])
    _write("by_disease.json", result["by_disease"])
    _write("disease_areas.json", result["disease_areas"])
    _write("contraindications.json", result["contraindications"])
    s = result["summary"]
    s["versions"] = {src: v["new"] for src, v in _manifest_versions().items()}
    _write("summary.json", s)

    s = result["summary"]
    click.echo(
        f"\nsources: {', '.join(f'{k}={v}' for k, v in s['source_pairs'].items())}\n"
        f"universe: {s['universe']} pairs | agree(>=2): {s['agree_2plus']} | all: {s['agree_all']}\n"
        f"moiety: {s.get('moiety')}\n"
        f"combinations: {s['combinations']}\n"
        f"pairwise: {s['pairwise']}\n"
        f"dismech: {s.get('dismech')}"
    )


@cli.command("changes")
def changes_cmd() -> None:
    """Characterize each source's old -> new release change -> src/data/changes.*"""
    click.echo("loading old + new releases...")
    edges = {s: {v: _load_source(s, v) for v in VERSIONS} for s in LOADERS}
    nn = NodeNorm(CACHE)
    nn.warm(set().union(*(load.all_curies(e) for d in edges.values() for e in d.values())))
    mondo = MondoGraph(INPUTS / "mondo_edges.tsv", INPUTS / "mondo_nodes.tsv")
    rec, _ = _reconciler(nn, mondo, [e for d in edges.values() for v in d.values() for e in v])
    versions = _manifest_versions()

    # moiety groups (shared cache with `build`) so a re-grounded drug isn't misread as
    # one drug dropped + another added
    click.echo("resolving drug-axis groups (active moiety; cached)...")
    gclients, grouper = moiety_grouper(DRUG_GROUP_CACHE)
    gmemo: dict[str, str] = {}

    def group(drug: str) -> str:
        if drug not in gmemo:
            gmemo[drug] = grouper.group(compare.named_clique(rec, drug)).group_id
        return gmemo[drug]

    summaries, rows, sets = {}, [], {}
    for s in LOADERS:
        click.echo(f"  diffing {s} {versions[s]['old']} -> {versions[s]['new']}...")
        summ, r, ss = changes.source_changes(s, edges[s]["old"], edges[s]["new"], rec, mondo,
                                             versions[s], group)
        summaries[s], sets[s] = summ, ss
        rows.extend(r)
        for lens, L in summ["lenses"].items():
            click.echo(f"    {lens}: {L['old']} -> {L['new']} (kept {L['kept']}, "
                       f"+{L['added']}, -{L['removed']}) {L['reasons']}")

    trajectory = changes.agreement_trajectory(sets)
    for t in trajectory:
        click.echo(f"  {t['pair']}: old/old {t['old_old']['shared']} -> new/new {t['new_new']['shared']}")
    gclients.save()
    _write("changes.json", {"sources": summaries, "trajectory": trajectory,
                            "repaired_drugs": len(rec.repaired)})
    _write_parquet("changes.parquet", rows)


if __name__ == "__main__":
    cli()
