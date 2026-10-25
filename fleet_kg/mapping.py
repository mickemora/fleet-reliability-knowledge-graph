"""Transform: source CSV extracts -> RDF that uses the fleet reliability ontology.

Runs in the rdf-tools Lambda (reading the CSVs from S3) and locally (tests, the local explorer).
Each CSV column maps to one ontology property; derived values (day numbers) are called out.
Missing or malformed values are passed through or left out so SHACL validation reports them.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping

from fleet_kg.namespaces import FRO, ID, iri

TABLES = ("stations", "vendors", "parts", "aircraft", "components", "defects", "work_orders",
          "removals", "deferrals", "directives", "flights")
DAY_ZERO = date(2020, 1, 1)


def _rdflib():
    import rdflib  # lazily: the VPC Lambdas never need it
    return rdflib


def read_tables(texts: Mapping[str, str]) -> dict[str, list[dict]]:
    return {name: list(csv.DictReader(io.StringIO(texts[name]))) for name in TABLES if name in texts}


def read_dir(path) -> dict[str, list[dict]]:
    from pathlib import Path
    p = Path(path)
    return read_tables({n: (p / f"{n}.csv").read_text(encoding="utf-8")
                        for n in TABLES if (p / f"{n}.csv").exists()})


def day_number(value: str | None) -> int | None:
    try:
        return (date.fromisoformat(value) - DAY_ZERO).days
    except (TypeError, ValueError):
        return None


class _Builder:
    def __init__(self):
        rdflib = _rdflib()
        self.rdflib = rdflib
        self.g = rdflib.Graph()
        self.g.bind("fro", FRO)
        self.g.bind("frd", ID)
        self.XSD = rdflib.XSD
        self.counts: dict[str, int] = {}

    def node(self, type_key: str, ident: str):
        return self.rdflib.URIRef(iri(type_key, ident))

    def entity(self, type_key: str, cls: str, ident: str, label: str | None):
        s = self.node(type_key, ident)
        self.g.add((s, self.rdflib.RDF.type, self.rdflib.URIRef(FRO + cls)))
        if label:
            self.g.add((s, self.rdflib.RDFS.label, self.rdflib.Literal(label)))
        self.counts[cls] = self.counts.get(cls, 0) + 1
        return s

    def lit(self, s, prop: str, value, kind: str = "string"):
        if value is None or str(value).strip() == "":
            return
        v = str(value).strip()
        L, X = self.rdflib.Literal, self.XSD
        lit = L(v)
        try:
            if kind == "integer":
                lit = L(int(v), datatype=X.integer)
            elif kind == "decimal":
                lit = L(Decimal(v), datatype=X.decimal)
            elif kind == "date":
                date.fromisoformat(v)
                lit = L(v, datatype=X.date)
            elif kind == "boolean":
                lit = L(v.lower() == "true", datatype=X.boolean)
        except (ValueError, InvalidOperation):
            pass
        self.g.add((s, self.rdflib.URIRef(FRO + prop), lit))

    def rel(self, s, prop: str, type_key: str, ident: str | None):
        if ident is None or str(ident).strip() == "":
            return
        self.g.add((s, self.rdflib.URIRef(FRO + prop), self.node(type_key, str(ident).strip())))


def to_graph(tables: Mapping[str, Iterable[dict]]):
    """Build the data graph. Returns (rdflib.Graph, summary dict)."""
    b = _Builder()
    rdflib = b.rdflib

    for r in tables.get("stations", []):
        s = b.entity("station", "Station", r["station_code"], f'{r["station_code"]} {r["name"]}')
        b.lit(s, "stationCode", r["station_code"])
        for col, prop in (("city", "city"), ("state", "state"), ("station_type", "stationType")):
            b.lit(s, prop, r[col])

    for r in tables.get("vendors", []):
        s = b.entity("vendor", "Vendor", r["vendor_code"], r["name"])
        b.lit(s, "vendorCode", r["vendor_code"])
        for col, prop in (("vendor_type", "vendorType"), ("city", "city"), ("country", "country")):
            b.lit(s, prop, r[col])

    for r in tables.get("parts", []):
        s = b.entity("part", "Part", r["part_number"], r["part_name"])
        b.lit(s, "partNumber", r["part_number"])
        b.rel(s, "inAtaChapter", "ataChapter", r["ata_chapter"])
        b.rel(s, "manufacturedBy", "vendor", r["manufacturer_code"])
        b.lit(s, "unitCost", r["unit_cost"], "decimal")
        b.lit(s, "mtburTarget", r["mtbur_target_hours"], "integer")

    for r in tables.get("aircraft", []):
        s = b.entity("aircraft", "Aircraft", r["tail_number"], f'{r["tail_number"]} {r["model"]}')
        b.lit(s, "tailNumber", r["tail_number"])
        for col, prop in (("model", "aircraftModel"), ("msn", "msn"), ("engine_type", "engineType")):
            b.lit(s, prop, r[col])
        b.lit(s, "deliveryDate", r["delivery_date"], "date")
        b.lit(s, "flightHours", r["flight_hours"], "decimal")
        b.lit(s, "flightCycles", r["flight_cycles"], "integer")
        b.lit(s, "cyclesInPeriod", r.get("cycles_in_period"), "integer")
        b.rel(s, "homeBase", "station", r["home_base"])

    for r in tables.get("components", []):
        s = b.entity("component", "ComponentUnit", r["serial_number"],
                     f'{r["part_number"]} S/N {r["serial_number"]}')
        b.lit(s, "serialNumber", r["serial_number"])
        b.rel(s, "ofPart", "part", r["part_number"])
        b.rel(s, "lastRepairedBy", "vendor", r["last_repaired_by"])
        b.lit(s, "lastShopVisitDate", r["last_shop_visit_date"], "date")
        b.rel(s, "installedOn", "aircraft", r.get("installed_on"))

    status_base = ID + "defect-status/"
    for r in tables.get("defects", []):
        s = b.entity("defect", "Defect", r["defect_number"], r["defect_number"])
        b.lit(s, "defectNumber", r["defect_number"])
        b.rel(s, "defectOn", "aircraft", r["tail_number"])
        b.rel(s, "reportedAt", "station", r["station_code"])
        b.rel(s, "inAtaChapter", "ataChapter", r["ata_chapter"])
        if r.get("status"):
            b.g.add((s, rdflib.URIRef(FRO + "hasStatus"), rdflib.URIRef(status_base + r["status"])))
        b.lit(s, "reportedDate", r["reported_date"], "date")
        b.lit(s, "reportedDayNumber", day_number(r["reported_date"]), "integer")
        b.lit(s, "reportSource", r["source"])
        b.lit(s, "description", r["description"])

    for r in tables.get("deferrals", []):
        s = b.entity("deferral", "Deferral", r["deferral_number"], r["deferral_number"])
        b.lit(s, "deferralNumber", r["deferral_number"])
        b.rel(s, "defers", "defect", r["defect_number"])
        b.rel(s, "deferralOn", "aircraft", r["tail_number"])
        b.lit(s, "melItem", r["mel_item"])
        b.lit(s, "melCategory", r["category"])
        for col, prop in (("deferred_date", "deferredDate"), ("expiry_date", "expiryDate"),
                          ("cleared_date", "clearedDate")):
            b.lit(s, prop, r[col], "date")

    for r in tables.get("work_orders", []):
        s = b.entity("workOrder", "WorkOrder", r["work_order_number"], r["work_order_number"])
        b.lit(s, "workOrderNumber", r["work_order_number"])
        b.rel(s, "workOrderOn", "aircraft", r["tail_number"])
        b.rel(s, "performedAt", "station", r["station_code"])
        b.rel(s, "corrects", "defect", r.get("corrects_defect"))
        b.rel(s, "accomplishes", "directive", r.get("accomplishes_directive"))
        b.lit(s, "openDate", r["open_date"], "date")
        b.lit(s, "closeDate", r["close_date"], "date")
        b.lit(s, "closeDayNumber", day_number(r["close_date"]), "integer")
        b.lit(s, "action", r["action"])
        b.lit(s, "laborHours", r["labor_hours"], "decimal")

    for r in tables.get("removals", []):
        s = b.entity("removal", "ComponentRemoval", r["removal_number"], r["removal_number"])
        b.lit(s, "removalNumber", r["removal_number"])
        b.rel(s, "removedUnit", "component", r["serial_number"])
        b.rel(s, "removedFrom", "aircraft", r["tail_number"])
        b.rel(s, "duringWorkOrder", "workOrder", r["work_order_number"])
        b.rel(s, "afterRepairBy", "vendor", r["after_repair_by"])
        b.lit(s, "removalDate", r["removal_date"], "date")
        b.lit(s, "unscheduled", r["unscheduled"], "boolean")
        b.lit(s, "hoursSinceInstall", r["hours_since_install"], "decimal")
        b.lit(s, "shopFinding", r["shop_finding"])
        b.lit(s, "removalReason", r["reason"])

    for r in tables.get("directives", []):
        s = b.entity("directive", "AirworthinessDirective", r["ad_number"], r["ad_number"])
        b.lit(s, "adNumber", r["ad_number"])
        b.lit(s, "title", r["title"])
        b.rel(s, "inAtaChapter", "ataChapter", r["ata_chapter"])
        b.lit(s, "effectiveDate", r["effective_date"], "date")
        b.lit(s, "complianceDate", r["compliance_date"], "date")
        for model in filter(None, r["applies_to_models"].split("|")):
            b.lit(s, "appliesToModel", model)

    for r in tables.get("flights", []):
        s = b.entity("flight", "FlightLeg", r["flight_leg_id"],
                     f'{r["flight_number"]} {r["flight_date"]}')
        b.lit(s, "flightLegId", r["flight_leg_id"])
        b.lit(s, "flightNumber", r["flight_number"])
        b.lit(s, "flightDate", r["flight_date"], "date")
        b.rel(s, "operatedBy", "aircraft", r["tail_number"])
        b.rel(s, "departedFrom", "station", r["departure_station"])
        b.rel(s, "delayedBy", "defect", r["delay_defect"])
        b.lit(s, "delayMinutes", r["delay_minutes"], "integer")
        b.lit(s, "cancelled", r["cancelled"], "boolean")

    return b.g, {"triples": len(b.g), "entities": b.counts}


def to_turtle(tables: Mapping[str, Iterable[dict]]) -> tuple[str, dict]:
    g, summary = to_graph(tables)
    return g.serialize(format="turtle"), summary
