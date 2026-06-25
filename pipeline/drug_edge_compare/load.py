"""Load the feeds into a single raw-edge shape.

MEDIC ships KGX JSONL of indication edges (all ``biolink:treats``, one edge per
drug-disease pair with per-agency FDA/EMA/PMDA provenance); DAKP ships KGX JSONL
with three predicates and richer provenance; dismech ships KGX JSONL too. We
flatten all to a common ``RawEdge`` dict and collapse the predicate to a
``relation`` bucket:

    biolink:treats, biolink:applied_to_treat  -> "treats"   (a drug is used on a disease)
    biolink:contraindicated_in                -> "contraindicated_in"

Per Kevin's call we ignore the treats/applied_to_treat distinction (it may be the
wrong predicate choice on the medic-ingest side); contraindications are held apart
because they are the semantic opposite, and MEDIC's indication export has nothing
to compare them against yet.
"""
from __future__ import annotations

import json
from pathlib import Path

# biolink predicate -> coarse relation used for comparison
RELATION = {
    "biolink:treats": "treats",
    "biolink:applied_to_treat": "treats",
    # dismech ships a single union predicate that already subsumes treats/applied
    "biolink:treats_or_applied_or_studied_to_treat": "treats",
    "biolink:contraindicated_in": "contraindicated_in",
}


def _relation(predicate: str) -> str | None:
    return RELATION.get(predicate)


def load_medic(edges_path: str | Path) -> list[dict]:
    """MEDIC indication KGX edges.jsonl -> list of RawEdge dicts (source='medic').

    One edge per drug→disease pair; ``sources`` carry per-agency provenance
    (infores:dailymed / :ema / :pmda as supporting_data_source) and
    ``supporting_text`` the verbatim ``[FDA]/[EMA]/[PMDA]`` indication text. We keep
    the supporting_text but compare on the (drug, disease) pair only, as before.
    """
    out: list[dict] = []
    with open(edges_path) as f:
        for line in f:
            e = json.loads(line)
            rel = _relation(e["predicate"])
            if rel is None:
                continue
            out.append(
                {
                    "source": "medic",
                    "relation": rel,
                    "predicate": e["predicate"],
                    "subject": e["subject"],
                    "object": e["object"],
                    "original_subject": e.get("original_subject", e["subject"]),
                    "original_object": e.get("original_object", e["object"]),
                    "clinical_approval_status": None,
                    "number_of_cases": None,
                    "publications": e.get("publications") or [],
                    "supporting_text": e.get("supporting_text") or [],
                }
            )
    return out


def load_dakp(edges_path: str | Path) -> list[dict]:
    """DAKP edges.jsonl -> list of RawEdge dicts (source='dakp')."""
    out: list[dict] = []
    with open(edges_path) as f:
        for line in f:
            e = json.loads(line)
            rel = _relation(e["predicate"])
            if rel is None:
                continue
            out.append(
                {
                    "source": "dakp",
                    "relation": rel,
                    "predicate": e["predicate"],
                    "subject": e["subject"],
                    "object": e["object"],
                    "original_subject": e.get("original_subject", e["subject"]),
                    "original_object": e.get("original_object", e["object"]),
                    "clinical_approval_status": e.get("clinical_approval_status"),
                    "number_of_cases": e.get("number_of_cases"),
                    # DAKP's underlying evidence: DailyMed SPL setids (``publications``)
                    # and FDA application numbers (``FDA_regulatory_approvals``).
                    "publications": e.get("publications") or [],
                    "fda_approvals": e.get("FDA_regulatory_approvals") or [],
                }
            )
    return out


def load_dismech(edges_path: str | Path) -> list[dict]:
    """dismech KGX edges.jsonl -> RawEdge dicts (source='dismech', treats only).

    dismech's treatment subjects mix drugs (CHEBI) with non-drug modalities (MAXO
    medical actions, NCIT procedures); the drug filter is applied downstream via
    the reconciler. Edges carry real per-edge publications + supporting_text.
    """
    out: list[dict] = []
    with open(edges_path) as f:
        for line in f:
            e = json.loads(line)
            rel = _relation(e["predicate"])
            if rel != "treats":
                continue
            out.append(
                {
                    "source": "dismech",
                    "relation": rel,
                    "predicate": e["predicate"],
                    "subject": e["subject"],
                    "object": e["object"],
                    "original_subject": e["subject"],
                    "original_object": e["object"],
                    "clinical_approval_status": None,
                    "number_of_cases": None,
                    "publications": e.get("publications") or [],
                    "supporting_text": e.get("supporting_text") or [],
                }
            )
    return out


def load_dismech_diseases(edges_path: str | Path) -> set[str]:
    """Every MONDO disease dismech mentions across *any* edge — its curated scope.

    dismech is disease-centric: a disease it hasn't curated yet has no edges, so a
    missing drug→disease pair there means "not curated", not "disagrees". This set
    (canonicalized downstream) bounds where dismech's *absence* is a real signal.
    Restricted to MONDO so HP phenotypes (objects of has_phenotype edges) aren't
    miscounted as curated diseases.
    """
    diseases: set[str] = set()
    with open(edges_path) as f:
        for line in f:
            e = json.loads(line)
            for end in (e.get("subject", ""), e.get("object", "")):
                if end.startswith("MONDO:"):
                    diseases.add(end)
    return diseases


def load_dakp_node_labels(nodes_path: str | Path) -> dict[str, str]:
    """DAKP nodes.jsonl -> {curie: name} for labelling (clique-preferred names)."""
    labels: dict[str, str] = {}
    with open(nodes_path) as f:
        for line in f:
            n = json.loads(line)
            if "name" in n and n["name"]:
                labels[n["id"]] = n["name"]
    return labels


def all_curies(edges: list[dict]) -> set[str]:
    """Every subject + object CURIE across a list of RawEdges."""
    curies: set[str] = set()
    for e in edges:
        curies.add(e["subject"])
        curies.add(e["object"])
    return curies
