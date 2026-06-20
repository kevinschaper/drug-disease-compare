# drug-disease-compare tasks

# List recipes
default:
    @just --list

# Download pinned inputs (MEDIC edges, DAKP KGX archive, MONDO is-a graph)
fetch:
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p data/inputs
    cd data/inputs
    # MEDIC indication edges (Monarch medic-ingest release; KGX JSONL, one edge per pair)
    curl -sL -o medic_edges.jsonl \
      "https://github.com/monarch-initiative/medic-ingest/releases/download/2026-06-19/medic_indication_edges.jsonl"
    # Drug Approvals KP KGX release (zstd tarball -> edges.jsonl + nodes.jsonl)
    curl -sL -o dakp.tar.zst \
      "https://kgx-storage.rtx.ai/releases/dakp/2026_04_21/dakp.tar.zst"
    tar --use-compress-program=unzstd -xf dakp.tar.zst
    mv edges.jsonl dakp_edges.jsonl
    mv nodes.jsonl dakp_nodes.jsonl
    # dismech KGX edges (only its CHEBI drug->disease subset is used downstream)
    curl -sL -o dismech_edges.jsonl \
      "https://github.com/monarch-initiative/dismech/releases/download/v0.1.30/dismech_edges.jsonl"
    # MONDO is-a graph for disease-axis closure (release KGX, version-matched to nodenorm cliques)
    curl -sL -o mondo_edges.tsv \
      "https://github.com/monarch-initiative/mondo/releases/latest/download/mondo_edges.tsv"
    curl -sL -o mondo_nodes.tsv \
      "https://github.com/monarch-initiative/mondo/releases/latest/download/mondo_nodes.tsv"
    echo "fetched inputs:"; ls -la

# Resolve every drug/disease CURIE through the SRI Node Normalizer -> data/nodenorm_cache.json
normalize:
    PYTHONPATH=pipeline uv run python -m drug_edge_compare.cli normalize

# Run the comparison pipeline -> src/data/*.json (normalizes first if cache is missing)
build:
    PYTHONPATH=pipeline uv run python -m drug_edge_compare.cli build

# Python tests
test:
    PYTHONPATH=pipeline uv run --with pytest pytest pipeline/tests -q

# Install site deps and preview locally
dev:
    npm install && npm run dev

# Build the static site (runs the comparison pipeline first)
site: build
    npm run build
