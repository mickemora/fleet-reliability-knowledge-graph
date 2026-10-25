"""Regenerate the Databricks artifacts in databricks/ and docs/lakehouse-model.md from the ontology.

    python scripts/generate_databricks.py

The deployed pipeline writes the same files, with your bucket's real S3 location, to
s3://<data bucket>/lakehouse/databricks/ (download them with `python scripts/kg.py lakehouse`).
A test checks that the committed copies are up to date with the ontology.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fleet_kg import lakehouse  # noqa: E402

PLACEHOLDER = "s3://<data-bucket>/lakehouse/delta"


def render() -> dict[Path, str]:
    from rdflib import Graph
    specs = lakehouse.table_specs(Graph().parse(ROOT / "ontology" / "fleet.ttl"))
    files = {ROOT / "databricks" / "unity_catalog.sql": lakehouse.unity_catalog_sql(specs, PLACEHOLDER)}
    for name, sql in lakehouse.metric_views().items():
        files[ROOT / "databricks" / "metric_views" / f"{name}.sql"] = sql
    lines = ["# Lakehouse model (generated)", "",
             "Generated from `ontology/fleet.ttl` by `python scripts/generate_databricks.py`. "
             "Each table is one ontology class; each column is one ontology property. "
             "Keys (PK) and foreign keys (FK) come from business-key and single-valued relationship "
             "properties. See [databricks.md](databricks.md) for how this is used.", ""]
    for t in specs:
        lines += [f"## `{t.name}`: `fro:{t.cls}`", "", t.comment, "",
                  "| Column | Type | Ontology property | Key | Description |", "|---|---|---|---|---|"]
        for c in t.columns:
            key = "PK" if c.primary_key else (f"FK → `{c.references[0]}`" if c.references else "")
            prop = f"`fro:{c.prop}`" if c.prop and c.prop != "broader" else ("`skos:broader`" if c.prop else "`rdfs:label`")
            lines.append(f"| `{c.name}` | {c.type} | {prop} | {key} | {c.comment.replace('|', '/')} |")
        lines.append("")
    files[ROOT / "docs" / "lakehouse-model.md"] = "\n".join(lines)
    return files


def main() -> None:
    for path, text in render().items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        print(f"wrote {path.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
