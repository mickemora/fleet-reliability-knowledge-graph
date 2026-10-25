"""Fleet Reliability Explorer API: the read-only queries behind the relationship explorer UI.

Pure logic over any SPARQL client with a `select()` method (NeptuneSparql in Lambda,
LocalSparql in tests and the local server). The HTTP wiring is in functions/explorer_api.

Routes (all GET unless noted, all under /api):
    /stats                          entity counts, delay minutes and cancellations
    /search?q=bleed                 tails, defects, units, parts, vendors, stations, ...
    /entities?type=defect&offset=0  paged list of one entity type
    /entity?iri=...                 attributes of one entity
    /neighborhood?iri=...           connected entities, grouped by relationship (graph view)
    /related?iri=<defect IRI>       the "Related information" panel for a defect
    /competency                     the competency questions
    /competency/cq03?minRemovals=3  run one competency question
"""

from __future__ import annotations

import re
import time

from fleet_kg import competency
from fleet_kg.namespaces import (BY_CLASS, BY_KEY, ENTITY_TYPES, RDFS, SKOS, FRO,
                                    parse_iri, sparql_prefixes)

PFX = sparql_prefixes()
ENTITY_VALUES = " ".join(f"fro:{t.cls}" for t in ENTITY_TYPES)
_SAFE_TEXT = re.compile(r"[^\w\s\-.,&'/]", re.UNICODE)
HIDDEN_PREDICATES = {SKOS + "broaderTransitive", SKOS + "topConceptOf", SKOS + "inScheme",
                     SKOS + "hasTopConcept"}
PER_RELATION = 12
# For a maintenance record the useful picture is wider than one hop: a defect's work order ->
# the removal it included -> the serialized unit and the shop that last repaired it.
# Each entry lists, per extra hop, the relationships to follow from the previous hop's nodes.
EXTRA_HOPS = {
    "defect": (("includesRemoval",), ("removedUnit", "afterRepairBy")),
    "workOrder": (("removedUnit", "afterRepairBy"),),
    "removal": (("ofPart", "lastRepairedBy"),),
    "flight": (("correctedBy", "deferredBy"),),
    "deferral": (("correctedBy",),),
    "component": (("removedFrom",),),
}

ATTRIBUTE_ORDER = [
    "tailNumber", "defectNumber", "workOrderNumber", "deferralNumber", "removalNumber",
    "serialNumber", "partNumber", "vendorCode", "stationCode", "flightLegId", "adNumber", "ataCode",
    "aircraftModel", "msn", "engineType", "deliveryDate", "flightHours", "flightCycles",
    "cyclesInPeriod", "reportedDate", "reportSource", "description", "melItem", "melCategory",
    "deferredDate", "expiryDate", "clearedDate", "openDate", "closeDate", "action", "laborHours",
    "removalDate", "unscheduled", "hoursSinceInstall", "shopFinding", "removalReason",
    "lastShopVisitDate", "unitCost", "mtburTarget", "vendorType", "stationType", "flightNumber",
    "flightDate", "delayMinutes", "cancelled", "title", "effectiveDate", "complianceDate",
    "appliesToModel", "city", "state", "country",
]
HIDDEN_ATTRIBUTES = {"identifier", "reportedDayNumber", "closeDayNumber"}


def select_vars(query: str) -> list[str]:
    """Projected variable names of a SELECT, in order: ?x at the top level and (expr AS ?y)."""
    m = re.search(r"\bSELECT\s+(?:DISTINCT\s+|REDUCED\s+)?(.*?)\bWHERE\b", query, re.S | re.I)
    if not m:
        return []
    clause, out, depth, i = m.group(1), [], 0, 0
    for tok in re.finditer(r"\(|\)|\bAS\s+\?(\w+)|\?(\w+)", clause, re.I):
        if tok.group(0) == "(":
            depth += 1
        elif tok.group(0) == ")":
            depth -= 1
        elif tok.group(1) and depth == 1:
            out.append(tok.group(1))
        elif tok.group(2) and depth == 0:
            out.append(tok.group(2))
    return list(dict.fromkeys(out))


