"""Read-only guard, result conversion and the natural-language flow (Bedrock stubbed)."""

import pytest

from fleet_kg.sparql import SparqlError, ensure_read_only, rows_from_json


@pytest.mark.parametrize("query", [
    "INSERT DATA { <a> <b> <c> }", "DELETE WHERE { ?s ?p ?o }", "DROP ALL", "CLEAR DEFAULT",
    "LOAD <http://x>", "SELECT * WHERE { SERVICE <http://x> { ?s ?p ?o } }",
    "WITH <g> DELETE { ?s ?p ?o } WHERE { ?s ?p ?o }", "not sparql at all"])
def test_guard_rejects(query):
    with pytest.raises(SparqlError):
        ensure_read_only(query)


def test_guard_allows_reads_and_limits_rows():
    assert ensure_read_only("SELECT ?s WHERE { ?s ?p ?o }", 50).endswith("LIMIT 50")
    assert "LIMIT 50" in ensure_read_only("SELECT ?s WHERE { ?s ?p ?o } LIMIT 9999", 50)
    assert ensure_read_only("SELECT ?s WHERE { ?s ?p ?o } LIMIT 5", 50).endswith("LIMIT 5")
    # keywords inside strings, IRIs and comments are not commands
    q = 'PREFIX x: <http://insert.example/drop#> SELECT ?s WHERE { ?s x:p "DELETE me" } # DROP\nLIMIT 1'
    assert ensure_read_only(q)
    assert ensure_read_only("ASK { ?s ?p ?o }") == "ASK { ?s ?p ?o }"


def test_rows_from_json_types():
    doc = {"results": {"bindings": [{
        "i": {"type": "literal", "value": "7", "datatype": "http://www.w3.org/2001/XMLSchema#integer"},
        "d": {"type": "literal", "value": "1.5", "datatype": "http://www.w3.org/2001/XMLSchema#decimal"},
        "t": {"type": "literal", "value": "2023-01-02", "datatype": "http://www.w3.org/2001/XMLSchema#date"},
        "u": {"type": "uri", "value": "https://fleet.example.com/id/defect/DF-100245"},
        "s": {"type": "literal", "value": "Aster"}}]}}
    assert rows_from_json(doc) == [{"i": 7, "d": 1.5, "t": "2023-01-02",
                                    "u": "https://fleet.example.com/id/defect/DF-100245", "s": "Aster"}]


class FakeBedrock:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def converse(self, **kwargs):
        self.calls.append(kwargs)
        return {"output": {"message": {"content": [{"text": self.replies.pop(0)}]}}}


GOOD = """Count ATA 36 defects per station.
```sparql
PREFIX fro: <https://fleet.example.com/ontology#>
SELECT ?station (COUNT(?d) AS ?defects) WHERE {
  ?d fro:inAtaChapter/fro:ataCode "36" ; fro:reportedAt/fro:stationCode ?station .
} GROUP BY ?station ORDER BY DESC(?defects)
```"""


def test_nlq_flow(kg):
    pytest.importorskip("rdflib")
    from fleet_kg.nlq import Nlq, system_prompt
    fake = FakeBedrock([GOOD, "DAL reported the most bleed defects."])
    result = Nlq(kg.select, bedrock=fake, model_id="test-model").ask("Where are bleed defects reported?")
    assert result["rows"] and "defects" in result["rows"][0]
    assert result["sparql"].rstrip().endswith("LIMIT 100")
    assert result["answer"].startswith("DAL")
    prompt = system_prompt()
    assert "fro:ComponentRemoval" in prompt and 'VALUES ?tailNumber { "N812BB" }' in prompt


def test_nlq_retries_once_then_reports(kg):
    pytest.importorskip("rdflib")
    from fleet_kg.nlq import Nlq
    bad = "Deleting.\n```sparql\nDELETE WHERE { ?s ?p ?o }\n```"
    fake = FakeBedrock([bad, bad])
    result = Nlq(kg.select, bedrock=fake, model_id="m").ask("delete everything please")
    assert result["error"] and "only read queries" in result["error"]
    assert len(fake.calls) == 2 and result["rows"] == []
