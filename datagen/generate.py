"""Synthetic fleet maintenance dataset: the CSV extracts a maintenance & engineering system exports.

    python -m datagen.generate                     # data/generated/raw/*.csv + manifest.json
    python -m datagen.generate --seed 7 --out /tmp/fleet
    python -m datagen.generate --inject-defects    # adds known data-quality defects (SHACL demo)

One year of operations (2025-10-01 to 2026-09-30) for 160 Boeing 737s: defects, work orders,
MEL deferrals, serialized component removals, shop visits, airworthiness directive compliance
and the flights that maintenance delayed or cancelled.

The simulation tracks every serialized rotable component: when an installed unit fails, a defect
is written up, it may be deferred under the MEL, a work order removes it, it goes to a repair
shop, and a spare is installed. Three signals are planted for the competency questions:

1. Rogue bleed valves: Bleed Air Pressure Regulating Valves (BV3611-04) overhauled by
   Gulf Coast Aero Components (V05) since March 2025 fail after a few hundred flight hours,
   often with "no fault found" at the shop, and return to service still faulty.
2. Station fix effectiveness: air conditioning (ATA 21) fixes at BWI often don't hold; the same
   aircraft writes up the same chapter again within three days.
3. A showcase aircraft, N812BB, with a chronic bleed problem: three write-ups in nine days,
   a deferral, a delay and a cancellation, and the rogue unit BV10457.
"""

from __future__ import annotations

import argparse
import csv
import heapq
import json
import math
import random
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from datagen import catalog as C

START, AS_OF = date(2025, 10, 1), date(2026, 9, 30)
DAYS = (AS_OF - START).days + 1
DEFAULT_OUT = Path(__file__).resolve().parent.parent / "data" / "generated"

MTBUR_SCALE = 1.0              # stretches catalog MTBURs to keep one year near ~1,300 defects
SUSPECT_MTBUR = 480.0          # flight hours, for units carrying the bad overhaul
SUSPECT_SHOP_FROM, SUSPECT_SHOP_TO = date(2025, 3, 1), date(2025, 6, 30)
SUSPECT_SHARE = 0.10           # of bleed valve positions holding a suspect unit at start
SUSPECT_RETURNS_TO_V05 = 0.45  # chance a removed suspect unit goes back to the same shop
BWI_ATA21_REPEAT, OTHER_REPEAT = 0.55, 0.06
SIMPLE_DEFECTS_PER_AIRCRAFT = 2.6

SHOWCASE_TAIL, SHOWCASE_DEFECT, ROGUE_SERIAL = "N812BB", "DF-100245", "BV10457"


def d2s(d: date) -> str:
    return d.isoformat()


@dataclass
class Dataset:
    seed: int
    stations: list[dict] = field(default_factory=list)
    vendors: list[dict] = field(default_factory=list)
    parts: list[dict] = field(default_factory=list)
    aircraft: list[dict] = field(default_factory=list)
    components: list[dict] = field(default_factory=list)
    defects: list[dict] = field(default_factory=list)
    work_orders: list[dict] = field(default_factory=list)
    removals: list[dict] = field(default_factory=list)
    deferrals: list[dict] = field(default_factory=list)
    directives: list[dict] = field(default_factory=list)
    flights: list[dict] = field(default_factory=list)
    signals: dict = field(default_factory=dict)
    injected: list[dict] = field(default_factory=list)

    TABLES = ("stations", "vendors", "parts", "aircraft", "components", "defects", "work_orders",
              "removals", "deferrals", "directives", "flights")

    def write(self, out: Path) -> Path:
        raw = out / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        for name in self.TABLES:
            rows = getattr(self, name)
            with open(raw / f"{name}.csv", "w", newline="", encoding="utf-8") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)
        (out / "manifest.json").write_text(json.dumps(self.manifest(), indent=2) + "\n")
        return out

    def manifest(self) -> dict:
        return {"seed": self.seed, "start": d2s(START), "asOf": d2s(AS_OF),
                "counts": {n: len(getattr(self, n)) for n in self.TABLES},
                "signals": self.signals, "injectedDefects": self.injected}