class NotFound(LookupError):
    pass


def lit(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def check_iri(value: str | None) -> str:
    if not value or not parse_iri(value):
        raise ValueError("iri must be a warranty entity IRI (https://warranty.example.com/id/...)")
    if any(c in value for c in '<>"{}|^`\\ '):
        raise ValueError("invalid IRI")
    return value


def _local(iri: str) -> str:
    return iri.split("#")[-1].split("/")[-1]


class Explorer:
    def __init__(self, sparql, cq_dir=None):
        self.sparql = sparql
        self.questions = competency.load_all(cq_dir)

    # ------------------------------------------------------------------ stats
    def stats(self) -> dict:
        rows = self.sparql.select(PFX + f"""
SELECT ?type (COUNT(DISTINCT ?s) AS ?n) WHERE {{
  VALUES ?type {{ {ENTITY_VALUES} }}
  ?s a ?type .
}} GROUP BY ?type""")
        counts = {BY_CLASS[r["type"]].key: r["n"] for r in rows if r["type"] in BY_CLASS}
        impact = self.sparql.select(PFX + """
SELECT (SUM(?m) AS ?minutes) (SUM(IF(?c, 1, 0)) AS ?cancellations) WHERE {
  ?f a fro:FlightLeg ; fro:delayMinutes ?m ; fro:cancelled ?c }""")
        triples = self.sparql.select("SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }")
        return {"counts": {t.key: counts.get(t.key, 0) for t in ENTITY_TYPES},
                "delayMinutes": (impact[0].get("minutes") or 0) if impact else 0,
                "cancellations": (impact[0].get("cancellations") or 0) if impact else 0,
                "triples": triples[0]["n"] if triples else 0,
                "types": [{"key": t.key, "label": t.label, "plural": t.plural}
                          for t in ENTITY_TYPES]}

    # ------------------------------------------------------------------ search
    def search(self, q: str, limit: int = 20) -> dict:
        text = _SAFE_TEXT.sub("", (q or "")).strip().lower()[:60]
        if len(text) < 2:
            raise ValueError("search text must be at least 2 characters")
        # Two steps: match text first (cheap), then describe only the matches.
        matches = self.sparql.select(PFX + f"""
SELECT DISTINCT ?s WHERE {{
  {{ ?s fro:identifier ?text }} UNION {{ ?s rdfs:label ?text }}
  FILTER(CONTAINS(LCASE(STR(?text)), {lit(text)}))
}} LIMIT 300""")
        subjects = [m["s"] for m in matches if parse_iri(m["s"])]
        rows = []
        if subjects:
            values = " ".join(f"<{x}>" for x in subjects)
            rows = self.sparql.select(PFX + f"""
SELECT ?s ?type ?label ?id WHERE {{
  VALUES ?s {{ {values} }}
  ?s a ?type .
  FILTER(?type IN ({", ".join(f"fro:{t.cls}" for t in ENTITY_TYPES)}))
  OPTIONAL {{ ?s rdfs:label ?label }}
  OPTIONAL {{ ?s fro:identifier ?id }}
}}""")
        seen, hits = set(), []
        order = {t.key: i for i, t in enumerate(ENTITY_TYPES)}
        for r in rows:
            if r["s"] in seen:
                continue
            seen.add(r["s"])
            t = BY_CLASS[r["type"]]
            ident = str(r.get("id", ""))
            label = str(r.get("label", ident))
            exact = text in (ident.lower(), label.lower())
            starts = ident.lower().startswith(text) or label.lower().startswith(text)
            hits.append({"iri": r["s"], "type": t.key, "typeLabel": t.label, "label": label,
                         "identifier": ident,
                         "_rank": (0 if exact else 1 if starts else 2, order[t.key], label)})
        hits.sort(key=lambda h: h["_rank"])
        for h in hits:
            h.pop("_rank")
        return {"query": text, "results": hits[:limit], "more": len(hits) > limit}

    # ------------------------------------------------------------------ lists
    LISTS = {
        "aircraft": ("?tailNumber ?aircraftModel ?engineType ?homeBase ?defects", """
  ?s fro:tailNumber ?tailNumber ; fro:aircraftModel ?aircraftModel ; fro:engineType ?engineType ;
     fro:homeBase/fro:stationCode ?homeBase .
  { SELECT ?s (COUNT(?d) AS ?defects) WHERE { ?s a fro:Aircraft . OPTIONAL { ?s fro:hasDefect ?d } } GROUP BY ?s }""",
                     "DESC(?defects) ?tailNumber"),
        "defect": ("?defectNumber ?reportedDate ?tailNumber ?chapter ?stationCode ?status ?description", """
  ?s fro:defectNumber ?defectNumber ; fro:reportedDate ?reportedDate ; fro:description ?description ;
     fro:defectOn/fro:tailNumber ?tailNumber ; fro:inAtaChapter/rdfs:label ?chapter ;
     fro:reportedAt/fro:stationCode ?stationCode ; fro:hasStatus/rdfs:label ?status .""",
                   "DESC(?reportedDate) ?defectNumber"),
        "workOrder": ("?workOrderNumber ?openDate ?tailNumber ?stationCode ?action", """
  ?s fro:workOrderNumber ?workOrderNumber ; fro:openDate ?openDate ; fro:action ?action ;
     fro:workOrderOn/fro:tailNumber ?tailNumber ; fro:performedAt/fro:stationCode ?stationCode .""",
                      "DESC(?openDate) ?workOrderNumber"),
        "deferral": ("?deferralNumber ?tailNumber ?melItem ?melCategory ?deferredDate ?expiryDate ?clearedDate", """
  ?s fro:deferralNumber ?deferralNumber ; fro:melItem ?melItem ; fro:melCategory ?melCategory ;
     fro:deferredDate ?deferredDate ; fro:expiryDate ?expiryDate ; fro:deferralOn/fro:tailNumber ?tailNumber .
  OPTIONAL { ?s fro:clearedDate ?clearedDate }""", "DESC(?deferredDate) ?deferralNumber"),
        "removal": ("?removalNumber ?removalDate ?serialNumber ?part ?tailNumber ?hoursSinceInstall ?shopFinding", """
  ?s fro:removalNumber ?removalNumber ; fro:removalDate ?removalDate ; fro:hoursSinceInstall ?hoursSinceInstall ;
     fro:shopFinding ?shopFinding ; fro:removedFrom/fro:tailNumber ?tailNumber ;
     fro:removedUnit ?u . ?u fro:serialNumber ?serialNumber ; fro:ofPart/rdfs:label ?part .""",
                    "DESC(?removalDate) ?removalNumber"),
        "component": ("?serialNumber ?part ?lastRepairedBy ?lastShopVisitDate ?installedOn ?removals", """
  ?s fro:serialNumber ?serialNumber ; fro:ofPart/rdfs:label ?part ; fro:lastShopVisitDate ?lastShopVisitDate .
  OPTIONAL { ?s fro:lastRepairedBy/rdfs:label ?lastRepairedBy }
  OPTIONAL { ?s fro:installedOn/fro:tailNumber ?installedOn }
  { SELECT ?s (COUNT(?r) AS ?removals) WHERE { ?s a fro:ComponentUnit . OPTIONAL { ?s fro:hasRemoval ?r } } GROUP BY ?s }""",
                      "DESC(?removals) ?serialNumber"),
        "part": ("?partNumber ?label ?chapter ?manufacturer ?units", """
  ?s fro:partNumber ?partNumber ; rdfs:label ?label ; fro:inAtaChapter/rdfs:label ?chapter ;
     fro:manufacturedBy/rdfs:label ?manufacturer .
  { SELECT ?s (COUNT(?u) AS ?units) WHERE { ?s a fro:Part . OPTIONAL { ?s fro:hasUnit ?u } } GROUP BY ?s }""",
                 "?partNumber"),
        "vendor": ("?vendorCode ?label ?vendorType ?city ?country", """
  ?s fro:vendorCode ?vendorCode ; rdfs:label ?label ; fro:vendorType ?vendorType ; fro:city ?city ;
     fro:country ?country .""", "?vendorCode"),
        "station": ("?stationCode ?label ?stationType ?defects", """
  ?s fro:stationCode ?stationCode ; rdfs:label ?label ; fro:stationType ?stationType .
  { SELECT ?s (COUNT(?d) AS ?defects) WHERE { ?s a fro:Station . OPTIONAL { ?s fro:stationDefect ?d } } GROUP BY ?s }""",
                    "DESC(?defects)"),
        "flight": ("?flightLegId ?flightDate ?tailNumber ?stationCode ?delayMinutes ?cancelled", """
  ?s fro:flightLegId ?flightLegId ; fro:flightDate ?flightDate ; fro:delayMinutes ?delayMinutes ;
     fro:cancelled ?cancelled ; fro:operatedBy/fro:tailNumber ?tailNumber ;
     fro:departedFrom/fro:stationCode ?stationCode .""", "DESC(?flightDate) ?flightLegId"),
        "directive": ("?adNumber ?title ?effectiveDate ?complianceDate ?accomplishedBy", """
  ?s fro:adNumber ?adNumber ; fro:title ?title ; fro:effectiveDate ?effectiveDate ;
     fro:complianceDate ?complianceDate .
  { SELECT ?s (COUNT(?w) AS ?accomplishedBy) WHERE { ?s a fro:AirworthinessDirective .
      OPTIONAL { ?s fro:accomplishedBy ?w } } GROUP BY ?s }""", "?adNumber"),
        "ataChapter": ("?ataCode ?label ?group", """
  ?s fro:ataCode ?ataCode ; rdfs:label ?label .
  OPTIONAL { ?s skos:broader/rdfs:label ?group }""", "?ataCode"),
    }

    def entities(self, type_key: str, offset: int = 0, limit: int = 50) -> dict:
        if type_key not in self.LISTS:
            raise ValueError(f"type must be one of {sorted(self.LISTS)}")
        offset, limit = max(0, int(offset)), max(1, min(int(limit), 200))
        t = BY_KEY[type_key]
        cols, where, order = self.LISTS[type_key]
        rows = self.sparql.select(PFX + f"""
SELECT ?s {cols} WHERE {{
  ?s a fro:{t.cls} .{where}
}} ORDER BY {order} LIMIT {limit} OFFSET {offset}""")
        total = self.sparql.select(PFX + f"SELECT (COUNT(?s) AS ?n) WHERE {{ ?s a fro:{t.cls} }}")
        columns = [c.lstrip("?") for c in cols.split()]
        return {"type": type_key, "label": t.plural, "columns": columns,
                "total": total[0]["n"] if total else 0, "offset": offset, "limit": limit,
                "rows": [{"iri": r.pop("s"), **r} for r in rows]}

    # ------------------------------------------------------------------ one entity
    def entity(self, iri: str) -> dict:
        iri = check_iri(iri)
        rows = self.sparql.select(PFX + f"""
SELECT ?p ?o ?plabel WHERE {{
  <{iri}> ?p ?o .
  FILTER(isLiteral(?o))
  OPTIONAL {{ ?p rdfs:label ?plabel }}
}}""")
        types = self.sparql.select(f"SELECT ?t WHERE {{ <{iri}> a ?t }}")
        if not rows and not types:
            raise NotFound(iri)
        t, ident = parse_iri(iri)
        attrs, label = {}, ident
        for r in rows:
            p = r["p"]
            if p == RDFS + "label":
                label = r["o"]
                continue
            name = _local(p)
            if not p.startswith(FRO) or name in HIDDEN_ATTRIBUTES:
                continue
            if name in attrs:   # multi-valued attribute, e.g. a directive's models
                attrs[name]["value"] = f'{attrs[name]["value"]}, {r["o"]}'
            else:
                attrs[name] = {"property": name, "label": r.get("plabel", name), "value": r["o"]}
        order = {n: i for i, n in enumerate(ATTRIBUTE_ORDER)}
        attributes = sorted(attrs.values(), key=lambda a: (order.get(a["property"], 999),
                                                           a["property"]))
        classes = sorted(_local(x["t"]) for x in types if x["t"].startswith(FRO))
        return {"iri": iri, "type": t.key, "typeLabel": t.label, "identifier": ident,
                "label": label, "classes": classes, "attributes": attributes}

    def neighborhood(self, iri: str, per_relation: int = PER_RELATION) -> dict:
        iri = check_iri(iri)
        center = self.entity(iri)
        rows = self.sparql.select(PFX + f"""
SELECT ?p ?plabel ?o ?type ?label WHERE {{
  VALUES ?type {{ {ENTITY_VALUES} }}
  <{iri}> ?p ?o .
  ?o a ?type .
  OPTIONAL {{ ?p rdfs:label ?plabel }}
  OPTIONAL {{ ?o rdfs:label ?label }}
}}""")
        groups: dict[str, dict] = {}
        for r in rows:
            if r["p"] in HIDDEN_PREDICATES or r["o"] == iri:
                continue
            g = groups.setdefault(r["p"], {"predicate": _local(r["p"]),
                                           "label": r.get("plabel", _local(r["p"])),
                                           "total": 0, "nodes": {}})
            if r["o"] not in g["nodes"]:
                g["total"] += 1
                t = BY_CLASS[r["type"]]
                _, ident = parse_iri(r["o"]) or (None, r["o"])
                g["nodes"][r["o"]] = {"iri": r["o"], "type": t.key, "typeLabel": t.label,
                                      "label": r.get("label", ident), "identifier": ident}
        nodes = [{"iri": iri, "type": center["type"], "typeLabel": center["typeLabel"],
                  "label": center["label"], "identifier": center["identifier"],
                  "center": True}]
        edges, relations = [], []
        for pred, g in sorted(groups.items(), key=lambda kv: kv[1]["label"]):
            shown = sorted(g["nodes"].values(), key=lambda n: str(n["label"]))[:per_relation]
            for n in shown:
                nodes.append(n)
                edges.append({"source": iri, "target": n["iri"], "predicate": g["predicate"],
                              "label": g["label"]})
            relations.append({"predicate": g["predicate"], "label": g["label"],
                              "total": g["total"], "shown": len(shown)})
        known = {n["iri"] for n in nodes}
        frontier = [n["iri"] for n in nodes[1:]]
        for hop, predicates in enumerate(EXTRA_HOPS.get(center["type"], ()), start=2):
            if not frontier:
                break
            pairs = " ".join(f"(<{x}> fro:{p})" for x in frontier for p in predicates)
            extra = self.sparql.select(PFX + f"""
SELECT ?s ?p ?plabel ?o ?type ?label WHERE {{
  VALUES (?s ?p) {{ {pairs} }}
  ?s ?p ?o .
  ?o a ?type .
  FILTER(?type IN ({", ".join(f"fro:{t.cls}" for t in ENTITY_TYPES)}))
  OPTIONAL {{ ?p rdfs:label ?plabel }}
  OPTIONAL {{ ?o rdfs:label ?label }}
}}""")
            frontier = []
            for r in extra:
                if r["o"] not in known:
                    known.add(r["o"])
                    frontier.append(r["o"])
                    t = BY_CLASS[r["type"]]
                    _, ident = parse_iri(r["o"]) or (None, r["o"])
                    nodes.append({"iri": r["o"], "type": t.key, "typeLabel": t.label,
                                  "label": r.get("label", ident), "identifier": ident,
                                  "hop": hop})
                edges.append({"source": r["s"], "target": r["o"], "predicate": _local(r["p"]),
                              "label": r.get("plabel", _local(r["p"])), "hop": hop})
        return {"center": center, "nodes": nodes, "edges": edges, "relations": relations}

    # ------------------------------------------------------------------ related panel
    def related(self, iri: str) -> dict:
        """The defect panel: where it sits in the fleet, what was done, what it cost the
        operation, and the aircraft's history in the same ATA chapter."""
        iri = check_iri(iri)
        t, ident = parse_iri(iri)
        if t.key != "defect":
            raise ValueError("related information is available for defects")
        rows = self.sparql.select(PFX + f"""
SELECT ?tailNumber ?model ?chapter ?group ?station ?status ?reported ?deferral ?workOrder
       ?serial ?part ?repairedBy ?finding ?hours WHERE {{
  <{iri}> fro:defectOn ?a ; fro:inAtaChapter ?c ; fro:reportedAt/rdfs:label ?station ;
          fro:hasStatus/rdfs:label ?status ; fro:reportedDate ?reported .
  ?a fro:tailNumber ?tailNumber ; fro:aircraftModel ?model .
  ?c rdfs:label ?chapter .
  OPTIONAL {{ <{iri}> fro:inSystemGroup/rdfs:label ?group }}
  OPTIONAL {{ <{iri}> fro:deferredBy/fro:deferralNumber ?deferral }}
  OPTIONAL {{ <{iri}> fro:correctedBy ?wo . ?wo fro:workOrderNumber ?workOrder .
             OPTIONAL {{ ?wo fro:includesRemoval ?r . ?r fro:removedUnit ?u ; fro:shopFinding ?finding ;
                         fro:hoursSinceInstall ?hours . ?u fro:serialNumber ?serial ;
                         fro:ofPart/rdfs:label ?part .
                         OPTIONAL {{ ?r fro:afterRepairBy/rdfs:label ?repairedBy }} }} }}
}} LIMIT 1""")
        if not rows:
            raise NotFound(iri)
        d = rows[0]
        impact = self.sparql.select(PFX + f"""
SELECT (COUNT(?f) AS ?flights) (SUM(?m) AS ?minutes) (SUM(IF(?c, 1, 0)) AS ?cancelled) WHERE {{
  ?f fro:delayedBy <{iri}> ; fro:delayMinutes ?m ; fro:cancelled ?c }}""")
        i = impact[0] if impact else {}
        history = self.sparql.select(PFX + f"""
SELECT ?defectNumber ?reportedDate ?station ?description ?status ?correctedBy WHERE {{
  <{iri}> fro:defectOn ?a ; fro:inAtaChapter ?c .
  ?d fro:defectOn ?a ; fro:inAtaChapter ?c ; fro:defectNumber ?defectNumber ;
     fro:reportedDate ?reportedDate ; fro:reportedAt/fro:stationCode ?station ;
     fro:description ?description ; fro:hasStatus/rdfs:label ?status .
  OPTIONAL {{ ?d fro:correctedBy/fro:workOrderNumber ?correctedBy }}
}} ORDER BY ?reportedDate""")
        return {
            "defect": d,
            "panel": [
                {"label": "Aircraft", "value": f'{d["tailNumber"]} ({d["model"]})'},
                {"label": "ATA chapter", "value": d.get("chapter")},
                {"label": "System group", "value": d.get("group")},
                {"label": "Reported at", "value": d.get("station")},
                {"label": "Status", "value": d.get("status")},
                {"label": "MEL deferral", "value": d.get("deferral")},
                {"label": "Corrected by", "value": d.get("workOrder")},
                {"label": "Unit removed", "value": d.get("serial")},
                {"label": "Unit last repaired by", "value": d.get("repairedBy")},
                {"label": "Shop finding", "value": d.get("finding")},
                {"label": "Flights impacted", "value": i.get("flights", 0)},
                {"label": "Delay minutes", "value": i.get("minutes") or 0},
                {"label": "Cancellations", "value": i.get("cancelled") or 0},
            ],
            "sameChapterHistory": history,
        }

    # ------------------------------------------------------------------ competency questions
    def list_questions(self) -> list[dict]:
        return [q.describe() for q in self.questions.values()]

    def run_question(self, qid: str, params: dict | None = None) -> dict:
        if qid not in self.questions:
            raise NotFound(f"unknown competency question {qid}")
        q = self.questions[qid]
        known = {p.name for p in q.params}
        sparql = q.bind({k: v for k, v in (params or {}).items() if k in known and v != ""})
        start = time.perf_counter()
        rows = self.sparql.select(sparql)
        ms = round((time.perf_counter() - start) * 1000)
        return_cols = select_vars(sparql)
        return {"id": q.id, "title": q.title, "question": q.question, "sparql": sparql,
                "columns": return_cols, "rows": rows, "elapsedMs": ms}
