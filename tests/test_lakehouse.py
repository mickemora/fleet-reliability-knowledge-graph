"""The ontology-driven lakehouse: table model, rows, Unity Catalog SQL, metric views, and
parity with the knowledge graph (the same questions give the same answers)."""

import json
import re
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("rdflib")
from rdflib import Graph  # noqa: E402

from fleet_kg import competency, lakehouse, mapping  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def specs():
    return lakehouse.table_specs(Graph().parse(ROOT / "ontology" / "fleet.ttl"))


@pytest.fixture(scope="module")
def rows(specs, generated):
    data, _ = mapping.to_graph(mapping.read_dir(generated[1] / "raw"))
    reference = Graph().parse(ROOT / "reference" / "ata-chapters.ttl")
    return lakehouse.project_rows(data, reference, specs)


def test_one_table_per_class_with_keys(specs):
    assert [t.name for t in specs] == list(lakehouse.TABLE_NAMES)
    names = {t.name: t for t in specs}
    for t in specs:
        assert sum(c.primary_key for c in t.columns) == 1
        assert t.comment, t.name
        for c in t.columns:
            assert c.comment, (t.name, c.name)
            if c.references:
                rt, rc = c.references
                assert names[rt].key.name == rc
    removal = {c.name: c for c in names["fact_component_removal"].columns}
    assert removal["removed_unit"].references == ("dim_component_unit", "serial_number")
    assert removal["hours_since_install"].type.startswith("DECIMAL")
    assert removal["unscheduled"].type == "BOOLEAN"
    assert {c.name: c.type for c in names["dim_airworthiness_directive"].columns}["applies_to_model"] == "ARRAY<STRING>"


def test_rows_match_the_source(rows, generated):
    ds, _ = generated
    assert len(rows["fact_defect"]) == len(ds.defects)
    assert len(rows["dim_component_unit"]) == len(ds.components)
    assert len(rows["dim_ata_chapter"]) == 28
    d = next(r for r in rows["fact_defect"] if r["defect_number"] == "DF-100245")
    assert (d["defect_on"], d["in_ata_chapter"], d["reported_at"], d["status"]) == ("N812BB", "36", "MDW", "CLOSED")
    keys = {r["vendor_code"] for r in rows["dim_vendor"]}
    assert all(r["after_repair_by"] in keys for r in rows["fact_component_removal"])
    json.loads(lakehouse.jsonl(rows["dim_aircraft"]).splitlines()[0])


def test_unity_catalog_sql(specs):
    sql = lakehouse.unity_catalog_sql(specs, "s3://b/lakehouse/delta")
    assert sql.count("CREATE TABLE IF NOT EXISTS") == len(specs)
    assert sql.count("PRIMARY KEY") == len(specs)
    assert sql.count("FOREIGN KEY") == sum(1 for t in specs for c in t.columns if c.references)
    assert "SET TAGS ('ontology_class' = 'fro:ComponentRemoval'" in sql
    assert "'ontology_property' = 'fro:hoursSinceInstall'" in sql
    # every statement ends properly and quotes are balanced
    for stmt in filter(str.strip, re.sub(r"--.*", "", sql).split(";\n")):
        assert stmt.replace("\\'", "").count("'") % 2 == 0, stmt   # \' is Spark's escape


def test_metric_views_reference_real_columns(specs):
    cols = {t.name: {c.name for c in t.columns} for t in specs}
    for name, sql in lakehouse.metric_views().items():
        assert sql.startswith(f"CREATE OR REPLACE VIEW fleet_reliability.maintenance.{name}")
        assert "version: 1.1" in sql and "$$;" in sql
        tables = re.findall(r"source: fleet_reliability\.maintenance\.(\w+)", sql)
        known = set().union(*(cols[t] for t in tables))
        for expr in re.findall(r"(?:expr|'on'): (.+)", sql):
            for ident in re.findall(r"\b([a-z][a-z_]+)\b", expr.split("'")[0] if "'" in expr and "on" not in expr else expr):
                if "_" in ident:
                    assert ident in known, (name, ident)


def test_committed_databricks_files_are_current():
    import importlib.util
    spec = importlib.util.spec_from_file_location("gen", ROOT / "scripts" / "generate_databricks.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    for path, text in gen.render().items():
        assert path.read_text() == text, f"{path} is stale: run python scripts/generate_databricks.py"


def _sqlite(specs, rows):
    db = sqlite3.connect(":memory:")
    for t in specs:
        names = [c.name for c in t.columns]
        db.execute(f"CREATE TABLE {t.name} ({', '.join(names)})")
        db.executemany(f"INSERT INTO {t.name} VALUES ({','.join('?' * len(names))})",
                       [[json.dumps(r[n]) if isinstance(r[n], list) else r[n] for n in names]
                        for r in rows[t.name]])
    return db


def _statements():
    sql = (ROOT / "databricks" / "competency_questions.sql").read_text()
    out = {}
    for block in sql.split(";\n"):
        m = re.search(r"-- (CQ\d\d)", block)
        if m and "MEASURE(" not in block:
            q = re.sub(r"--[^\n]*", "", block)
            q = re.sub(r"date_add\(([^,]+), (\d+)\)", r"date(\1, '+\2 day')", q).replace("FIRST(", "MIN(")
            out[m.group(1).lower()] = q
    return out


def test_databricks_sql_matches_the_graph(specs, rows, kg):
    """Run the Databricks SQL (on SQLite, with two dialect shims) and the SPARQL competency
    questions on the same data: they must agree. Same ontology, same answers."""
    db = _sqlite(specs, rows)
    sql = _statements()
    graph = {q.id: kg.select(q.bind()) for q in competency.load_all().values()}

    lake = {r[0]: r[2] for r in db.execute(sql["cq03"])}
    assert lake == {r["serialNumber"]: r["removals"] for r in graph["cq03"]}

    lake = {r[0]: (r[3], round(r[4])) for r in db.execute(sql["cq05"])}
    assert lake == {r["vendorCode"]: (r["unscheduledRemovals"], round(r["meanHoursToRemoval"]))
                    for r in graph["cq05"]}

    lake = {r[0]: (r[1], r[2]) for r in db.execute(sql["cq08"])}
    assert lake == {r["stationCode"]: (r["fixes"], r["repeatedWithinWindow"]) for r in graph["cq08"]}

    lake = {r[0]: (r[1], r[2], r[3]) for r in db.execute(sql["cq09"])}
    assert lake == {r["chapter"]: (r["flightsImpacted"], r["delayMinutes"], r["cancellations"])
                    for r in graph["cq09"]}