class Generator:
    def __init__(self, seed: int = 42):
        self.seed = seed
        self.r = random.Random(seed)
        self.ds = Dataset(seed=seed)
        reserved = {SHOWCASE_DEFECT[3:]}
        self._ids = {
            "DF": self._pool(100000, 999999, reserved), "WO": self._pool(1000000, 9999999, set()),
            "RM": self._pool(100000, 999999, set()), "MEL": self._pool(100000, 999999, set()),
            "FL": self._pool(100, 4999, set())}
        self._serial_seq: dict[str, int] = {}
        self.part = {p[0]: p for p in C.PARTS}

    def _pool(self, lo, hi, exclude):
        seen = set(exclude)
        while True:
            n = str(self.r.randint(lo, hi))
            if n not in seen:
                seen.add(n)
                yield n

    def next_id(self, kind: str) -> str:
        return f"{kind}-{next(self._ids[kind])}"

    def new_serial(self, pn: str) -> str:
        prefix = pn[:2]
        n = self._serial_seq.get(prefix, 10000) + self.r.randint(1, 7)
        if prefix == "BV" and n >= 10457 and self._serial_seq.get(prefix, 0) < 10457:
            n = 10458                          # keep the rogue showcase serial for the script
        self._serial_seq[prefix] = n
        return f"{prefix}{n}"

    def day(self, i: float) -> date:
        return START + timedelta(days=int(math.floor(i)))

    def station(self, ata: str | None = None) -> str:
        weights = dict(C.STATION_WEIGHTS)
        if ata == "21":
            weights["BWI"] *= 6            # pack complaints cluster at BWI (signal 2)
        return self.r.choices(list(weights), list(weights.values()))[0]

    # ------------------------------------------------------------------ build
    def run(self) -> Dataset:
        ds, r = self.ds, self.r
        ds.stations = [{"station_code": c, "name": n, "city": city, "state": st, "station_type": t}
                       for c, (n, city, st, t) in C.STATIONS.items()]
        ds.vendors = [{"vendor_code": c, "name": n, "vendor_type": t, "city": city, "country": cc}
                      for c, n, t, city, cc in C.VENDORS]
        ds.parts = [{"part_number": p[0], "part_name": p[1], "ata_chapter": p[2],
                     "manufacturer_code": p[3], "unit_cost": f"{p[4]:.2f}",
                     "mtbur_target_hours": p[6]} for p in C.PARTS]
        ds.directives = [{"ad_number": a[0], "title": a[1], "ata_chapter": a[2],
                          "effective_date": a[3], "compliance_date": a[4],
                          "applies_to_models": "|".join(a[5])} for a in C.DIRECTIVES]
        self._fleet()
        self._initial_components()
        self._simulate()
        self._simple_defects()
        self._showcase()
        self._open_deferrals_near_expiry()
        self._directive_compliance()
        self._finish()
        return ds

    def _fleet(self):
        r = self.r
        for model, (count, digit, engine, (y0, y1), hpd, cpd) in C.FLEET.items():
            tails = sorted(r.sample(range(1, 100), count))
            for t in tails:
                tail = f"N{digit}{t:02d}BB"
                delivered = date(r.randint(y0, y1), r.randint(1, 12), r.randint(1, 28))
                days = (AS_OF - delivered).days
                self.ds.aircraft.append({
                    "tail_number": tail, "model": model, "msn": str(r.randint(30000, 69999)),
                    "engine_type": engine, "delivery_date": d2s(delivered),
                    "flight_hours": round(days * hpd * r.uniform(0.9, 1.0), 1),
                    "flight_cycles": int(days * cpd * r.uniform(0.9, 1.0)),
                    "home_base": r.choice(C.BASES),
                    "cycles_in_period": int(DAYS * cpd * r.uniform(0.9, 1.05)),
                    "_hpd": hpd * r.uniform(0.92, 1.08)})
        if SHOWCASE_TAIL not in {a["tail_number"] for a in self.ds.aircraft}:
            self.ds.aircraft[60]["tail_number"] = SHOWCASE_TAIL   # first 737-800
        self.ac = {a["tail_number"]: a for a in self.ds.aircraft}

    def _unit(self, pn: str, vendor: str, shop: date, serial: str | None = None,
              suspect: bool = False) -> dict:
        u = {"serial_number": serial or self.new_serial(pn), "part_number": pn,
             "last_repaired_by": vendor, "last_shop_visit_date": d2s(shop), "installed_on": "",
             "_suspect": suspect, "_available": -9999}
        self.units[u["serial_number"]] = u
        return u

    def _initial_components(self):
        r = self.r
        self.units: dict[str, dict] = {}
        self.slots: dict[tuple, dict] = {}        # (tail, pn, position) -> {"unit", "install_day"}
        self.queue: list = []
        for a in self.ds.aircraft:
            for p in C.PARTS:
                pn, positions = p[0], p[5]
                for pos in range(positions):
                    suspect = pn == C.SUSPECT_PART and r.random() < SUSPECT_SHARE
                    if (a["tail_number"], pn) == (SHOWCASE_TAIL, C.SUSPECT_PART):
                        suspect = False          # the showcase script controls these two
                    if suspect:
                        shop = SUSPECT_SHOP_FROM + timedelta(days=r.randint(0, 110))
                        u = self._unit(pn, C.SUSPECT_VENDOR, shop, suspect=True)
                        install_day = -r.randint(5, 40)
                    else:
                        vendor = r.choice([p[3]] + C.REPAIR_STATIONS)
                        if vendor == C.SUSPECT_VENDOR:
                            vendor = "V06"
                        shop = START - timedelta(days=r.randint(60, 1500))
                        u = self._unit(pn, vendor, shop)
                        install_day = -r.randint(30, 1200)
                    self._install(a["tail_number"], pn, pos, u, install_day, schedule_from=0)
            # spares pool
        for p in C.PARTS:
            for _ in range(max(4, p[5] * 5)):
                vendor = r.choice([p[3]] + ["V06", "V07"])
                self._unit(p[0], vendor, START - timedelta(days=r.randint(10, 300)))

    def _install(self, tail, pn, pos, unit, install_day, schedule_from=None):
        unit["installed_on"] = tail
        self.slots[(tail, pn, pos)] = {"unit": unit, "install_day": install_day}
        if (tail, pn) == (SHOWCASE_TAIL, C.SUSPECT_PART):
            return
        hpd = self.ac[tail]["_hpd"]
        mean = SUSPECT_MTBUR if unit["_suspect"] else self.part[pn][6] * MTBUR_SCALE
        start = install_day if schedule_from is None else max(install_day, schedule_from)
        fail_day = start + self.r.expovariate(1 / mean) / hpd
        if fail_day < DAYS:
            heapq.heappush(self.queue, (fail_day, tail, pn, pos, unit["serial_number"]))

    def _simulate(self):
        while self.queue:
            t, tail, pn, pos, serial = heapq.heappop(self.queue)
            slot = self.slots[(tail, pn, pos)]
            if slot["unit"]["serial_number"] != serial:
                continue
            self._unscheduled_removal(t, tail, pn, pos)

    # ------------------------------------------------------------------ events
    def _defect(self, t: float, tail: str, ata: str, text: str, station: str,
                defect_number: str | None = None, source: str | None = None) -> dict:
        d = {"defect_number": defect_number or self.next_id("DF"), "tail_number": tail,
             "reported_date": d2s(self.day(t)), "station_code": station, "ata_chapter": ata,
             "source": source or self.r.choices(["Pilot report", "Maintenance finding"], [7, 3])[0],
             "description": text, "status": "CLOSED", "_t": t}
        self.ds.defects.append(d)
        return d

    def _work_order(self, t: float, tail: str, station: str, action: str, defect: dict | None,
                    hours: float, directive: str = "") -> dict:
        open_d = self.day(t)
        w = {"work_order_number": self.next_id("WO"), "tail_number": tail, "station_code": station,
             "open_date": d2s(open_d), "close_date": d2s(open_d + timedelta(days=self.r.choice([0, 0, 1]))),
             "corrects_defect": defect["defect_number"] if defect else "",
             "accomplishes_directive": directive, "action": action,
             "labor_hours": f"{hours:.1f}"}
        if w["close_date"] > d2s(AS_OF):
            w["close_date"] = d2s(AS_OF)
        self.ds.work_orders.append(w)
        return w

    def _deferral(self, t: float, defect: dict, mel_item: str, category: str,
                  cleared: float | None) -> dict:
        start = self.day(t)
        m = {"deferral_number": self.next_id("MEL"), "defect_number": defect["defect_number"],
             "tail_number": defect["tail_number"], "mel_item": mel_item, "category": category,
             "deferred_date": d2s(start),
             "expiry_date": d2s(start + timedelta(days=C.MEL_CATEGORY_DAYS[category])),
             "cleared_date": d2s(self.day(cleared)) if cleared is not None else ""}
        if cleared is None:
            defect["status"] = "DEFERRED"
        self.ds.deferrals.append(m)
        return m

    def _flight_impact(self, t: float, tail: str, station: str, defect: dict,
                       p_delay: float, cancel: bool | None = None, minutes: int | None = None):
        r = self.r
        if cancel is None and r.random() > p_delay:
            return None
        cancelled = cancel if cancel is not None else r.random() < 0.08
        num = f"{C.FLIGHT_PREFIX}{next(self._ids['FL'])}"
        day = self.day(t)
        f = {"flight_leg_id": f"{num}-{day.strftime('%Y%m%d')}", "flight_number": num,
             "flight_date": d2s(day), "tail_number": tail, "departure_station": station,
             "delay_minutes": 0 if cancelled else (minutes or int(r.triangular(15, 240, 55))),
             "cancelled": "true" if cancelled else "false",
             "delay_defect": defect["defect_number"]}
        self.ds.flights.append(f)
        return f

    def _spare(self, pn: str, t: float) -> dict:
        ready = [u for u in self.units.values() if u["part_number"] == pn and not u["installed_on"]
                 and u["_available"] <= t and u["serial_number"] != ROGUE_SERIAL]
        if ready:
            return self.r.choice(ready)
        return self._unit(pn, self.part[pn][3], self.day(t) - timedelta(days=5))

    def _send_to_shop(self, unit: dict, t: float, finding: str):
        r = self.r
        unit["installed_on"] = ""
        if unit["part_number"] == C.SUSPECT_PART:
            vendor = (C.SUSPECT_VENDOR if unit["_suspect"] and r.random() < SUSPECT_RETURNS_TO_V05
                      else r.choice(["V05", "V06", "V07", "V07"]))
        else:
            vendor = r.choice(C.REPAIR_STATIONS + [self.part[unit["part_number"]][3]])
        if unit["_suspect"] and vendor != C.SUSPECT_VENDOR:
            unit["_suspect"] = False        # a competent overhaul cures it
        elif vendor == C.SUSPECT_VENDOR and unit["part_number"] == C.SUSPECT_PART:
            unit["_suspect"] = True         # the bad overhaul process is still in place
        shop_day = t + r.randint(12, 30)
        if shop_day < DAYS:
            unit["last_repaired_by"] = vendor
            unit["last_shop_visit_date"] = d2s(self.day(shop_day))
            unit["_available"] = shop_day + r.randint(3, 15)
        else:
            unit["_available"] = 10**9

    def _unscheduled_removal(self, t, tail, pn, pos, *, station=None, defect_number=None,
                             force_finding=None, wo_station=None, defer=None, impact=None):
        r = self.r
        p = self.part[pn]
        slot = self.slots[(tail, pn, pos)]
        unit = slot["unit"]
        station = station or self.station(p[2])
        defect = self._defect(t, tail, p[2], p[8], station, defect_number)
        p_delay = 0.4 if p[2] == "36" else 0.2
        if impact:
            self._flight_impact(t, tail, station, defect, 1, **impact)
        else:
            self._flight_impact(t, tail, station, defect, p_delay)
        fix_t = t + r.choice([0, 0, 0.5])
        if defer or (defer is None and p[7] and r.random() < 0.35):
            cat = r.choice(["B", "C", "C"])
            fix_t = t + (defer or r.randint(1, C.MEL_CATEGORY_DAYS[cat] - 1))
            wo_station = wo_station or self.ac[tail]["home_base"]
            if fix_t >= DAYS:
                self._deferral(t, defect, p[7], cat, None)
                return
            self._deferral(t, defect, p[7], cat, fix_t)
        wo_station = wo_station or station
        wo = self._work_order(fix_t, tail, wo_station, p[9], defect, p[6] / 5000 + r.uniform(1, 3))
        hours = (fix_t - slot["install_day"]) * self.ac[tail]["_hpd"]
        finding = force_finding or (
            ("No fault found" if r.random() < 0.55 else "Confirmed failure") if unit["_suspect"]
            else ("Confirmed failure" if r.random() < 0.7 else "No fault found"))
        self.ds.removals.append({
            "removal_number": self.next_id("RM"), "serial_number": unit["serial_number"],
            "tail_number": tail, "work_order_number": wo["work_order_number"],
            "removal_date": wo["open_date"], "unscheduled": "true",
            "hours_since_install": f"{max(hours, 1):.1f}",
            "after_repair_by": unit["last_repaired_by"], "shop_finding": finding,
            "reason": p[8]})
        self._send_to_shop(unit, fix_t, finding)
        if (tail, pn) != (SHOWCASE_TAIL, C.SUSPECT_PART):
            self._install(tail, pn, pos, self._spare(pn, fix_t), fix_t)
        self._maybe_repeat(fix_t, tail, p[2], p[8], "Troubleshot per fault isolation manual, ops check good",
                           p[7], wo_station)

    def _maybe_repeat(self, fix_t, tail, ata, text, action, mel, wo_station):
        """Signal 2: air conditioning fixes at BWI often don't hold."""
        repeat_p = BWI_ATA21_REPEAT if (ata == "21" and wo_station == "BWI") else OTHER_REPEAT
        if self.r.random() < repeat_p:
            again = fix_t + self.r.uniform(0.5, 2.9)
            if again < DAYS:
                self._simple(again, tail, ata, text.split(" (repeat)")[0] + " (repeat)", action, mel,
                             station=self.station(), repeat_ok=False)

    def _simple_defects(self):
        r = self.r
        for a in self.ds.aircraft:
            lam, k, p = math.exp(-SIMPLE_DEFECTS_PER_AIRCRAFT), 0, 1.0
            while True:
                p *= r.random()
                if p <= lam:
                    break
                k += 1
            for _ in range(k):
                ata, text, action, mel = r.choice(C.SIMPLE_DEFECTS)
                self._simple(r.uniform(0, DAYS - 1), a["tail_number"], ata, text, action, mel)

    def _simple(self, t, tail, ata, text, action, mel, station=None, repeat_ok=True):
        r = self.r
        station = station or self.station(ata)
        defect = self._defect(t, tail, ata, text, station)
        self._flight_impact(t, tail, station, defect, 0.08)
        fix_t, wo_station = t, station
        if mel and r.random() < 0.3:
            fix_t = t + r.randint(1, 4)
            if fix_t >= DAYS:
                self._deferral(t, defect, mel, "C", None)
                return
            self._deferral(t, defect, mel, "C", fix_t)
            wo_station = self.ac[tail]["home_base"]
        self._work_order(fix_t, tail, wo_station, action, defect, r.uniform(0.3, 2.5))
        if repeat_ok:
            self._maybe_repeat(fix_t, tail, ata, text, action, mel, wo_station)

    # ------------------------------------------------------------------ showcase (signal 3)
    def _showcase(self):
        r = self.r
        tail, pn = SHOWCASE_TAIL, C.SUSPECT_PART
        rogue = self._unit(pn, C.SUSPECT_VENDOR, date(2025, 4, 22), serial=ROGUE_SERIAL, suspect=True)
        # Rogue history: removed from two other aircraft earlier in the year, "no fault found".
        others = [a["tail_number"] for a in self.ds.aircraft
                  if a["model"] != "737 MAX 8" and a["tail_number"] != tail]
        history = [(38, others[3], date(2025, 9, 18)), (117, others[17], date(2025, 12, 20))]
        for t, other, installed in history:
            rogue["installed_on"] = other
            self._showcase_removal(t, other, rogue, installed, finding="No fault found")
        # On N812BB: installed 2026-03-02, then the chronic sequence in April 2026.
        rogue["installed_on"] = tail
        rogue["last_shop_visit_date"] = "2026-02-10"
        self.slots[(tail, pn, 0)]["unit"]["installed_on"] = ""
        self.slots[(tail, pn, 0)] = {"unit": rogue, "install_day": (date(2026, 3, 2) - START).days}
        d0 = (date(2026, 4, 15) - START).days
        first = self._defect(d0, tail, "36", "BLEED TRIP OFF light during climb", "DAL",
                             source="Pilot report")
        self._work_order(d0, tail, "DAL", "Reset bleed trip, ops check good, could not duplicate",
                         first, 1.2)
        second = self._defect(d0 + 4, tail, "36", "BLEED TRIP OFF light during climb", "MDW",
                              defect_number=SHOWCASE_DEFECT, source="Pilot report")
        self._flight_impact(d0 + 4, tail, "MDW", second, 1, cancel=False, minutes=95)
        self._deferral(d0 + 4, second, "36-11-01", "C", d0 + 6)
        wo = self._work_order(d0 + 6, tail, "HOU", self.part[pn][9], second, 3.4)
        self._showcase_removal(d0 + 6, tail, rogue, date(2026, 3, 2), finding="No fault found", wo=wo)
        third = self._defect(d0 + 8, tail, "36", "BLEED TRIP OFF light during climb", "PHX",
                             source="Pilot report")
        self._flight_impact(d0 + 8, tail, "PHX", third, 1, cancel=True)
        other = self.slots[(tail, pn, 1)]["unit"]
        wo3 = self._work_order(d0 + 8, tail, "PHX", self.part[pn][9], third, 3.1)
        self._showcase_removal(d0 + 8, tail, other, START - timedelta(days=400),
                               finding="Confirmed failure", wo=wo3)
        for pos, t in ((0, d0 + 6), (1, d0 + 8)):
            spare = self._spare(pn, t)
            spare["last_repaired_by"] = "V06"
            spare["_suspect"] = False
            self.slots[(tail, pn, pos)] = {"unit": spare, "install_day": t}
            spare["installed_on"] = tail
        self.showcase_defects = [first["defect_number"], SHOWCASE_DEFECT, third["defect_number"]]

    def _showcase_removal(self, t, tail, unit, installed: date, finding: str, wo=None):
        if wo is None:
            d = self._defect(t, tail, "36", "BLEED TRIP OFF light during climb", self.station("36"),
                             source="Pilot report")
            wo = self._work_order(t, tail, d["station_code"], self.part[C.SUSPECT_PART][9], d, 3.0)
        hours = (self.day(t) - installed).days * self.ac[tail]["_hpd"]
        self.ds.removals.append({
            "removal_number": self.next_id("RM"), "serial_number": unit["serial_number"],
            "tail_number": tail, "work_order_number": wo["work_order_number"],
            "removal_date": wo["open_date"], "unscheduled": "true",
            "hours_since_install": f"{hours:.1f}", "after_repair_by": unit["last_repaired_by"],
            "shop_finding": finding, "reason": "BLEED TRIP OFF light during climb"})
        unit["installed_on"] = ""
        if unit["serial_number"] == ROGUE_SERIAL:
            unit["last_repaired_by"] = C.SUSPECT_VENDOR      # back to the same shop, every time
            unit["last_shop_visit_date"] = d2s(self.day(t + 20))
        else:
            unit["last_repaired_by"] = "V06"
            unit["last_shop_visit_date"] = d2s(self.day(t + 25))

    def _open_deferrals_near_expiry(self):
        """A few category B/C deferrals that expire within 48 hours of the as-of date."""
        r = self.r
        tails = r.sample([a["tail_number"] for a in self.ds.aircraft if a["tail_number"] != SHOWCASE_TAIL], 5)
        for tail, (pn, cat, age) in zip(tails, [("PC2150-12", "C", 9), ("LT3341-10", "C", 8),
                                               ("FP2841-07", "B", 2), ("GC2421-06", "B", 1),
                                               ("WH3041-05", "C", 4)]):
            p = self.part[pn]
            t = DAYS - 1 - age
            d = self._defect(t, tail, p[2], p[8], self.station(p[2]))
            self._deferral(t, d, p[7], cat, None)

    def _directive_compliance(self):
        r = self.r
        for number, title, ata, eff, due, models, share in C.DIRECTIVES:
            start = (date.fromisoformat(eff) - START).days
            end = min((date.fromisoformat(due) - START).days, DAYS - 1)
            for a in self.ds.aircraft:
                if a["model"] in models and r.random() < share:
                    t = r.uniform(max(start, 0), end)
                    self._work_order(t, a["tail_number"], a["home_base"],
                                     f"Accomplished {number}: {title.lower()}", None,
                                     r.uniform(1.5, 4.0), directive=number)

    def _finish(self):
        ds = self.ds
        corrected = {w["corrects_defect"] for w in ds.work_orders if w["corrects_defect"]}
        for d in ds.defects:
            if d["defect_number"] not in corrected and d["status"] != "DEFERRED":
                d["status"] = "OPEN"
            d.pop("_t", None)
        ds.defects.sort(key=lambda d: (d["reported_date"], d["defect_number"]))
        ds.work_orders.sort(key=lambda w: (w["open_date"], w["work_order_number"]))
        ds.removals.sort(key=lambda m: (m["removal_date"], m["removal_number"]))
        ds.deferrals.sort(key=lambda m: (m["deferred_date"], m["deferral_number"]))
        ds.flights.sort(key=lambda f: (f["flight_date"], f["flight_number"]))
        ds.components = [{k: v for k, v in u.items() if not k.startswith("_")}
                         for u in sorted(self.units.values(), key=lambda u: u["serial_number"])]
        for a in ds.aircraft:
            a.pop("_hpd", None)
        rogue_counts = {}
        for m in ds.removals:
            rogue_counts[m["serial_number"]] = rogue_counts.get(m["serial_number"], 0) + 1
        ds.signals = {
            "rogueUnits": {"partNumber": C.SUSPECT_PART, "vendorCode": C.SUSPECT_VENDOR,
                           "shopFrom": d2s(SUSPECT_SHOP_FROM),
                           "serialsWith3PlusRemovals": sorted(s for s, n in rogue_counts.items() if n >= 3)},
            "stationFixEffectiveness": {"stationCode": "BWI", "ataChapter": "21"},
            "showcase": {"tailNumber": SHOWCASE_TAIL, "defectNumber": SHOWCASE_DEFECT,
                         "rogueSerial": ROGUE_SERIAL, "defects": self.showcase_defects},
        }


