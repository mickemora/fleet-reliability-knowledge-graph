"""Explorer API logic and HTTP wiring on the in-memory graph."""

import json

import pytest

pytest.importorskip("rdflib")

from functions.explorer_api.handler import handle_http  # noqa: E402
from fleet_kg.explorer import NotFound  # noqa: E402
from fleet_kg.namespaces import iri  # noqa: E402

DEFECT = iri("defect", "DF-100245")


def test_stats(explorer, generated):
    s = explorer.stats()
    assert s["counts"]["defect"] == len(generated[0].defects)
    assert s["delayMinutes"] > 0 and s["triples"] > 50_000


@pytest.mark.parametrize("text,type_,ident", [
    ("N812BB", "aircraft", "N812BB"), ("DF-100245", "defect", "DF-100245"),
    ("BV10457", "component", "BV10457"), ("gulf coast", "vendor", "V05"), ("BWI", "station", "BWI")])
def test_search(explorer, text, type_, ident):
    first = explorer.search(text)["results"][0]
    assert (first["type"], first["identifier"]) == (type_, ident)


def test_lists(explorer):
    for key in explorer.LISTS:
        page = explorer.entities(key, limit=5)
        assert page["rows"] and page["total"] > 0, key


def test_defect_neighborhood_reaches_the_shop(explorer):
    n = explorer.neighborhood(DEFECT)
    by_type = {x["type"]: x for x in n["nodes"]}
    assert {"aircraft", "station", "workOrder", "deferral", "flight", "removal", "component", "vendor"} <= set(by_type)
    assert by_type["component"]["identifier"] == "BV10457" and by_type["component"]["hop"] == 3


def test_related_panel(explorer):
    r = explorer.related(DEFECT)
    panel = {p["label"]: p["value"] for p in r["panel"]}
    assert panel["Unit removed"] == "BV10457" and panel["Delay minutes"] == 95
    assert len(r["sameChapterHistory"]) == 3


def test_bad_iris(explorer):
    for bad in ("http://evil/", DEFECT + "> } DROP ALL {", ""):
        with pytest.raises((ValueError, NotFound)):
            explorer.entity(bad)


def _get(explorer, path, **qs):
    resp = handle_http({"rawPath": path, "queryStringParameters": qs,
                        "requestContext": {"http": {"method": "GET"}}}, explorer)
    return resp["statusCode"], json.loads(resp["body"])


def test_http_routes(explorer):
    assert _get(explorer, "/api/stats")[0] == 200
    status, body = _get(explorer, "/api/competency/cq05")
    assert status == 200 and body["rows"][0]["vendorCode"] == "V05"
    assert _get(explorer, "/api/competency/cq01", tailNumber="nope")[0] == 400
    assert _get(explorer, "/api/competency/cq99")[0] == 404
    assert _get(explorer, "/api/entities", type="spaceship")[0] == 400
