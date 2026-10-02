from pathlib import Path

from drug_edge_compare import load


def _write(p: Path, text: str) -> Path:
    p.write_text(text)
    return p


def test_medic_predicate_collapse(tmp_path):
    jsonl = _write(
        tmp_path / "medic.jsonl",
        '{"subject":"CHEBI:1","predicate":"biolink:treats","object":"MONDO:1",'
        '"publications":["PMID:41385096"],"supporting_text":["[FDA] indicated for ..."]}\n'
        '{"subject":"CHEBI:2","predicate":"biolink:treats","object":"MONDO:2",'
        '"original_object":"DOID:9"}\n',
    )
    edges = load.load_medic(jsonl)
    assert len(edges) == 2
    assert all(e["relation"] == "treats" and e["source"] == "medic" for e in edges)
    assert edges[0]["original_subject"] == "CHEBI:1"        # falls back to subject
    assert edges[1]["original_object"] == "DOID:9"          # kept pre-norm id when present


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


def test_medic_redesign_per_assertion(tmp_path):
    """MeDIC 1.x: one edge per regulator assertion, authority + verbatim text per edge."""
    jsonl = _write(
        tmp_path / "medic2.jsonl",
        '{"subject":"CHEBI:1","predicate":"biolink:treats","object":"MONDO:1",'
        '"medic_authority":"EMA","primary_knowledge_source":"infores:ema",'
        '"supporting_text":"indicated for X","medic_pair_reliability":"HIGH"}\n'
        '{"subject":"CHEBI:1","predicate":"biolink:contraindicated_in","object":"MONDO:2",'
        '"medic_authority":"FDA","primary_knowledge_source":"infores:fda-dailymed",'
        '"supporting_text":"contraindicated in Y","medic_pair_reliability":"LOW"}\n'
        '{"subject":"CHEBI:1","predicate":"biolink:in_clinical_trials_for","object":"MONDO:3"}\n',
    )
    edges = load.load_medic(jsonl)
    assert [e["relation"] for e in edges] == ["treats", "contraindicated_in"]  # trials skipped
    assert edges[0]["agency_text"] == {"EMA": "indicated for X"}
    assert edges[0]["reliability"] == "HIGH"
    assert edges[1]["agencies"] == ["FDA"]


def test_medic_ingest_agency_text(tmp_path):
    jsonl = _write(
        tmp_path / "medic.jsonl",
        '{"subject":"CHEBI:1","predicate":"biolink:treats","object":"MONDO:1",'
        '"supporting_text":["[FDA] for X","[PMDA] for X too"]}\n',
    )
    (e,) = load.load_medic(jsonl)
    assert e["agency_text"] == {"FDA": "for X", "PMDA": "for X too"}
    assert e["reliability"] is None


def test_dakp_regulatory_approvals_rename(tmp_path):
    jsonl = _write(
        tmp_path / "dakp.jsonl",
        '{"subject":"CHEBI:1","predicate":"biolink:treats","object":"MONDO:1",'
        '"FDA_regulatory_approvals":["NDA1"]}\n'
        '{"subject":"CHEBI:2","predicate":"biolink:treats","object":"MONDO:1",'
        '"regulatory_approvals":["NDA2","EMEA/H/C/1"]}\n',
    )
    old, new = load.load_dakp(jsonl)
    assert old["fda_approvals"] == ["NDA1"]
    assert new["fda_approvals"] == ["NDA2", "EMEA/H/C/1"]
