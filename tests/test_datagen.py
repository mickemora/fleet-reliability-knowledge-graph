"""The synthetic fleet dataset: volumes, referential integrity and the planted signals."""

from collections import Counter, defaultdict

from datagen.generate import Generator, inject_defects


def test_volumes(generated):
    ds, _ = generated
    assert len(ds.aircraft) == 160 and len(ds.stations) == 20 and len(ds.parts) == 20
    assert 1000 <= len(ds.defects) <= 1600
    assert len(ds.removals) > 500 and len(ds.deferrals) > 200 and len(ds.flights) > 150


def test_deterministic(generated):
    again = Generator(seed=42).run()
    assert [d["defect_number"] for d in again.defects] == [d["defect_number"] for d in generated[0].defects]


def test_referential_integrity(generated):
    ds, _ = generated
    tails = {a["tail_number"] for a in ds.aircraft}
    stations = {s["station_code"] for s in ds.stations}
    defects = {d["defect_number"]: d for d in ds.defects}
    wos = {w["work_order_number"]: w for w in ds.work_orders}
    units = {u["serial_number"]: u for u in ds.components}
    assert len(defects) == len(ds.defects) and len(wos) == len(ds.work_orders)
    for d in ds.defects:
        assert d["tail_number"] in tails and d["station_code"] in stations
    for w in ds.work_orders:
        assert w["tail_number"] in tails and w["station_code"] in stations
        assert bool(w["corrects_defect"]) != bool(w["accomplishes_directive"])
        if w["corrects_defect"]:
            assert defects[w["corrects_defect"]]["tail_number"] == w["tail_number"]
        assert w["open_date"] <= w["close_date"]
    for m in ds.deferrals:
        assert defects[m["defect_number"]]["tail_number"] == m["tail_number"]
        assert m["deferred_date"] < m["expiry_date"]
    for r in ds.removals:
        assert r["serial_number"] in units and r["work_order_number"] in wos
        assert float(r["hours_since_install"]) >= 0
    for f in ds.flights:
        assert defects[f["delay_defect"]]["tail_number"] == f["tail_number"]
    installed = Counter(u["installed_on"] for u in ds.components if u["installed_on"])
    assert set(installed) <= tails


def test_rogue_bleed_valves(generated):
    ds, _ = generated
    units = {u["serial_number"]: u for u in ds.components}
    hours = defaultdict(list)
    for r in ds.removals:
        if units[r["serial_number"]]["part_number"] == "BV3611-04":
            hours[r["after_repair_by"]].append(float(r["hours_since_install"]))
    mean = {v: sum(h) / len(h) for v, h in hours.items()}
    assert mean["V05"] < 1000 and all(mean[v] > 3000 for v in mean if v != "V05")
    assert len(ds.signals["rogueUnits"]["serialsWith3PlusRemovals"]) >= 5


def test_showcase(generated):
    ds, _ = generated
    s = ds.signals["showcase"]
    on_tail = [d for d in ds.defects if d["defect_number"] in s["defects"]]
    assert {d["tail_number"] for d in on_tail} == {"N812BB"} and len(on_tail) == 3
    rogue = [r for r in ds.removals if r["serial_number"] == "BV10457"]
    assert len(rogue) == 3 and {r["shop_finding"] for r in rogue} == {"No fault found"}
    assert any(f["delay_defect"] == "DF-100245" for f in ds.flights)


def test_defect_injection_is_logged():
    ds = inject_defects(Generator(seed=42).run())
    assert len({d["defect"] for d in ds.injected}) == 8
