# Lakehouse model (generated)

Generated from `ontology/fleet.ttl` by `python scripts/generate_databricks.py`. Each table is one ontology class; each column is one ontology property. Keys (PK) and foreign keys (FK) come from business-key and single-valued relationship properties. See [databricks.md](databricks.md) for how this is used.

## `dim_station`: `fro:Station`

An airport where the airline performs line maintenance; some are maintenance bases.

| Column | Type | Ontology property | Key | Description |
|---|---|---|---|---|
| `station_code` | STRING | `fro:stationCode` | PK | Station code |
| `name` | STRING | `rdfs:label` |  | Display name (rdfs:label) of the Station. |
| `city` | STRING | `fro:city` |  | City |
| `state` | STRING | `fro:state` |  | State |
| `station_type` | STRING | `fro:stationType` |  | Station type |

## `dim_vendor`: `fro:Vendor`

A component manufacturer (OEM) or a repair station that overhauls components.

| Column | Type | Ontology property | Key | Description |
|---|---|---|---|---|
| `vendor_code` | STRING | `fro:vendorCode` | PK | Vendor code |
| `name` | STRING | `rdfs:label` |  | Display name (rdfs:label) of the Vendor. |
| `city` | STRING | `fro:city` |  | City |
| `country` | STRING | `fro:country` |  | Country |
| `vendor_type` | STRING | `fro:vendorType` |  | Vendor type |

## `dim_ata_chapter`: `fro:AtaChapter`

A node in the ATA iSpec 2200 aircraft system numbering, for example 36 Pneumatic within Airframe Systems.

| Column | Type | Ontology property | Key | Description |
|---|---|---|---|---|
| `ata_code` | STRING | `fro:ataCode` | PK | ATA code |
| `name` | STRING | `rdfs:label` |  | Display name (rdfs:label) of the AtaChapter. |
| `system_group` | STRING | `skos:broader` | FK → `dim_ata_chapter` | ATA code of the top-level system group (skos:broader). |

## `dim_part`: `fro:Part`

A part number: the design of a component, with its ATA chapter and manufacturer.

| Column | Type | Ontology property | Key | Description |
|---|---|---|---|---|
| `part_number` | STRING | `fro:partNumber` | PK | Part number |
| `name` | STRING | `rdfs:label` |  | Display name (rdfs:label) of the Part. |
| `in_ata_chapter` | STRING | `fro:inAtaChapter` | FK → `dim_ata_chapter` | In ATA chapter (ATA Chapter ata code). |
| `manufactured_by` | STRING | `fro:manufacturedBy` | FK → `dim_vendor` | Manufactured by (Vendor vendor code). |
| `mtbur_target` | BIGINT | `fro:mtburTarget` |  | Expected mean time between unscheduled removals in flight hours, from the reliability program. |
| `unit_cost` | DECIMAL(14,2) | `fro:unitCost` |  | Unit cost (USD) |

## `dim_aircraft`: `fro:Aircraft`

A single aircraft in the fleet, identified by its registration (tail number).

| Column | Type | Ontology property | Key | Description |
|---|---|---|---|---|
| `tail_number` | STRING | `fro:tailNumber` | PK | Tail number |
| `aircraft_model` | STRING | `fro:aircraftModel` |  | Aircraft model |
| `cycles_in_period` | BIGINT | `fro:cyclesInPeriod` |  | Departures flown in the reporting period (2025-10-01 to 2026-09-30); the denominator for defect rates. |
| `delivery_date` | DATE | `fro:deliveryDate` |  | Delivery date |
| `engine_type` | STRING | `fro:engineType` |  | Engine type |
| `flight_cycles` | BIGINT | `fro:flightCycles` |  | Takeoff-and-landing cycles since delivery. |
| `flight_hours` | DECIMAL(14,2) | `fro:flightHours` |  | Total flight hours |
| `home_base` | STRING | `fro:homeBase` | FK → `dim_station` | Home base (Station station code). |
| `msn` | STRING | `fro:msn` |  | Manufacturer serial number |

## `dim_component_unit`: `fro:ComponentUnit`

One physical, serial-numbered instance of a part. It moves between aircraft and repair shops over its life.

| Column | Type | Ontology property | Key | Description |
|---|---|---|---|---|
| `serial_number` | STRING | `fro:serialNumber` | PK | Serial number |
| `installed_on` | STRING | `fro:installedOn` | FK → `dim_aircraft` | Where the unit is installed now. Units in a shop or in stores have none. (Aircraft tail number). |
| `last_repaired_by` | STRING | `fro:lastRepairedBy` | FK → `dim_vendor` | Last repaired by (Vendor vendor code). |
| `last_shop_visit_date` | DATE | `fro:lastShopVisitDate` |  | Last shop visit date |
| `of_part` | STRING | `fro:ofPart` | FK → `dim_part` | Of part (Part part number). |

## `dim_airworthiness_directive`: `fro:AirworthinessDirective`

A mandatory action required by the regulator on the aircraft models it applies to, by a compliance date.

| Column | Type | Ontology property | Key | Description |
|---|---|---|---|---|
| `ad_number` | STRING | `fro:adNumber` | PK | AD number |
| `applies_to_model` | ARRAY<STRING> | `fro:appliesToModel` |  | An aircraft model the directive applies to (one value per model). |
| `compliance_date` | DATE | `fro:complianceDate` |  | Compliance date |
| `effective_date` | DATE | `fro:effectiveDate` |  | Effective date |
| `in_ata_chapter` | STRING | `fro:inAtaChapter` | FK → `dim_ata_chapter` | In ATA chapter (ATA Chapter ata code). |
| `title` | STRING | `fro:title` |  | Title |

## `fact_defect`: `fro:Defect`

