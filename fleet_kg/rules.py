"""Materialization rules: the inferences the ontology implies, written as SPARQL UPDATE.

Each rule only inserts triples that are not already in the graph, so the inferred graph holds
exactly what reasoning added and running the rules again changes nothing.

Neptune stores RDF and answers SPARQL, but it does not run an OWL/RDFS reasoner. So after each
load the pipeline runs these updates once and writes the results into their own named graph
(GRAPH_INFERRED). Dropping that graph removes every inferred triple; rerunning the rules
rebuilds it. The same updates run against rdflib locally, so tests prove what they produce.

The rules are a small, explicit subset of RDFS / OWL 2 RL, chosen because the explorer and the
competency questions depend on them:

  inverse-of         owl:inverseOf pairs in both directions (Defect defectOn Aircraft -> Aircraft hasDefect Defect)
  sub-property       rdfs:subPropertyOf (every business key is also a fro:identifier)
  sub-class          rdfs:subClassOf+  (an Aircraft is also an Asset and a BusinessEntity)
  broader-transitive skos:broader+     (ATA 36 Pneumatic is within Airframe Systems)
  in-system-group    derived: a defect belongs to the top-level ATA system group of its chapter
"""

from __future__ import annotations

from fleet_kg.namespaces import GRAPH_INFERRED, sparql_prefixes

P = sparql_prefixes(("fro", "skos", "rdf", "rdfs")) + "PREFIX owl: <http://www.w3.org/2002/07/owl#>\n"

RULES: list[tuple[str, str]] = [
    ("inverse-of (forward)", P + f"""
INSERT {{ GRAPH <{GRAPH_INFERRED}> {{ ?o ?inverse ?s }} }}
WHERE {{
  ?p owl:inverseOf ?inverse .
  ?s ?p ?o .
  FILTER(isIRI(?o))
  FILTER NOT EXISTS {{ ?o ?inverse ?s }}
}}"""),
    ("inverse-of (backward)", P + f"""
INSERT {{ GRAPH <{GRAPH_INFERRED}> {{ ?o ?p ?s }} }}
WHERE {{
  ?p owl:inverseOf ?inverse .
  ?s ?inverse ?o .
  FILTER(isIRI(?o))
  FILTER NOT EXISTS {{ ?o ?p ?s }}
}}"""),
    ("sub-property", P + f"""
INSERT {{ GRAPH <{GRAPH_INFERRED}> {{ ?s ?super ?o }} }}
WHERE {{
  ?p rdfs:subPropertyOf+ ?super .
  FILTER(STRSTARTS(STR(?p), STR(fro:)))
  ?s ?p ?o .
  FILTER NOT EXISTS {{ ?s ?super ?o }}
}}"""),
    ("sub-class", P + f"""
INSERT {{ GRAPH <{GRAPH_INFERRED}> {{ ?s a ?super }} }}
WHERE {{
  ?cls rdfs:subClassOf+ ?super .
  FILTER(STRSTARTS(STR(?cls), STR(fro:)))
  ?s a ?cls .
  FILTER NOT EXISTS {{ ?s a ?super }}
}}"""),
    ("broader-transitive", P + f"""
INSERT {{ GRAPH <{GRAPH_INFERRED}> {{ ?c skos:broaderTransitive ?b }} }}
WHERE {{
  ?c skos:broader+ ?b .
  FILTER NOT EXISTS {{ ?c skos:broaderTransitive ?b }}
}}"""),
    ("in-system-group", P + f"""
INSERT {{ GRAPH <{GRAPH_INFERRED}> {{ ?defect fro:inSystemGroup ?group }} }}
WHERE {{
  ?defect a fro:Defect ; fro:inAtaChapter ?chapter .
  ?chapter skos:broader* ?group .
  FILTER NOT EXISTS {{ ?group skos:broader ?any }}
  FILTER NOT EXISTS {{ ?defect fro:inSystemGroup ?group }}
}}"""),
]

CLEAR = f"DROP SILENT GRAPH <{GRAPH_INFERRED}>"
COUNT = f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{GRAPH_INFERRED}> {{ ?s ?p ?o }} }}"