def inject_defects(ds: Dataset, rng: random.Random | None = None) -> Dataset:
    """Corrupt a few records in known ways so the SHACL validation has something to catch."""
    rng = rng or random.Random(99)
    showcase = set(ds.signals["showcase"]["defects"])

    def log(kind, record, detail):
        ds.injected.append({"defect": kind, "record": record, "detail": detail})

    defs = {m["defect_number"]: m for m in ds.defects}
    m = rng.choice([x for x in ds.deferrals if x["defect_number"] not in showcase])
    m["expiry_date"] = m["deferred_date"]
    log("DEFERRAL_EXPIRES_ON_DEFERRAL", m["deferral_number"], "expiry date equals deferred date")
    m = rng.choice([x for x in ds.deferrals if x["category"] == "C" and x["deferral_number"] != m["deferral_number"]])
    m["category"] = "X"
    log("BAD_MEL_CATEGORY", m["deferral_number"], "MEL category X")
    w = rng.choice([x for x in ds.work_orders if x["corrects_defect"] and x["corrects_defect"] not in showcase])
    w["close_date"] = (date.fromisoformat(w["open_date"]) - timedelta(days=2)).isoformat()
    log("WORK_ORDER_CLOSED_BEFORE_OPEN", w["work_order_number"], "close date before open date")
    w2 = rng.choice([x for x in ds.work_orders if x["corrects_defect"] and x is not w
                     and x["corrects_defect"] not in showcase])
    other = rng.choice([a["tail_number"] for a in ds.aircraft
                        if a["tail_number"] != defs[w2["corrects_defect"]]["tail_number"]])
    w2["tail_number"] = other
    log("WORK_ORDER_WRONG_AIRCRAFT", w2["work_order_number"], "corrects a defect on another aircraft")
    rm = rng.choice(ds.removals)
    rm["hours_since_install"] = "-12.0"
    log("NEGATIVE_HOURS", rm["removal_number"], "negative hours since install")
    d = rng.choice([x for x in ds.defects if x["defect_number"] not in showcase])
    d["ata_chapter"] = "99"
    log("UNKNOWN_ATA_CHAPTER", d["defect_number"], "ATA chapter 99 does not exist")
    d2 = rng.choice([x for x in ds.defects if x is not d and x["defect_number"] not in showcase])
    old = d2["defect_number"]
    d2["defect_number"] = "DF-" + old[3:6]
    log("BAD_DEFECT_NUMBER", d2["defect_number"], f"was {old}")
    for f in ds.flights:
        if f["delay_defect"] == old:
            f["delay_defect"] = d2["defect_number"]
    for x in ds.deferrals:
        if x["defect_number"] == old:
            x["defect_number"] = d2["defect_number"]
    for x in ds.work_orders:
        if x["corrects_defect"] == old:
            x["corrects_defect"] = d2["defect_number"]
    a = rng.choice([x for x in ds.aircraft if x["tail_number"] != SHOWCASE_TAIL])
    a["home_base"] = "XXX"
    log("UNKNOWN_HOME_BASE", a["tail_number"], "home base XXX is not a station")
    return ds


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--inject-defects", action="store_true")
    args = ap.parse_args()
    ds = Generator(args.seed).run()
    if args.inject_defects:
        inject_defects(ds)
    ds.write(args.out)
    m = ds.manifest()
    print(json.dumps({"out": str(args.out), "counts": m["counts"], "signals": m["signals"],
                      "injectedDefects": len(m["injectedDefects"])}, indent=2))


if __name__ == "__main__":
    main()
