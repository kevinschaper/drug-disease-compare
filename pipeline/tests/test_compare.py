"""End-to-end pipeline test with a seeded Node Normalizer cache (no network)."""
import json
from pathlib import Path

import pytest

from drug_edge_compare import compare
from drug_edge_compare.mondo import MondoGraph
from drug_edge_compare.nodenorm import NodeNorm
from drug_edge_compare.reconcile import Reconciler


def _clique(pid, label, eqs=None, type_="biolink:Disease"):
    eqs = eqs or [pid]
    return {
        "id": {"identifier": pid, "label": label},
        "equivalent_identifiers": [{"identifier": e} for e in eqs],
        "type": [type_],
    }


@pytest.fixture
def rec(tmp_path):
    cache = {
        "CHEBI:1": _clique("CHEBI:1", "DrugOne", type_="biolink:SmallMolecule"),
        "CHEBI:2": _clique("CHEBI:2", "DrugTwo", type_="biolink:SmallMolecule"),
        "MONDO:0000001": _clique("MONDO:0000001", "ParentDisease"),
        "MONDO:0000002": _clique("MONDO:0000002", "ChildDisease"),
        "MONDO:0000003": _clique("MONDO:0000003", "OtherDisease"),
        "DOID:5": _clique("MONDO:0000001", "ParentDisease", ["MONDO:0000001", "DOID:5"]),
        "HP:0001250": _clique("MONDO:0000003", "OtherDisease", ["MONDO:0000003", "HP:0001250"]),
        "HP:9999": _clique("HP:9999", "PurePhenotype", ["HP:9999"], type_="biolink:PhenotypicFeature"),
    }
    cache_path = tmp_path / "cache.json"
    cache_path.write_text(json.dumps(cache))
    nn = NodeNorm(cache_path)

    edges_tsv = tmp_path / "mondo_edges.tsv"
    edges_tsv.write_text(
        "id\tsubject\tpredicate\tobject\n"
        "e1\tMONDO:0000002\tbiolink:subclass_of\tMONDO:0000001\n"
    )
    nodes_tsv = tmp_path / "mondo_nodes.tsv"
    nodes_tsv.write_text(
        "id\tname\tdeprecated\n"
        "MONDO:0000001\tParentDisease\t\n"
        "MONDO:0000002\tChildDisease\t\n"
        "MONDO:0000003\tOtherDisease\t\n"
    )
    mondo = MondoGraph(edges_tsv, nodes_tsv)
    return Reconciler(nn, mondo), mondo


def _edge(source, predicate, subj, obj, status=None, cases=0):
    rel = {"biolink:treats": "treats", "biolink:applied_to_treat": "treats",
           "biolink:contraindicated_in": "contraindicated_in"}[predicate]
    return {"source": source, "relation": rel, "predicate": predicate, "subject": subj,
            "object": obj, "original_subject": subj, "original_object": obj,
            "clinical_approval_status": status, "number_of_cases": cases, "publications": ""}


def test_reconcile_disease_axis(rec):
    reconciler, _ = rec
    assert reconciler.disease("DOID:5").canonical == "MONDO:0000001"          # lift
    hp = reconciler.disease("HP:0001250")
    assert hp.canonical == "MONDO:0000003" and hp.deconflated_from_hp          # de-conflate
    kept = reconciler.disease("HP:9999")
    assert kept.canonical == "HP:9999" and kept.kept_hp                        # kept HP
    assert reconciler.drug("CHEBI:1").canonical == "CHEBI:1"


def test_status_precedence_and_buckets(rec):
    reconciler, mondo = rec
    edges = [
        _edge("medic", "biolink:treats", "CHEBI:1", "MONDO:0000001"),
        _edge("medic", "biolink:treats", "CHEBI:1", "HP:0001250"),   # -> MONDO:0000003
        _edge("medic", "biolink:treats", "CHEBI:2", "DOID:5"),       # -> MONDO:0000001
        _edge("medic", "biolink:treats", "CHEBI:1", "HP:9999"),      # kept HP
        # approved beats the off-label edge on the same pair
        _edge("dakp", "biolink:applied_to_treat", "CHEBI:1", "MONDO:0000001", "off_label_use", 2),
        _edge("dakp", "biolink:treats", "CHEBI:1", "MONDO:0000001", "approved_for_condition", 9),
        # child of MONDO:0000001 -> recovered as hierarchy-related
        _edge("dakp", "biolink:applied_to_treat", "CHEBI:1", "MONDO:0000002", "off_label_use", 3),
        _edge("dakp", "biolink:treats", "CHEBI:1", "HP:9999", "approved_for_condition", 1),
        _edge("dakp", "biolink:contraindicated_in", "CHEBI:2", "MONDO:0000003", None, 5),
    ]
    medic, dakp, contra = compare.build_pairs(edges, reconciler)
    assert dakp[("CHEBI:1", "MONDO:0000001")]["status"] == "approved_for_condition"
    assert dakp[("CHEBI:1", "MONDO:0000001")]["cases"] == 11

    result = compare.compare(edges, reconciler, mondo)
    s = result["summary"]
    assert s["agree_exact"] == 2          # (CHEBI:1,MONDO:1) and (CHEBI:1,HP:9999)
    assert s["related_hierarchy"] == 1    # (CHEBI:1,MONDO:2) recovered against MEDIC's MONDO:1
    assert s["medic_only"] == 2           # (CHEBI:1,MONDO:3) and (CHEBI:2,MONDO:1)
    assert s["dakp_only"] == 0
    assert s["contraindication_pairs"] == 1

    dc = result["deconflation"]["summary"]
    assert dc.get("hp_to_mondo") == 1
    assert dc.get("kept_hp") == 1
    assert dc.get("lifted_to_mondo") == 1

    rel = result["related"][0]
    assert rel["medic_disease"] == "MONDO:0000001" and rel["dakp_disease"] == "MONDO:0000002"
    assert rel["relation"] == "more_general"   # MEDIC's disease is the parent
