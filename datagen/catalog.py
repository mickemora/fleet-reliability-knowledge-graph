"""Static reference data for the synthetic fleet maintenance dataset.

The airline ("Bluebonnet Air", flight prefix BB), its tail numbers, vendors, part numbers and
airworthiness directives are fictional. Airport codes, aircraft types, engine types and ATA chapter
numbers are real industry references, used so the data reads like the real thing.
"""

AIRLINE = "Bluebonnet Air"
FLIGHT_PREFIX = "BB"

# code: (name, city, state, station type)
STATIONS = {
    "DAL": ("Dallas Love Field", "Dallas", "TX", "Maintenance base"),
    "HOU": ("Houston Hobby", "Houston", "TX", "Maintenance base"),
    "PHX": ("Phoenix Sky Harbor", "Phoenix", "AZ", "Maintenance base"),
    "MCO": ("Orlando International", "Orlando", "FL", "Maintenance base"),
    "BWI": ("Baltimore/Washington", "Baltimore", "MD", "Line"),
    "MDW": ("Chicago Midway", "Chicago", "IL", "Line"),
    "DEN": ("Denver International", "Denver", "CO", "Line"),
    "LAS": ("Las Vegas Harry Reid", "Las Vegas", "NV", "Line"),
    "OAK": ("Oakland International", "Oakland", "CA", "Line"),
    "ATL": ("Atlanta Hartsfield-Jackson", "Atlanta", "GA", "Line"),
    "BNA": ("Nashville International", "Nashville", "TN", "Line"),
    "AUS": ("Austin-Bergstrom", "Austin", "TX", "Line"),
    "SAN": ("San Diego International", "San Diego", "CA", "Line"),
    "STL": ("St. Louis Lambert", "St. Louis", "MO", "Line"),
    "MSY": ("New Orleans Armstrong", "New Orleans", "LA", "Line"),
    "TPA": ("Tampa International", "Tampa", "FL", "Line"),
    "LAX": ("Los Angeles International", "Los Angeles", "CA", "Line"),
    "SJC": ("San Jose Mineta", "San Jose", "CA", "Line"),
    "ELP": ("El Paso International", "El Paso", "TX", "Line"),
    "SAT": ("San Antonio International", "San Antonio", "TX", "Line"),
}
BASES = ["DAL", "HOU", "PHX", "MCO"]
STATION_WEIGHTS = {c: (6 if c in BASES else 2) for c in STATIONS}

# model: (count, tail prefix digit, engine type, delivery year range, hours/day, cycles/day)
FLEET = {
    "737-700": (55, "7", "CFM56-7B24", (2005, 2012), 9.1, 5.6),
    "737-800": (60, "8", "CFM56-7B27", (2013, 2018), 9.8, 5.0),
    "737 MAX 8": (45, "9", "LEAP-1B27", (2019, 2024), 10.2, 4.9),
}

# ATA chapters (iSpec 2200 numbering), grouped into three system groups.
ATA_GROUPS = {"AFS": "Airframe Systems", "STR": "Structures", "PWR": "Power Plant"}
ATA_CHAPTERS = {
    "21": ("Air Conditioning", "AFS"), "22": ("Auto Flight", "AFS"), "23": ("Communications", "AFS"),
    "24": ("Electrical Power", "AFS"), "25": ("Equipment/Furnishings", "AFS"),
    "26": ("Fire Protection", "AFS"), "27": ("Flight Controls", "AFS"), "28": ("Fuel", "AFS"),
    "29": ("Hydraulic Power", "AFS"), "30": ("Ice and Rain Protection", "AFS"),
    "31": ("Indicating/Recording Systems", "AFS"), "32": ("Landing Gear", "AFS"),
    "33": ("Lights", "AFS"), "34": ("Navigation", "AFS"), "35": ("Oxygen", "AFS"),
    "36": ("Pneumatic", "AFS"), "38": ("Water/Waste", "AFS"), "49": ("Airborne Auxiliary Power", "AFS"),
    "52": ("Doors", "STR"), "53": ("Fuselage", "STR"), "56": ("Windows", "STR"),
    "73": ("Engine Fuel and Control", "PWR"), "77": ("Engine Indicating", "PWR"),
    "79": ("Oil", "PWR"), "80": ("Starting", "PWR"),
}

