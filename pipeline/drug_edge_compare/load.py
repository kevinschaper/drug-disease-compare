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
because they are the semantic opposite. The medic redesign exports
``biolink:contraindicated_for``, which we read as the same relation as DAKP's
``biolink:contraindicated_in`` so the two can be compared head to head.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_AGENCY_PREFIX = re.compile(r"^\[(FDA|EMA|PMDA)\]\s*(.*)$", re.DOTALL)

# biolink predicate -> coarse relation used for comparison
RELATION = {
    "biolink:treats": "treats",
    "biolink:applied_to_treat": "treats",
    # dismech ships a single union predicate that already subsumes treats/applied
    "biolink:treats_or_applied_or_studied_to_treat": "treats",
    "biolink:contraindicated_in": "contraindicated_in",
    # the medic redesign names its contraindications with the older biolink slot
    "biolink:contraindicated_for": "contraindicated_in",
}

# MEDIC redesign: per-edge ``primary_knowledge_source`` names the regulator(s)
# whose label asserts the pair; map to the agency chips the site shows.
_MEDIC_AGENCY = {
    "infores:fda-dailymed": "FDA", "infores:dailymed": "FDA",
    "infores:ema": "EMA", "infores:pmda": "PMDA", "infores:cdsco": "CDSCO",
}


def _relation(predicate: str) -> str | None:
    return RELATION.get(predicate)


def load_medic(edges_path: str | Path) -> list[dict]:
    """MEDIC KGX edges.jsonl -> list of RawEdge dicts (source='medic').

    Reads both export generations:

    * **medic-ingest** (2026-06-19 release): ``biolink:treats`` only, one edge per pair,
      list-valued ``supporting_text`` holding verbatim ``[FDA]/[EMA]/[PMDA]`` text.
    * **medic redesign** (MeDIC 1.x): one edge per *assertion* (a pair asserted by
      several regulators has several edges), ``biolink:treats`` +
      ``biolink:contraindicated_in`` (plus a handful of research predicates we skip).
      ``medic_authority`` names the regulator, ``supporting_text`` is that label's
      verbatim (possibly truncated) section text, and ``medic_pair_reliability`` the
      pair-level HIGH/MEDIUM/LOW tier.

    Both are normalized to ``agency_text`` ({FDA|EMA|PMDA|CDSCO: text}) + ``reliability``.
    """
    out: list[dict] = []
    with open(edges_path) as f:
        for line in f:
            e = json.loads(line)
            rel = _relation(e["predicate"])
            if rel is None:
                continue
            st = e.get("supporting_text") or []
            agency_text: dict[str, str] = {}
            if isinstance(st, str):
                # redesign: one assertion per edge, authority named explicitly
                pks = e.get("primary_knowledge_source")
                agency = e.get("medic_authority") or _MEDIC_AGENCY.get(pks, pks)
                if agency:
                    agency_text[agency] = st
            else:
                for t in st:
                    if m := _AGENCY_PREFIX.match(t):
                        agency_text.setdefault(m.group(1), m.group(2).strip())
                # Aug-2026 interim redesign export: list of regulators, no text
                if isinstance(e.get("primary_knowledge_source"), list):
                    for p in e["primary_knowledge_source"]:
                        agency_text.setdefault(_MEDIC_AGENCY.get(p, p), "")
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
                    "agency_text": agency_text,
                    "agencies": list(agency_text),
                    "reliability": (e.get("medic_pair_reliability") or e.get("medic_reliability")
                                    or e.get("reliability")),
                }
            )
    return out


def load_dakp(edges_path: str | Path) -> list[dict]:
    """DAKP edges.jsonl -> list of RawEdge dicts (source='dakp').

    Same shape across the rtx.ai 0.5.x builds and the 1.x Hugging Face releases; only
    the approvals field was renamed (and the infores rebranded, which we don't read).
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
                    # and application numbers -- ``FDA_regulatory_approvals`` through the
                    # 2026_04_21 build, ``regulatory_approvals`` (FDA + EMA) from 1.x on.
                    "publications": e.get("publications") or [],
                    "fda_approvals": (e.get("regulatory_approvals")
                                      or e.get("FDA_regulatory_approvals") or []),
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


def load_node_labels(nodes_path: str | Path) -> dict[str, str]:
    """KGX nodes.jsonl -> {curie: name}, for labels and exact-name drug repair."""
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
