"""Single source of truth for IRIs, named graphs and the business entity types.

Everything that builds or parses an IRI (the CSV-to-RDF mapping, the explorer API, the
competency queries, the lakehouse export, the UI) goes through this module, so the identifiers stay consistent.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote, unquote

BASE = "https://fleet.example.com/"
FRO = BASE + "ontology#"           # the fleet reliability ontology (classes, properties)
ID = BASE + "id/"                  # instance data
GRAPH = BASE + "graph/"            # named graphs in Neptune

SKOS = "http://www.w3.org/2004/02/skos/core#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
OWL = "http://www.w3.org/2002/07/owl#"
XSD = "http://www.w3.org/2001/XMLSchema#"
SH = "http://www.w3.org/ns/shacl#"

# One named graph per source, so each can be reloaded or dropped on its own.
# Neptune's default graph is the union of all named graphs, so queries see everything.
GRAPH_ONTOLOGY = GRAPH + "ontology"     # ontology/fleet.ttl
GRAPH_REFERENCE = GRAPH + "reference"   # reference/*.ttl (ATA chapters, defect statuses)
GRAPH_DATA = GRAPH + "data"             # transformed maintenance records
GRAPH_INFERRED = GRAPH + "inferred"     # triples materialized by fleet_kg.rules
ALL_GRAPHS = (GRAPH_ONTOLOGY, GRAPH_REFERENCE, GRAPH_DATA, GRAPH_INFERRED)

PREFIXES = {
    "fro": FRO, "frd": ID, "skos": SKOS, "rdf": RDF, "rdfs": RDFS,
    "owl": OWL, "xsd": XSD, "sh": SH,
}


def sparql_prefixes(names: tuple[str, ...] = ("fro", "frd", "skos", "rdf", "rdfs", "xsd")) -> str:
    return "".join(f"PREFIX {n}: <{PREFIXES[n]}>\n" for n in names)


@dataclass(frozen=True)
class EntityType:
    key: str          # API / UI key
    cls: str          # ontology class local name
    path: str         # IRI path segment
    id_prop: str      # identifier property local name
    label: str        # display name (singular)
    plural: str


ENTITY_TYPES: tuple[EntityType, ...] = (
    EntityType("aircraft", "Aircraft", "aircraft", "tailNumber", "Aircraft", "Aircraft"),
    EntityType("defect", "Defect", "defect", "defectNumber", "Defect", "Defects"),
    EntityType("workOrder", "WorkOrder", "work-order", "workOrderNumber", "Work Order", "Work Orders"),
    EntityType("deferral", "Deferral", "deferral", "deferralNumber", "MEL Deferral", "MEL Deferrals"),
    EntityType("removal", "ComponentRemoval", "removal", "removalNumber", "Component Removal",
               "Removals"),
    EntityType("component", "ComponentUnit", "component", "serialNumber", "Component", "Components"),
    EntityType("part", "Part", "part", "partNumber", "Part", "Parts"),
    EntityType("vendor", "Vendor", "vendor", "vendorCode", "Vendor", "Vendors"),
    EntityType("station", "Station", "station", "stationCode", "Station", "Stations"),
    EntityType("flight", "FlightLeg", "flight", "flightLegId", "Flight", "Flights"),
    EntityType("directive", "AirworthinessDirective", "directive", "adNumber",
               "Airworthiness Directive", "Directives"),
    EntityType("ataChapter", "AtaChapter", "ata", "ataCode", "ATA Chapter", "ATA Chapters"),
)
BY_KEY = {t.key: t for t in ENTITY_TYPES}
BY_CLASS = {FRO + t.cls: t for t in ENTITY_TYPES}
BY_PATH = {t.path: t for t in ENTITY_TYPES}


def iri(type_key: str, ident: str) -> str:
    """IRI for a business entity, e.g. iri('aircraft', 'N812BB')."""
    return f"{ID}{BY_KEY[type_key].path}/{quote(str(ident), safe='')}"


def parse_iri(value: str) -> tuple[EntityType, str] | None:
    """Inverse of iri(): returns (type, identifier) or None for non-entity IRIs."""
    if not value.startswith(ID):
        return None
    path, _, ident = value[len(ID):].partition("/")
    t = BY_PATH.get(path)
    return (t, unquote(ident)) if t and ident else None


def fro(local: str) -> str:
    return FRO + local
