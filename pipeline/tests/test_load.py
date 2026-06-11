from pathlib import Path

from drug_edge_compare import load


def _write(p: Path, text: str) -> Path:
    p.write_text(text)
    return p


def test_medic_predicate_collapse(tmp_path):
    tsv = _write(
        tmp_path / "medic.tsv",
        "id\tsubject\tpredicate\tobject\n"
        "u1\tCHEBI:1\tbiolink:treats\tMONDO:1\n"
        "u2\tCHEBI:2\tbiolink:treats\tMONDO:2\n",
    )
    edges = load.load_medic(tsv)
    assert len(edges) == 2
    assert all(e["relation"] == "treats" and e["source"] == "medic" for e in edges)
    assert edges[0]["original_subject"] == "CHEBI:1"  # MEDIC has no pre-norm id


def test_dakp_predicate_buckets(tmp_path):
    jsonl = _write(
        tmp_path / "dakp.jsonl",
        '{"subject":"CHEBI:1","predicate":"biolink:applied_to_treat","object":"MONDO:1",'
        '"clinical_approval_status":"off_label_use","number_of_cases":3}\n'
        '{"subject":"CHEBI:2","predicate":"biolink:treats","object":"MONDO:2",'
        '"clinical_approval_status":"approved_for_condition","number_of_cases":1}\n'
        '{"subject":"CHEBI:3","predicate":"biolink:contraindicated_in","object":"MONDO:3",'
        '"number_of_cases":5}\n',
    )
    edges = load.load_dakp(jsonl)
    rels = sorted(e["relation"] for e in edges)
    assert rels == ["contraindicated_in", "treats", "treats"]
    contra = next(e for e in edges if e["relation"] == "contraindicated_in")
    assert contra["number_of_cases"] == 5


def test_all_curies(tmp_path):
    jsonl = _write(
        tmp_path / "d.jsonl",
        '{"subject":"CHEBI:1","predicate":"biolink:treats","object":"MONDO:1"}\n',
    )
    edges = load.load_dakp(jsonl)
    assert load.all_curies(edges) == {"CHEBI:1", "MONDO:1"}
