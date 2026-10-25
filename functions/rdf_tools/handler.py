"""RDF tools Lambda (outside the VPC; needs rdflib + pySHACL, bundled at synth time).

Pipeline steps:
  {"action": "transform"}   raw/*.csv in S3 -> rdf/data/fleet-data.ttl  (fleet_kg.mapping)
  {"action": "validate"}    SHACL-validate rdf/data + reference against shapes/ (fleet_kg.validation);
                            writes reports/shacl/<timestamp>.ttl and reports/latest.json
  {"action": "export_lakehouse"}
                            project the validated RDF into ontology-shaped tables (fleet_kg.lakehouse):
                            lakehouse/staging/<table>.jsonl + _schema.json for the Glue Delta job, and
                            lakehouse/databricks/ (Unity Catalog SQL and metric views for this bucket)
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import boto3

from fleet_kg import lakehouse, mapping, validation

s3 = boto3.client("s3")


def _bucket() -> str:
    return os.environ["DATA_BUCKET"]


def _read(key: str) -> str:
    return s3.get_object(Bucket=_bucket(), Key=key)["Body"].read().decode("utf-8")


def _put(key: str, body: str, content_type: str) -> None:
    s3.put_object(Bucket=_bucket(), Key=key, Body=body.encode("utf-8"), ContentType=content_type)


def _keys(prefix: str, suffix: str) -> list[str]:
    keys = []
    for page in s3.get_paginator("list_objects_v2").paginate(Bucket=_bucket(), Prefix=prefix):
        keys += [o["Key"] for o in page.get("Contents", []) if o["Key"].endswith(suffix)]
    return sorted(keys)


def _graph(prefix: str):
    from rdflib import Graph
    g = Graph()
    for key in _keys(prefix, ".ttl"):
        g.parse(data=_read(key), format="turtle")
    return g


def action_transform(_event):
    texts = {name: _read(f"raw/{name}.csv") for name in mapping.TABLES}
    turtle, summary = mapping.to_turtle(mapping.read_tables(texts))
    _put("rdf/data/fleet-data.ttl", turtle, "text/turtle")
    _put("reports/transform-summary.json", json.dumps(summary, indent=2), "application/json")
    return summary


def action_validate(event):
    data = _graph("rdf/data/")
    for triple in _graph("reference/"):
        data.add(triple)
    summary, report = validation.validate(data, _graph("shapes/"), _graph("ontology/"))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    report_key = f"reports/shacl/{stamp}.ttl"
    _put(report_key, report, "text/turtle")
    summary.update({"reportKey": report_key, "validatedAt": stamp,
                    "execution": (event or {}).get("execution")})
    _put("reports/latest.json", json.dumps(summary, indent=2), "application/json")
    # Step Functions payloads are capped at 256 KB: return the summary, not every result.
    return {k: v for k, v in summary.items() if k != "results"} | {
        "topResults": summary["results"][:10]}


def action_export_lakehouse(_event):
    specs = lakehouse.table_specs(_graph("ontology/"))
    rows = lakehouse.project_rows(_graph("rdf/data/"), _graph("reference/"), specs)
    staging = "lakehouse/staging"
    for name, table_rows in rows.items():
        _put(f"{staging}/{name}.jsonl", lakehouse.jsonl(table_rows), "application/x-ndjson")
    _put(f"{staging}/_schema.json", json.dumps(lakehouse.schema_document(specs), indent=2),
         "application/json")
    location = f"s3://{_bucket()}/lakehouse/delta"
    _put("lakehouse/databricks/unity_catalog.sql", lakehouse.unity_catalog_sql(specs, location),
         "text/plain")
    for name, sql in lakehouse.metric_views().items():
        _put(f"lakehouse/databricks/metric_views/{name}.sql", sql, "text/plain")
    return {"tables": {name: len(r) for name, r in rows.items()}, "deltaLocation": location}


ACTIONS = {"transform": action_transform, "validate": action_validate,
           "export_lakehouse": action_export_lakehouse}


def handler(event, _context=None):
    action = (event or {}).get("action")
    if action not in ACTIONS:
        raise ValueError(f"unknown action {action!r}; one of {sorted(ACTIONS)}")
    return ACTIONS[action](event)