# (code, name, vendor type, city, country)
VENDORS = [
    ("V01", "Aerotherm Systems", "OEM", "Phoenix", "US"),
    ("V02", "Northwind Air Management", "OEM", "Torrance", "US"),
    ("V03", "Skyline Avionics", "OEM", "Cedar Rapids", "US"),
    ("V04", "Titan Landing Systems", "OEM", "Cleveland", "US"),
    ("V05", "Gulf Coast Aero Components", "Repair station", "Lafayette", "US"),
    ("V06", "Mesa Component Services", "Repair station", "Mesa", "US"),
    ("V07", "Great Lakes Aero Repair", "Repair station", "Grand Rapids", "US"),
    ("V08", "Corvus Electrical", "OEM", "Rockford", "US"),
    ("V09", "Atlas Engine Accessories", "OEM", "Windsor Locks", "US"),
]
REPAIR_STATIONS = ["V05", "V06", "V07"]

# Rotable parts: (part number, name, ATA, OEM, unit cost, positions per aircraft,
#                 mean flight hours between unscheduled removals, MEL item or None,
#                 defect description, corrective action)
PARTS = [
    ("BV3611-04", "Bleed Air Pressure Regulating Valve", "36", "V01", 38_500, 2, 9_000, "36-11-01",
     "BLEED TRIP OFF light during climb", "Replaced pressure regulating and shutoff valve, ops check good"),
    ("PC2150-12", "Pack Flow Control Valve", "21", "V02", 27_400, 2, 14_000, "21-51-01",
     "Pack trip off in cruise, cabin warm", "Replaced pack flow control valve, ops check good"),
    ("TS2161-03", "Cabin Temperature Sensor", "21", "V02", 1_900, 1, 22_000, None,
     "Cabin temperature fluctuating", "Replaced zone temperature sensor"),
    ("AC2271-09", "Autopilot Flight Control Computer", "22", "V03", 112_000, 1, 30_000, "22-11-01",
     "Autopilot A disengaged in cruise", "Replaced flight control computer A, BITE test passed"),
    ("RT2312-20", "VHF Transceiver", "23", "V03", 18_600, 1, 26_000, "23-12-01",
     "VHF 2 static, unable to transmit", "Replaced VHF transceiver 2"),
    ("GC2421-06", "Generator Control Unit", "24", "V08", 21_300, 1, 24_000, "24-22-01",
     "GEN 2 OFF BUS light, generator dropped offline", "Replaced generator control unit"),
    ("FD2615-02", "Engine Fire Detector Loop", "26", "V08", 6_200, 1, 40_000, "26-11-01",
     "Engine fire detection fault on test", "Replaced fire detector loop element"),
    ("SA2721-15", "Aileron Power Control Unit", "27", "V04", 64_800, 1, 45_000, None,
     "Aileron trim requires excessive input", "Replaced aileron PCU, rigging check good"),
    ("FP2841-07", "Fuel Boost Pump", "28", "V09", 15_900, 1, 20_000, "28-22-01",
     "Fuel pump LOW PRESSURE light", "Replaced fuel boost pump"),
    ("HP2911-11", "Engine-Driven Hydraulic Pump", "29", "V04", 33_700, 1, 18_000, "29-11-01",
     "Hydraulic system A low pressure", "Replaced engine-driven hydraulic pump"),
    ("WH3041-05", "Window Heat Controller", "30", "V08", 4_800, 1, 16_000, "30-41-01",
     "Window heat OVERHEAT light", "Replaced window heat controller"),
    ("DU3162-01", "Common Display Unit", "31", "V03", 58_200, 1, 35_000, "31-62-01",
     "Captain outboard display blank", "Replaced display unit"),
    ("BR3242-08", "Main Wheel Brake Assembly", "32", "V04", 24_100, 1, 12_000, None,
     "Brake temperature high after landing", "Replaced brake assembly"),
    ("LG3233-02", "Landing Gear Retract Actuator", "32", "V04", 41_900, 1, 50_000, None,
     "Gear disagree light on retraction", "Replaced retract actuator, gear swing good"),
    ("LT3341-10", "Landing Light Assembly", "33", "V08", 2_300, 1, 9_000, "33-42-01",
     "Left landing light inoperative", "Replaced landing light assembly"),
    ("IR3421-04", "Air Data Inertial Reference Unit", "34", "V03", 96_500, 1, 32_000, "34-21-01",
     "IRS FAULT light, alignment failure", "Replaced ADIRU, alignment check good"),
    ("OX3511-01", "Crew Oxygen Mask", "35", "V09", 3_100, 1, 28_000, "35-11-01",
     "Crew oxygen mask flow check failed", "Replaced crew oxygen mask"),
    ("AP4911-02", "APU Starter Generator", "49", "V09", 29_800, 1, 11_000, "49-11-01",
     "APU fails to start", "Replaced APU starter generator"),
    ("FC7321-06", "Fuel Metering Unit", "73", "V09", 88_400, 1, 40_000, None,
     "Engine 1 fuel flow fluctuating", "Replaced fuel metering unit"),
    ("ST8011-03", "Engine Air Turbine Starter", "80", "V01", 26_700, 1, 15_000, "80-11-01",
     "Engine 2 slow start, starter valve open light", "Replaced air turbine starter"),
]
SUSPECT_PART = "BV3611-04"
SUSPECT_VENDOR = "V05"

