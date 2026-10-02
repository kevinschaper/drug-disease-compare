# drug-disease-compare tasks

# List recipes
default:
    @just --list

# Local MeDIC redesign build whose exports are the "new" MEDIC (not yet released)
medic_exports := env_var_or_default("MEDIC_EXPORTS", "/home/kschaper/Monarch/medic-redesign/medic/exports")

# Download pinned inputs: old + new release of each source, and the MONDO is-a graph
fetch: sync-medic
    #!/usr/bin/env bash
    set -euo pipefail
    mkdir -p data/inputs/{medic,dakp,dismech}/{old,new}
    cd data/inputs
    # MEDIC old: medic-ingest release (KGX JSONL, one edge per pair)
    curl -sfL -o medic/old/medic_edges.jsonl \
      "https://github.com/monarch-initiative/medic-ingest/releases/download/2026-06-19/medic_indication_edges.jsonl"
    # DAKP old: rtx.ai build (zstd tarball). The host is intermittently unreachable --
    # if this fails, copy edges.jsonl/nodes.jsonl from the tarball in by hand.
    if [ ! -s dakp/old/dakp_edges.jsonl ]; then
      curl -sfL -o dakp/old/dakp.tar.zst "https://kgx-storage.rtx.ai/releases/dakp/2026_04_21/dakp.tar.zst"
      (cd dakp/old && tar --use-compress-program=unzstd -xf dakp.tar.zst \
        && mv edges.jsonl dakp_edges.jsonl && mv nodes.jsonl dakp_nodes.jsonl)
    fi
    # DAKP new: Hugging Face release
    hf="https://huggingface.co/datasets/SkyeAv/drug-approvals-kp/resolve/main/1.16.0"
    curl -sfL -o dakp/new/dakp_edges.jsonl "$hf/DRUG_APPROVALS_KP_1.16.0.edges.ndjson"
    curl -sfL -o dakp/new/dakp_nodes.jsonl "$hf/DRUG_APPROVALS_KP_1.16.0.nodes.ndjson"
    # dismech old + new (only its CHEBI drug->disease subset is used downstream)
    curl -sfL -o dismech/old/dismech_edges.jsonl \
      "https://github.com/monarch-initiative/dismech/releases/download/v0.1.30/dismech_edges.jsonl"
    curl -sfL -o dismech/new/dismech_edges.jsonl \
      "https://github.com/monarch-initiative/dismech/releases/download/v0.1.42/dismech_edges.jsonl"
    # MONDO is-a graph for disease-axis closure
    curl -sfL -o mondo_edges.tsv \
      "https://github.com/monarch-initiative/mondo/releases/latest/download/mondo_edges.tsv"
    curl -sfL -o mondo_nodes.tsv \
      "https://github.com/monarch-initiative/mondo/releases/latest/download/mondo_nodes.tsv"
    sha256sum */*/*_edges.jsonl

# Copy the latest local MeDIC KGX export in as the "new" MEDIC
sync-medic:
    mkdir -p data/inputs/medic/new
    cp {{medic_exports}}/medic_edges.jsonl {{medic_exports}}/medic_kgx_metadata.yaml data/inputs/medic/new/
    sha256sum data/inputs/medic/new/medic_edges.jsonl

# Resolve every drug/disease CURIE through the SRI Node Normalizer -> data/nodenorm_cache.json
normalize:
    PYTHONPATH=pipeline uv run python -m drug_edge_compare.cli normalize

# Run the comparison pipeline -> src/data/*.json (normalizes first if cache is missing)
build:
    PYTHONPATH=pipeline uv run python -m drug_edge_compare.cli build

# Characterize each source's old -> new release change -> src/data/changes.*
changes:
    PYTHONPATH=pipeline uv run python -m drug_edge_compare.cli changes

# Python tests
test:
    PYTHONPATH=pipeline uv run --with pytest pytest pipeline/tests -q

# Install site deps and preview locally
dev:
    npm install && npm run dev

# Build the static site (runs the comparison pipeline first)
site: build changes
    npm run build
