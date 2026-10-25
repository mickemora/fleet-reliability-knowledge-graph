"""Materialization rules and the ten competency questions on the in-memory graph."""

import pytest

pytest.importorskip("rdflib")

from fleet_kg import competency, rules  # noqa: E402
from fleet_kg.explorer import select_vars  # noqa: E402
from fleet_kg.namespaces import iri, sparql_prefixes  # noqa: E402

P = sparql_prefixes()


def ask(kg, body):
    return kg.ask(P + "ASK { " + body + " }")


def test_inverses_subclasses_subproperties(kg):
    a = iri("aircraft", "N812BB")
    assert ask(kg, f"<{a}> fro:hasDefect <{iri('defect', 'DF-100245')}>")
    assert ask(kg, f"<{iri('component', 'BV10457')}> fro:hasRemoval ?r")
    assert ask(kg, f"<{a}> a fro:Asset") and ask(kg, f"<{a}> a fro:BusinessEntity")
    assert ask(kg, f'<{a}> fro:identifier "N812BB"')


def test_every_defect_has_one_system_group(kg):
    rows = kg.select(P + """SELECT ?d WHERE { ?d a fro:Defect .
        OPTIONAL { ?d fro:inSystemGroup ?g } } GROUP BY ?d HAVING (COUNT(?g) != 1)""")
    assert rows == []


def test_rules_are_idempotent(kg):
    before = kg.select(rules.COUNT)[0]["n"]
    for _, update in rules.RULES:
        kg.update(update)
    assert kg.select(rules.COUNT)[0]["n"] == before


@pytest.fixture(scope="module")
def answers(kg):
    return {q.id: kg.select(q.bind()) for q in competency.load_all().values()}


def test_ten_questions_answer(answers):
    assert sorted(answers) == [f"cq{i:02d}" for i in range(1, 11)]
    assert all(answers.values()), [k for k, v in answers.items() if not v]


def test_cq01_tail_360(answers):
    items = {r["item"] for r in answers["cq01"]}
    assert "DF-100245" in items
    assert {r["section"][0] for r in answers["cq01"]} >= {"2", "4"}


def test_cq02_finds_the_chronic_tail(answers):
    assert any(r["tailNumber"] == "N812BB" and "36" in r["chapter"] for r in answers["cq02"])


def test_cq03_rogue_units_are_bleed_valves(answers, generated):
    serials = {r["serialNumber"] for r in answers["cq03"]}
    assert "BV10457" in serials
    assert sum(s.startswith("BV") for s in serials) / len(serials) >= 0.8


def test_cq05_flags_the_repair_shop(answers):
    rows = answers["cq05"]
    assert rows[0]["vendorCode"] == "V05" and rows[0]["meanHoursToRemoval"] < 1000
    assert all(r["meanHoursToRemoval"] > 3000 for r in rows[1:])


def test_cq06_cq07(answers):
    assert all(r["expiryDate"] <= "2026-10-02" for r in answers["cq06"]) and len(answers["cq06"]) >= 3
    assert {r["model"] for r in answers["cq07"]} == {"737 MAX 8"}


def test_cq08_station_fix_effectiveness(answers):
    assert answers["cq08"][0]["stationCode"] == "BWI"
    assert answers["cq08"][0]["repeatPct"] >= 25


def test_cq09_pneumatic_leads_delays(answers):
    assert "36" in answers["cq09"][0]["chapter"]


def test_cq10_exposure(answers):
    assert all(r["serialNumber"].startswith("BV") for r in answers["cq10"])


def test_parameters_are_validated():
    qs = competency.load_all()
    assert '"N700BB"' in qs["cq01"].bind({"tailNumber": "N700BB"})
    assert "BIND(5 AS ?windowDays)" in qs["cq02"].bind({"windowDays": "5"})
    for bad in ('N812BB" } DROP ALL #', "812BB"):
        with pytest.raises(ValueError):
            qs["cq01"].bind({"tailNumber": bad})


def test_select_vars():
    assert select_vars("SELECT ?a (COUNT(?x) AS ?n) (ROUND(AVG(?y)) AS ?m) WHERE {}") == ["a", "n", "m"]
