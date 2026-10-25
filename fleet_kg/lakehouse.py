"""Ontology-driven lakehouse: the same ontology, projected into Delta tables for Databricks.

The knowledge graph and the lakehouse are two physical models of one logical model. Nothing here
is hand-maintained per table: the table layout, column types, keys, comments and tags are all
derived from ontology/fleet.ttl, and the rows are projected from the same SHACL-validated RDF
that is loaded into Neptune. So a definition changed in the ontology changes both.

    ontology class            -> table (dim_* for things, fact_* for events)
    datatype property         -> column (xsd type -> Spark/Databricks type)
    functional object property-> foreign-key column holding the target's business key
    business-key property     -> primary key
    skos:definition / label   -> table and column COMMENTs
    class / property IRIs     -> Unity Catalog tags (ontology_class, ontology_property)

Outputs:
    staging rows (JSON Lines) + a schema document  -> the Glue job writes them as Delta tables
    unity_catalog.sql                              -> run in Databricks to register the tables
    metric_views/*.sql                             -> Unity Catalog metric views (YAML 1.1)
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from decimal import Decimal

from fleet_kg.namespaces import BY_CLASS, BY_KEY, FRO, ID, parse_iri

# Ontology class -> table. dim_ = things that persist, fact_ = events.
TABLES = (
    ("dim_station", "Station"), ("dim_vendor", "Vendor"), ("dim_ata_chapter", "AtaChapter"),
    ("dim_part", "Part"), ("dim_aircraft", "Aircraft"), ("dim_component_unit", "ComponentUnit"),
    ("dim_airworthiness_directive", "AirworthinessDirective"),
    ("fact_defect", "Defect"), ("fact_deferral", "Deferral"), ("fact_work_order", "WorkOrder"),
    ("fact_component_removal", "ComponentRemoval"), ("fact_flight_impact", "FlightLeg"),
)
TABLE_NAMES = tuple(t for t, _ in TABLES)
TABLE_BY_CLASS = {c: t for t, c in TABLES}

# Properties declared on a superclass that apply to these classes only.
BROAD = {"description": {"Defect"}, "city": {"Vendor", "Station"},
         "inAtaChapter": {"Defect", "Part", "AirworthinessDirective"}}
# Helper attributes that exist for graph queries only (Spark has date functions).
GRAPH_ONLY = {"reportedDayNumber", "closeDayNumber", "identifier"}
MULTI_VALUED = {"appliesToModel"}
# Classes whose display name (rdfs:label) is a real attribute.
NAMED = {"Station", "Vendor", "Part", "AtaChapter"}

XSD = "http://www.w3.org/2001/XMLSchema#"
TYPES = {XSD + "string": "STRING", XSD + "date": "DATE", XSD + "decimal": "DECIMAL(14,2)",
         XSD + "integer": "BIGINT", XSD + "boolean": "BOOLEAN"}


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


@dataclass
class Column:
    name: str
    type: str
    comment: str
    prop: str | None                 # ontology property local name (None for name/system_group)
    primary_key: bool = False
    references: tuple[str, str] | None = None   # (table, column)

    @property
    def nullable(self) -> bool:
        return not self.primary_key


@dataclass
class Table:
    name: str
    cls: str
    comment: str
    columns: list[Column] = field(default_factory=list)

    @property
    def key(self) -> Column:
        return next(c for c in self.columns if c.primary_key)


def _text(g, subject, *preds) -> str:
    for p in preds:
        v = g.value(subject, p)
        if v is not None:
            text = str(v)
            return text[0].upper() + text[1:]
    return ""


def table_specs(ontology) -> list[Table]:
    """Derive every table from the ontology graph (rdflib.Graph of ontology/fleet.ttl)."""
    from rdflib import OWL, RDF, RDFS, URIRef
    from rdflib.namespace import SKOS

    def local(x):
        return str(x)[len(FRO):]

    id_prop = {t.cls: t.id_prop for t in BY_KEY.values()}
    functional = set(map(local, ontology.subjects(RDF.type, OWL.FunctionalProperty)))
    tables = []
    for table_name, cls in TABLES:
        c_iri = URIRef(FRO + cls)
        comment = _text(ontology, c_iri, SKOS.definition, RDFS.label)
        cols = [Column(snake(id_prop[cls]), "STRING",
                       _text(ontology, URIRef(FRO + id_prop[cls]), SKOS.definition, RDFS.label),
                       id_prop[cls], primary_key=True)]
        if cls in NAMED:
            cols.append(Column("name", "STRING", f"Display name (rdfs:label) of the {cls}.", None))
        for p in sorted(ontology.subjects(RDFS.domain, None), key=str):
            if not str(p).startswith(FRO):
                continue
            name = local(p)
            dom = local(ontology.value(p, RDFS.domain))
            if name in GRAPH_ONLY or name == id_prop[cls]:
                continue
            if dom != cls and cls not in BROAD.get(name, ()):
                continue
            label = _text(ontology, p, SKOS.definition, RDFS.label)
            rng = ontology.value(p, RDFS.range)
            if (p, RDF.type, OWL.DatatypeProperty) in ontology:
                typ = TYPES.get(str(rng), "STRING")
                if name in MULTI_VALUED:
                    typ = "ARRAY<STRING>"
                cols.append(Column(snake(name), typ, label, name))
            elif (p, RDF.type, OWL.ObjectProperty) in ontology and name in functional:
                target = local(rng)
                if target == "DefectStatus":
                    cols.append(Column("status", "STRING", "Defect status: OPEN, DEFERRED or CLOSED.", name))
                    continue
                t_table = TABLE_BY_CLASS.get(target)
                if not t_table:
                    continue
                ref_col = snake(id_prop[target])
                cols.append(Column(snake(name), "STRING",
                                   f"{label[0].upper() + label[1:]} ({BY_CLASS[FRO + target].label} "
                                   f"{ref_col.replace('_', ' ')}).", name,
                                   references=(t_table, ref_col)))
        if cls == "AtaChapter":
            cols.append(Column("system_group", "STRING",
                               "ATA code of the top-level system group (skos:broader).", "broader",
                               references=("dim_ata_chapter", "ata_code")))
        tables.append(Table(table_name, cls, comment, cols))
    return tables


# --------------------------------------------------------------------------- rows

def _value(v):
    from rdflib import Literal
    if isinstance(v, Literal):
        py = v.toPython()
        if isinstance(py, Decimal):
            return float(py)
        if hasattr(py, "isoformat"):
            return py.isoformat()
        return py
    parsed = parse_iri(str(v))
    if parsed:
        return parsed[1]
    s = str(v)
    return s.rsplit("/", 1)[-1]          # concept IRIs, e.g. defect status -> CLOSED


def project_rows(data, reference, specs: list[Table]) -> dict[str, list[dict]]:
    """Rows for every table, read from the validated RDF (instance data + reference data)."""
    from rdflib import RDF, RDFS, URIRef
    from rdflib.namespace import SKOS

    out = {}
    for t in specs:
        graph = reference if t.cls == "AtaChapter" else data
        rows = []
        for s in sorted(graph.subjects(RDF.type, URIRef(FRO + t.cls)), key=str):
            row = {}
            for c in t.columns:
                if c.name == "name":
                    v = graph.value(s, SKOS.prefLabel) or graph.value(s, RDFS.label)
                    row["name"] = str(v) if v is not None else None
                elif c.prop == "broader":
                    v = graph.value(s, SKOS.broader)
                    row[c.name] = str(v).rsplit("/", 1)[-1] if v is not None else None
                elif c.type == "ARRAY<STRING>":
                    row[c.name] = sorted(str(v) for v in graph.objects(s, URIRef(FRO + c.prop)))
                else:
                    v = graph.value(s, URIRef(FRO + c.prop))
                    row[c.name] = _value(v) if v is not None else None
            rows.append(row)
        out[t.name] = rows
    return out


def schema_document(specs: list[Table]) -> dict:
    """What the Glue job needs to build Spark schemas."""
    return {"tables": [{"name": t.name, "ontologyClass": f"fro:{t.cls}",
                        "columns": [{"name": c.name, "type": c.type, "nullable": c.nullable}
                                    for c in t.columns]} for t in specs]}


def jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(r, separators=(",", ":"), default=str) + "\n" for r in rows)


# --------------------------------------------------------------------------- Unity Catalog

def _q(text: str) -> str:
    return "'" + text.replace("\\", "\\\\").replace("'", "\\'") + "'"


def unity_catalog_sql(specs: list[Table], location: str, catalog: str = "fleet_reliability",
                      schema: str = "maintenance") -> str:
    """Databricks SQL that registers the Delta tables in Unity Catalog with the ontology's
    definitions as comments, keys as informational constraints and IRIs as tags."""
    fq = f"{catalog}.{schema}"
    out = [
        "-- Generated from ontology/fleet.ttl by fleet_kg/lakehouse.py. Do not edit by hand.",
        "-- Prerequisite: a Unity Catalog external location covering the path below",
        "-- (see docs/databricks.md). Run in a SQL warehouse or notebook with Unity Catalog.",
        "",
        f"CREATE CATALOG IF NOT EXISTS {catalog};",
        f"CREATE SCHEMA IF NOT EXISTS {fq}",
        f"  COMMENT 'Fleet reliability: one logical model (the ontology) shared with the Neptune knowledge graph';",
        "",
    ]
    for t in specs:
        path = f"{location.rstrip('/')}/{t.name}"
        out += [f"-- {t.name}: ontology class fro:{t.cls}",
                f"CREATE TABLE IF NOT EXISTS {fq}.{t.name} USING DELTA LOCATION {_q(path)};",
                f"COMMENT ON TABLE {fq}.{t.name} IS {_q(t.comment)};",
                f"ALTER TABLE {fq}.{t.name} SET TAGS ('ontology_class' = 'fro:{t.cls}', "
                f"'ontology_iri' = '{FRO}{t.cls}');"]
        for c in t.columns:
            out.append(f"ALTER TABLE {fq}.{t.name} ALTER COLUMN {c.name} COMMENT {_q(c.comment)};")
            if c.prop and c.prop != "broader":
                out.append(f"ALTER TABLE {fq}.{t.name} ALTER COLUMN {c.name} "
                           f"SET TAGS ('ontology_property' = 'fro:{c.prop}');")
        k = t.key
        out += [f"ALTER TABLE {fq}.{t.name} ALTER COLUMN {k.name} SET NOT NULL;",
                f"ALTER TABLE {fq}.{t.name} ADD CONSTRAINT {t.name}_pk PRIMARY KEY ({k.name});", ""]
    out.append("-- Relationships: informational foreign keys, one per single-valued ontology relationship")
    for t in specs:
        for c in t.columns:
            if c.references:
                rt, rc = c.references
                out.append(f"ALTER TABLE {fq}.{t.name} ADD CONSTRAINT {t.name}_{c.name}_fk "
                           f"FOREIGN KEY ({c.name}) REFERENCES {fq}.{rt} ({rc});")
    return "\n".join(out) + "\n"


def metric_views(catalog: str = "fleet_reliability", schema: str = "maintenance") -> dict[str, str]:
    """Unity Catalog metric views (YAML spec 1.1) for the pilot's reliability KPIs."""
    fq = f"{catalog}.{schema}"
    # Source columns are referenced bare, joined columns with the join name, nested joins by
    # chaining names (aircraft.x, unit.part.y), as in the Databricks metric view docs. Join
    # conditions use bare names, which the ontology-derived column names keep unambiguous.
    views = {
        "mv_defects": f"""version: 1.1
comment: "Defects by fleet type, ATA chapter and station. Source: fro:Defect."
source: {fq}.fact_defect
joins:
  - name: aircraft
    source: {fq}.dim_aircraft
    'on': defect_on = tail_number
  - name: chapter
    source: {fq}.dim_ata_chapter
    'on': in_ata_chapter = ata_code
dimensions:
  - name: Reported Month
    expr: DATE_TRUNC('MONTH', reported_date)
  - name: Aircraft Model
    expr: aircraft.aircraft_model
  - name: ATA Chapter
    expr: CONCAT(chapter.ata_code, ' ', chapter.name)
  - name: System Group
    expr: chapter.system_group
  - name: Station
    expr: reported_at
  - name: Report Source
    expr: report_source
measures:
  - name: Defects
    expr: COUNT(1)
  - name: Pilot Reports
    expr: COUNT(1) FILTER (WHERE report_source = 'Pilot report')
  - name: Open Or Deferred
    expr: COUNT(1) FILTER (WHERE status IN ('OPEN', 'DEFERRED'))
""",
        "mv_component_removals": f"""version: 1.1
comment: "Unscheduled removals and time to removal by part and by the shop that last repaired the unit. Source: fro:ComponentRemoval."
source: {fq}.fact_component_removal
joins:
  - name: unit
    source: {fq}.dim_component_unit
    'on': removed_unit = serial_number
    joins:
      - name: part
        source: {fq}.dim_part
        'on': of_part = part_number
  - name: shop
    source: {fq}.dim_vendor
    'on': after_repair_by = vendor_code
dimensions:
  - name: Removal Month
    expr: DATE_TRUNC('MONTH', removal_date)
  - name: Part
    expr: CONCAT(unit.part.part_number, ' ', unit.part.name)
  - name: Repaired By
    expr: shop.name
  - name: Shop Finding
    expr: shop_finding
measures:
  - name: Unscheduled Removals
    expr: COUNT(1) FILTER (WHERE unscheduled)
  - name: Mean Hours To Removal
    expr: AVG(hours_since_install)
  - name: No Fault Found Rate
    expr: AVG(CASE WHEN shop_finding = 'No fault found' THEN 1.0 ELSE 0.0 END)
""",
        "mv_operational_impact": f"""version: 1.1
comment: "Flights delayed or cancelled by maintenance defects. Source: fro:FlightLeg."
source: {fq}.fact_flight_impact
joins:
  - name: defect
    source: {fq}.fact_defect
    'on': delayed_by = defect_number
    joins:
      - name: chapter
        source: {fq}.dim_ata_chapter
        'on': in_ata_chapter = ata_code
dimensions:
  - name: Flight Month
    expr: DATE_TRUNC('MONTH', flight_date)
  - name: Departure Station
    expr: departed_from
  - name: ATA Chapter
    expr: CONCAT(defect.chapter.ata_code, ' ', defect.chapter.name)
measures:
  - name: Flights Impacted
    expr: COUNT(1)
  - name: Delay Minutes
    expr: SUM(delay_minutes)
  - name: Cancellations
    expr: COUNT(1) FILTER (WHERE cancelled)
""",
    }
    return {name: f"CREATE OR REPLACE VIEW {fq}.{name}\nWITH METRICS\nLANGUAGE YAML\nAS $$\n{yaml}$$;\n"
            for name, yaml in views.items()}