# Non-rotable defects (no component removal): (ATA, description, action, MEL item or None)
SIMPLE_DEFECTS = [
    ("25", "Row 14 seat recline inoperative", "Adjusted seat recline lock", "25-21-01"),
    ("25", "Lavatory door latch sticking", "Lubricated and adjusted latch", None),
    ("33", "Reading light 22C inoperative", "Replaced lamp", "33-21-01"),
    ("38", "Aft lavatory toilet not flushing", "Cleared waste line blockage", "38-31-01"),
    ("52", "Forward entry door seal damaged", "Replaced door seal section", None),
    ("53", "Lightning strike found on walkaround", "Inspected and blended per SRM", None),
    ("56", "First officer side window delaminating", "Inspected within limits, scheduled replacement", "56-11-01"),
    ("23", "PA inaudible in aft cabin", "Reseated PA amplifier connector", "23-31-01"),
    ("21", "Cabin too warm at gate", "Cleaned pack heat exchanger inlet, ops check good", "21-51-01"),
    ("31", "Flight data recorder fault message", "Reset FDAU, fault cleared", None),
    ("77", "Engine 1 vibration indication fluctuating", "Cleaned vibration sensor connector", None),
    ("79", "Engine 2 oil quantity indication low", "Serviced oil, no leaks found", None),
]

# Airworthiness directives (fictional numbers): (number, title, ATA, effective, compliance by,
#                                               models, share of applicable aircraft complied)
DIRECTIVES = [
    ("AD-2025-11-03", "Main landing gear retract actuator inspection", "32", "2025-11-15", "2026-06-30",
     ["737-700", "737-800"], 1.0),
    ("AD-2026-04-11", "Aileron power control unit rigging check", "27", "2026-05-01", "2026-10-31",
     ["737 MAX 8"], 0.66),
    ("AD-2026-07-22", "Engine fire detection loop inspection", "26", "2026-08-01", "2027-01-31",
     ["737-700", "737-800", "737 MAX 8"], 0.4),
]

MEL_CATEGORY_DAYS = {"B": 3, "C": 10}
