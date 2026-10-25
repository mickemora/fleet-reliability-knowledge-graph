"""Ontology, ATA taxonomy and SHACL shapes: they parse, agree and catch bad data."""

from pathlib import Path

import pytest

pytest.importorskip("rdflib")
from rdflib import OWL, RDF, RDFS, Graph, Namespace  # noqa: E402

from fleet_kg import mapping, validation  # noqa: E402
from fleet_kg.namespaces import ENTITY_TYPES, FRO  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")
F = Namespace(FRO)


@pytest.fixture(scope="module")
def ontology():
    return Graph().parse(ROOT / "ontology" / "fleet.ttl")


@pytest.fixture(scope="module")
def shapes():
    return Graph().parse(ROOT / "shapes" / "fleet-shapes.ttl")


@pytest.fixture(scope="module")
def reference():
    return Graph().parse(ROOT / "reference" / "ata-chapters.ttl")


def test_entity_registry_matches_ontology(ontology):
    for t in ENTITY_TYPES:
        assert (F[t.cls], RDF.type, OWL.Class) in ontology
        assert (F[t.id_prop], RDFS.subPropertyOf, F.identifier) in ontology


def test_every_property_is_documented(ontology):
    for p in set(ontology.subjects(RDF.type, OWL.ObjectProperty)) | \
             set(ontology.subjects(RDF.type, OWL.DatatypeProperty)):
        assert ontology.value(p, RDFS.label), p
        if p != F.identifier:
            assert ontology.value(p, RDFS.domain) and ontology.value(p, RDFS.range), p


def test_inverse_pairs_agree(ontology):
    for p, inv in ontology.subject_objects(OWL.inverseOf):
        assert ontology.value(p, RDFS.domain) == ontology.value(inv, RDFS.range), p
        assert ontology.value(p, RDFS.range) == ontology.value(inv, RDFS.domain), p


def test_ata_taxonomy(reference):
    chapters = set(reference.subjects(RDF.type, F.AtaChapter))
    groups = {c for c in chapters if (c, SKOS.broader, None) not in reference}
    assert len(groups) == 3
    assert all(reference.value(c, SKOS.broader) in groups for c in chapters - groups)


def test_data_uses_only_declared_vocabulary(generated, ontology):
    data, _ = mapping.to_graph(mapping.read_dir(generated[1] / "raw"))
    assert validation.vocabulary_check(data, ontology) == []


def _validate(raw, shapes, ontology, reference):
    data, _ = mapping.to_graph(mapping.read_dir(raw))
    for t in reference:
        data.add(t)
    return validation.validate(data, shapes, ontology)


def test_clean_data_conforms(generated, shapes, ontology, reference):
    summary, report = _validate(generated[1] / "raw", shapes, ontology, reference)
    assert summary["conforms"], summary["results"][:3]
    assert "ValidationReport" in report


def test_every_injected_defect_is_caught(tmp_path, shapes, ontology, reference):
    from datagen.generate import Generator, inject_defects
    ds = inject_defects(Generator(seed=42).run())
    ds.write(tmp_path)
    summary, _ = _validate(tmp_path / "raw", shapes, ontology, reference)
    assert not summary["conforms"]
    flagged = {e.rsplit("/", 1)[-1] for r in summary["results"] if r["severity"] == "Violation"
               for e in r["examples"]}
    for d in ds.injected:
        assert d["record"] in flagged, d