A reported fault on an aircraft: a pilot report (PIREP) or a maintenance finding.

| Column | Type | Ontology property | Key | Description |
|---|---|---|---|---|
| `defect_number` | STRING | `fro:defectNumber` | PK | Defect number |
| `defect_on` | STRING | `fro:defectOn` | FK → `dim_aircraft` | Defect on (Aircraft tail number). |
| `description` | STRING | `fro:description` |  | Description |
| `status` | STRING | `fro:hasStatus` |  | Defect status: OPEN, DEFERRED or CLOSED. |
| `in_ata_chapter` | STRING | `fro:inAtaChapter` | FK → `dim_ata_chapter` | In ATA chapter (ATA Chapter ata code). |
| `report_source` | STRING | `fro:reportSource` |  | Pilot report (PIREP) or Maintenance finding (MAREP). |
| `reported_at` | STRING | `fro:reportedAt` | FK → `dim_station` | Reported at (Station station code). |
| `reported_date` | DATE | `fro:reportedDate` |  | Reported date |

## `fact_deferral`: `fro:Deferral`

Permission to fly with a defect unrepaired under a Minimum Equipment List item, until an expiry date set by the item's category.

| Column | Type | Ontology property | Key | Description |
|---|---|---|---|---|
| `deferral_number` | STRING | `fro:deferralNumber` | PK | Deferral number |
| `cleared_date` | DATE | `fro:clearedDate` |  | Cleared date |
| `deferral_on` | STRING | `fro:deferralOn` | FK → `dim_aircraft` | Deferral on (Aircraft tail number). |
| `deferred_date` | DATE | `fro:deferredDate` |  | Deferred date |
| `defers` | STRING | `fro:defers` | FK → `fact_defect` | Defers (Defect defect number). |
| `expiry_date` | DATE | `fro:expiryDate` |  | Expiry date |
| `mel_category` | STRING | `fro:melCategory` |  | Repair interval category: B (3 calendar days) or C (10 calendar days) in this pilot. |
| `mel_item` | STRING | `fro:melItem` |  | MEL item |

## `fact_work_order`: `fro:WorkOrder`

Maintenance work performed on an aircraft at a station: correcting a defect or accomplishing a directive.

| Column | Type | Ontology property | Key | Description |
|---|---|---|---|---|
| `work_order_number` | STRING | `fro:workOrderNumber` | PK | Work order number |
| `accomplishes` | STRING | `fro:accomplishes` | FK → `dim_airworthiness_directive` | Accomplishes (Airworthiness Directive ad number). |
| `action` | STRING | `fro:action` |  | Corrective action |
| `close_date` | DATE | `fro:closeDate` |  | Close date |
| `corrects` | STRING | `fro:corrects` | FK → `fact_defect` | Corrects (Defect defect number). |
| `labor_hours` | DECIMAL(14,2) | `fro:laborHours` |  | Labor hours |
| `open_date` | DATE | `fro:openDate` |  | Open date |
| `performed_at` | STRING | `fro:performedAt` | FK → `dim_station` | Performed at (Station station code). |
| `work_order_on` | STRING | `fro:workOrderOn` | FK → `dim_aircraft` | Work order on (Aircraft tail number). |

## `fact_component_removal`: `fro:ComponentRemoval`

The removal of a serialized component from an aircraft during a work order, with the hours it flew since installation and what the repair shop found.

| Column | Type | Ontology property | Key | Description |
|---|---|---|---|---|
| `removal_number` | STRING | `fro:removalNumber` | PK | Removal number |
| `after_repair_by` | STRING | `fro:afterRepairBy` | FK → `dim_vendor` | The shop that last repaired the unit before the installation that ended in this removal. The basis for repair-shop reliability. (Vendor vendor code). |
| `during_work_order` | STRING | `fro:duringWorkOrder` | FK → `fact_work_order` | During work order (Work Order work order number). |
| `hours_since_install` | DECIMAL(14,2) | `fro:hoursSinceInstall` |  | Flight hours the unit flew between installation and this removal (time since installation, TSI). |
| `removal_date` | DATE | `fro:removalDate` |  | Removal date |
| `removal_reason` | STRING | `fro:removalReason` |  | Removal reason |
| `removed_from` | STRING | `fro:removedFrom` | FK → `dim_aircraft` | Removed from (Aircraft tail number). |
| `removed_unit` | STRING | `fro:removedUnit` | FK → `dim_component_unit` | Removed unit (Component serial number). |
| `shop_finding` | STRING | `fro:shopFinding` |  | Confirmed failure, or No fault found (NFF): the shop could not reproduce the fault. |
| `unscheduled` | BOOLEAN | `fro:unscheduled` |  | Unscheduled |

## `fact_flight_impact`: `fro:FlightLeg`

One scheduled flight on one date. In this pilot, only flights delayed or cancelled by a maintenance defect are recorded.

| Column | Type | Ontology property | Key | Description |
|---|---|---|---|---|
| `flight_leg_id` | STRING | `fro:flightLegId` | PK | Flight leg ID |
| `cancelled` | BOOLEAN | `fro:cancelled` |  | Cancelled |
| `delay_minutes` | BIGINT | `fro:delayMinutes` |  | Delay minutes |
| `delayed_by` | STRING | `fro:delayedBy` | FK → `fact_defect` | Delayed by (Defect defect number). |
| `departed_from` | STRING | `fro:departedFrom` | FK → `dim_station` | Departs from (Station station code). |
| `flight_date` | DATE | `fro:flightDate` |  | Flight date |
| `flight_number` | STRING | `fro:flightNumber` |  | Flight number |
| `operated_by` | STRING | `fro:operatedBy` | FK → `dim_aircraft` | Operated by (Aircraft tail number). |
