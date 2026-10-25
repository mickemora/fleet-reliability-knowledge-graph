-- Generated from ontology/fleet.ttl by fleet_kg/lakehouse.py. Do not edit by hand.
-- Prerequisite: a Unity Catalog external location covering the path below
-- (see docs/databricks.md). Run in a SQL warehouse or notebook with Unity Catalog.

CREATE CATALOG IF NOT EXISTS fleet_reliability;
CREATE SCHEMA IF NOT EXISTS fleet_reliability.maintenance
  COMMENT 'Fleet reliability: one logical model (the ontology) shared with the Neptune knowledge graph';

-- dim_station: ontology class fro:Station
CREATE TABLE IF NOT EXISTS fleet_reliability.maintenance.dim_station USING DELTA LOCATION 's3://<data-bucket>/lakehouse/delta/dim_station';
COMMENT ON TABLE fleet_reliability.maintenance.dim_station IS 'An airport where the airline performs line maintenance; some are maintenance bases.';
ALTER TABLE fleet_reliability.maintenance.dim_station SET TAGS ('ontology_class' = 'fro:Station', 'ontology_iri' = 'https://fleet.example.com/ontology#Station');
ALTER TABLE fleet_reliability.maintenance.dim_station ALTER COLUMN station_code COMMENT 'Station code';
ALTER TABLE fleet_reliability.maintenance.dim_station ALTER COLUMN station_code SET TAGS ('ontology_property' = 'fro:stationCode');
ALTER TABLE fleet_reliability.maintenance.dim_station ALTER COLUMN name COMMENT 'Display name (rdfs:label) of the Station.';
ALTER TABLE fleet_reliability.maintenance.dim_station ALTER COLUMN city COMMENT 'City';
ALTER TABLE fleet_reliability.maintenance.dim_station ALTER COLUMN city SET TAGS ('ontology_property' = 'fro:city');
ALTER TABLE fleet_reliability.maintenance.dim_station ALTER COLUMN state COMMENT 'State';
ALTER TABLE fleet_reliability.maintenance.dim_station ALTER COLUMN state SET TAGS ('ontology_property' = 'fro:state');
ALTER TABLE fleet_reliability.maintenance.dim_station ALTER COLUMN station_type COMMENT 'Station type';
ALTER TABLE fleet_reliability.maintenance.dim_station ALTER COLUMN station_type SET TAGS ('ontology_property' = 'fro:stationType');
ALTER TABLE fleet_reliability.maintenance.dim_station ALTER COLUMN station_code SET NOT NULL;
ALTER TABLE fleet_reliability.maintenance.dim_station ADD CONSTRAINT dim_station_pk PRIMARY KEY (station_code);

-- dim_vendor: ontology class fro:Vendor
CREATE TABLE IF NOT EXISTS fleet_reliability.maintenance.dim_vendor USING DELTA LOCATION 's3://<data-bucket>/lakehouse/delta/dim_vendor';
COMMENT ON TABLE fleet_reliability.maintenance.dim_vendor IS 'A component manufacturer (OEM) or a repair station that overhauls components.';
ALTER TABLE fleet_reliability.maintenance.dim_vendor SET TAGS ('ontology_class' = 'fro:Vendor', 'ontology_iri' = 'https://fleet.example.com/ontology#Vendor');
ALTER TABLE fleet_reliability.maintenance.dim_vendor ALTER COLUMN vendor_code COMMENT 'Vendor code';
ALTER TABLE fleet_reliability.maintenance.dim_vendor ALTER COLUMN vendor_code SET TAGS ('ontology_property' = 'fro:vendorCode');
ALTER TABLE fleet_reliability.maintenance.dim_vendor ALTER COLUMN name COMMENT 'Display name (rdfs:label) of the Vendor.';
ALTER TABLE fleet_reliability.maintenance.dim_vendor ALTER COLUMN city COMMENT 'City';
ALTER TABLE fleet_reliability.maintenance.dim_vendor ALTER COLUMN city SET TAGS ('ontology_property' = 'fro:city');
ALTER TABLE fleet_reliability.maintenance.dim_vendor ALTER COLUMN country COMMENT 'Country';
ALTER TABLE fleet_reliability.maintenance.dim_vendor ALTER COLUMN country SET TAGS ('ontology_property' = 'fro:country');
ALTER TABLE fleet_reliability.maintenance.dim_vendor ALTER COLUMN vendor_type COMMENT 'Vendor type';
ALTER TABLE fleet_reliability.maintenance.dim_vendor ALTER COLUMN vendor_type SET TAGS ('ontology_property' = 'fro:vendorType');
ALTER TABLE fleet_reliability.maintenance.dim_vendor ALTER COLUMN vendor_code SET NOT NULL;
ALTER TABLE fleet_reliability.maintenance.dim_vendor ADD CONSTRAINT dim_vendor_pk PRIMARY KEY (vendor_code);

-- dim_ata_chapter: ontology class fro:AtaChapter
CREATE TABLE IF NOT EXISTS fleet_reliability.maintenance.dim_ata_chapter USING DELTA LOCATION 's3://<data-bucket>/lakehouse/delta/dim_ata_chapter';
COMMENT ON TABLE fleet_reliability.maintenance.dim_ata_chapter IS 'A node in the ATA iSpec 2200 aircraft system numbering, for example 36 Pneumatic within Airframe Systems.';
ALTER TABLE fleet_reliability.maintenance.dim_ata_chapter SET TAGS ('ontology_class' = 'fro:AtaChapter', 'ontology_iri' = 'https://fleet.example.com/ontology#AtaChapter');
ALTER TABLE fleet_reliability.maintenance.dim_ata_chapter ALTER COLUMN ata_code COMMENT 'ATA code';
ALTER TABLE fleet_reliability.maintenance.dim_ata_chapter ALTER COLUMN ata_code SET TAGS ('ontology_property' = 'fro:ataCode');
ALTER TABLE fleet_reliability.maintenance.dim_ata_chapter ALTER COLUMN name COMMENT 'Display name (rdfs:label) of the AtaChapter.';
ALTER TABLE fleet_reliability.maintenance.dim_ata_chapter ALTER COLUMN system_group COMMENT 'ATA code of the top-level system group (skos:broader).';
ALTER TABLE fleet_reliability.maintenance.dim_ata_chapter ALTER COLUMN ata_code SET NOT NULL;
ALTER TABLE fleet_reliability.maintenance.dim_ata_chapter ADD CONSTRAINT dim_ata_chapter_pk PRIMARY KEY (ata_code);

-- dim_part: ontology class fro:Part
CREATE TABLE IF NOT EXISTS fleet_reliability.maintenance.dim_part USING DELTA LOCATION 's3://<data-bucket>/lakehouse/delta/dim_part';
COMMENT ON TABLE fleet_reliability.maintenance.dim_part IS 'A part number: the design of a component, with its ATA chapter and manufacturer.';
ALTER TABLE fleet_reliability.maintenance.dim_part SET TAGS ('ontology_class' = 'fro:Part', 'ontology_iri' = 'https://fleet.example.com/ontology#Part');
ALTER TABLE fleet_reliability.maintenance.dim_part ALTER COLUMN part_number COMMENT 'Part number';
ALTER TABLE fleet_reliability.maintenance.dim_part ALTER COLUMN part_number SET TAGS ('ontology_property' = 'fro:partNumber');
ALTER TABLE fleet_reliability.maintenance.dim_part ALTER COLUMN name COMMENT 'Display name (rdfs:label) of the Part.';
ALTER TABLE fleet_reliability.maintenance.dim_part ALTER COLUMN in_ata_chapter COMMENT 'In ATA chapter (ATA Chapter ata code).';
ALTER TABLE fleet_reliability.maintenance.dim_part ALTER COLUMN in_ata_chapter SET TAGS ('ontology_property' = 'fro:inAtaChapter');
ALTER TABLE fleet_reliability.maintenance.dim_part ALTER COLUMN manufactured_by COMMENT 'Manufactured by (Vendor vendor code).';
ALTER TABLE fleet_reliability.maintenance.dim_part ALTER COLUMN manufactured_by SET TAGS ('ontology_property' = 'fro:manufacturedBy');
ALTER TABLE fleet_reliability.maintenance.dim_part ALTER COLUMN mtbur_target COMMENT 'Expected mean time between unscheduled removals in flight hours, from the reliability program.';
ALTER TABLE fleet_reliability.maintenance.dim_part ALTER COLUMN mtbur_target SET TAGS ('ontology_property' = 'fro:mtburTarget');
ALTER TABLE fleet_reliability.maintenance.dim_part ALTER COLUMN unit_cost COMMENT 'Unit cost (USD)';
ALTER TABLE fleet_reliability.maintenance.dim_part ALTER COLUMN unit_cost SET TAGS ('ontology_property' = 'fro:unitCost');
ALTER TABLE fleet_reliability.maintenance.dim_part ALTER COLUMN part_number SET NOT NULL;
ALTER TABLE fleet_reliability.maintenance.dim_part ADD CONSTRAINT dim_part_pk PRIMARY KEY (part_number);

-- dim_aircraft: ontology class fro:Aircraft
CREATE TABLE IF NOT EXISTS fleet_reliability.maintenance.dim_aircraft USING DELTA LOCATION 's3://<data-bucket>/lakehouse/delta/dim_aircraft';
COMMENT ON TABLE fleet_reliability.maintenance.dim_aircraft IS 'A single aircraft in the fleet, identified by its registration (tail number).';
ALTER TABLE fleet_reliability.maintenance.dim_aircraft SET TAGS ('ontology_class' = 'fro:Aircraft', 'ontology_iri' = 'https://fleet.example.com/ontology#Aircraft');
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN tail_number COMMENT 'Tail number';
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN tail_number SET TAGS ('ontology_property' = 'fro:tailNumber');
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN aircraft_model COMMENT 'Aircraft model';
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN aircraft_model SET TAGS ('ontology_property' = 'fro:aircraftModel');
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN cycles_in_period COMMENT 'Departures flown in the reporting period (2025-10-01 to 2026-09-30); the denominator for defect rates.';
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN cycles_in_period SET TAGS ('ontology_property' = 'fro:cyclesInPeriod');
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN delivery_date COMMENT 'Delivery date';
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN delivery_date SET TAGS ('ontology_property' = 'fro:deliveryDate');
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN engine_type COMMENT 'Engine type';
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN engine_type SET TAGS ('ontology_property' = 'fro:engineType');
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN flight_cycles COMMENT 'Takeoff-and-landing cycles since delivery.';
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN flight_cycles SET TAGS ('ontology_property' = 'fro:flightCycles');
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN flight_hours COMMENT 'Total flight hours';
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN flight_hours SET TAGS ('ontology_property' = 'fro:flightHours');
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN home_base COMMENT 'Home base (Station station code).';
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN home_base SET TAGS ('ontology_property' = 'fro:homeBase');
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN msn COMMENT 'Manufacturer serial number';
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN msn SET TAGS ('ontology_property' = 'fro:msn');
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ALTER COLUMN tail_number SET NOT NULL;
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ADD CONSTRAINT dim_aircraft_pk PRIMARY KEY (tail_number);

-- dim_component_unit: ontology class fro:ComponentUnit
CREATE TABLE IF NOT EXISTS fleet_reliability.maintenance.dim_component_unit USING DELTA LOCATION 's3://<data-bucket>/lakehouse/delta/dim_component_unit';
COMMENT ON TABLE fleet_reliability.maintenance.dim_component_unit IS 'One physical, serial-numbered instance of a part. It moves between aircraft and repair shops over its life.';
ALTER TABLE fleet_reliability.maintenance.dim_component_unit SET TAGS ('ontology_class' = 'fro:ComponentUnit', 'ontology_iri' = 'https://fleet.example.com/ontology#ComponentUnit');
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ALTER COLUMN serial_number COMMENT 'Serial number';
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ALTER COLUMN serial_number SET TAGS ('ontology_property' = 'fro:serialNumber');
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ALTER COLUMN installed_on COMMENT 'Where the unit is installed now. Units in a shop or in stores have none. (Aircraft tail number).';
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ALTER COLUMN installed_on SET TAGS ('ontology_property' = 'fro:installedOn');
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ALTER COLUMN last_repaired_by COMMENT 'Last repaired by (Vendor vendor code).';
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ALTER COLUMN last_repaired_by SET TAGS ('ontology_property' = 'fro:lastRepairedBy');
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ALTER COLUMN last_shop_visit_date COMMENT 'Last shop visit date';
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ALTER COLUMN last_shop_visit_date SET TAGS ('ontology_property' = 'fro:lastShopVisitDate');
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ALTER COLUMN of_part COMMENT 'Of part (Part part number).';
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ALTER COLUMN of_part SET TAGS ('ontology_property' = 'fro:ofPart');
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ALTER COLUMN serial_number SET NOT NULL;
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ADD CONSTRAINT dim_component_unit_pk PRIMARY KEY (serial_number);

-- dim_airworthiness_directive: ontology class fro:AirworthinessDirective
CREATE TABLE IF NOT EXISTS fleet_reliability.maintenance.dim_airworthiness_directive USING DELTA LOCATION 's3://<data-bucket>/lakehouse/delta/dim_airworthiness_directive';
COMMENT ON TABLE fleet_reliability.maintenance.dim_airworthiness_directive IS 'A mandatory action required by the regulator on the aircraft models it applies to, by a compliance date.';
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive SET TAGS ('ontology_class' = 'fro:AirworthinessDirective', 'ontology_iri' = 'https://fleet.example.com/ontology#AirworthinessDirective');
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN ad_number COMMENT 'AD number';
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN ad_number SET TAGS ('ontology_property' = 'fro:adNumber');
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN applies_to_model COMMENT 'An aircraft model the directive applies to (one value per model).';
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN applies_to_model SET TAGS ('ontology_property' = 'fro:appliesToModel');
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN compliance_date COMMENT 'Compliance date';
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN compliance_date SET TAGS ('ontology_property' = 'fro:complianceDate');
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN effective_date COMMENT 'Effective date';
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN effective_date SET TAGS ('ontology_property' = 'fro:effectiveDate');
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN in_ata_chapter COMMENT 'In ATA chapter (ATA Chapter ata code).';
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN in_ata_chapter SET TAGS ('ontology_property' = 'fro:inAtaChapter');
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN title COMMENT 'Title';
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN title SET TAGS ('ontology_property' = 'fro:title');
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ALTER COLUMN ad_number SET NOT NULL;
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ADD CONSTRAINT dim_airworthiness_directive_pk PRIMARY KEY (ad_number);

-- fact_defect: ontology class fro:Defect
CREATE TABLE IF NOT EXISTS fleet_reliability.maintenance.fact_defect USING DELTA LOCATION 's3://<data-bucket>/lakehouse/delta/fact_defect';
COMMENT ON TABLE fleet_reliability.maintenance.fact_defect IS 'A reported fault on an aircraft: a pilot report (PIREP) or a maintenance finding.';
ALTER TABLE fleet_reliability.maintenance.fact_defect SET TAGS ('ontology_class' = 'fro:Defect', 'ontology_iri' = 'https://fleet.example.com/ontology#Defect');
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN defect_number COMMENT 'Defect number';
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN defect_number SET TAGS ('ontology_property' = 'fro:defectNumber');
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN defect_on COMMENT 'Defect on (Aircraft tail number).';
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN defect_on SET TAGS ('ontology_property' = 'fro:defectOn');
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN description COMMENT 'Description';
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN description SET TAGS ('ontology_property' = 'fro:description');
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN status COMMENT 'Defect status: OPEN, DEFERRED or CLOSED.';
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN status SET TAGS ('ontology_property' = 'fro:hasStatus');
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN in_ata_chapter COMMENT 'In ATA chapter (ATA Chapter ata code).';
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN in_ata_chapter SET TAGS ('ontology_property' = 'fro:inAtaChapter');
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN report_source COMMENT 'Pilot report (PIREP) or Maintenance finding (MAREP).';
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN report_source SET TAGS ('ontology_property' = 'fro:reportSource');
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN reported_at COMMENT 'Reported at (Station station code).';
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN reported_at SET TAGS ('ontology_property' = 'fro:reportedAt');
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN reported_date COMMENT 'Reported date';
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN reported_date SET TAGS ('ontology_property' = 'fro:reportedDate');
ALTER TABLE fleet_reliability.maintenance.fact_defect ALTER COLUMN defect_number SET NOT NULL;
ALTER TABLE fleet_reliability.maintenance.fact_defect ADD CONSTRAINT fact_defect_pk PRIMARY KEY (defect_number);

-- fact_deferral: ontology class fro:Deferral
CREATE TABLE IF NOT EXISTS fleet_reliability.maintenance.fact_deferral USING DELTA LOCATION 's3://<data-bucket>/lakehouse/delta/fact_deferral';
COMMENT ON TABLE fleet_reliability.maintenance.fact_deferral IS 'Permission to fly with a defect unrepaired under a Minimum Equipment List item, until an expiry date set by the item\'s category.';
ALTER TABLE fleet_reliability.maintenance.fact_deferral SET TAGS ('ontology_class' = 'fro:Deferral', 'ontology_iri' = 'https://fleet.example.com/ontology#Deferral');
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN deferral_number COMMENT 'Deferral number';
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN deferral_number SET TAGS ('ontology_property' = 'fro:deferralNumber');
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN cleared_date COMMENT 'Cleared date';
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN cleared_date SET TAGS ('ontology_property' = 'fro:clearedDate');
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN deferral_on COMMENT 'Deferral on (Aircraft tail number).';
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN deferral_on SET TAGS ('ontology_property' = 'fro:deferralOn');
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN deferred_date COMMENT 'Deferred date';
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN deferred_date SET TAGS ('ontology_property' = 'fro:deferredDate');
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN defers COMMENT 'Defers (Defect defect number).';
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN defers SET TAGS ('ontology_property' = 'fro:defers');
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN expiry_date COMMENT 'Expiry date';
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN expiry_date SET TAGS ('ontology_property' = 'fro:expiryDate');
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN mel_category COMMENT 'Repair interval category: B (3 calendar days) or C (10 calendar days) in this pilot.';
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN mel_category SET TAGS ('ontology_property' = 'fro:melCategory');
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN mel_item COMMENT 'MEL item';
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN mel_item SET TAGS ('ontology_property' = 'fro:melItem');
ALTER TABLE fleet_reliability.maintenance.fact_deferral ALTER COLUMN deferral_number SET NOT NULL;
ALTER TABLE fleet_reliability.maintenance.fact_deferral ADD CONSTRAINT fact_deferral_pk PRIMARY KEY (deferral_number);

-- fact_work_order: ontology class fro:WorkOrder
CREATE TABLE IF NOT EXISTS fleet_reliability.maintenance.fact_work_order USING DELTA LOCATION 's3://<data-bucket>/lakehouse/delta/fact_work_order';
COMMENT ON TABLE fleet_reliability.maintenance.fact_work_order IS 'Maintenance work performed on an aircraft at a station: correcting a defect or accomplishing a directive.';
ALTER TABLE fleet_reliability.maintenance.fact_work_order SET TAGS ('ontology_class' = 'fro:WorkOrder', 'ontology_iri' = 'https://fleet.example.com/ontology#WorkOrder');
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN work_order_number COMMENT 'Work order number';
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN work_order_number SET TAGS ('ontology_property' = 'fro:workOrderNumber');
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN accomplishes COMMENT 'Accomplishes (Airworthiness Directive ad number).';
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN accomplishes SET TAGS ('ontology_property' = 'fro:accomplishes');
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN action COMMENT 'Corrective action';
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN action SET TAGS ('ontology_property' = 'fro:action');
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN close_date COMMENT 'Close date';
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN close_date SET TAGS ('ontology_property' = 'fro:closeDate');
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN corrects COMMENT 'Corrects (Defect defect number).';
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN corrects SET TAGS ('ontology_property' = 'fro:corrects');
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN labor_hours COMMENT 'Labor hours';
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN labor_hours SET TAGS ('ontology_property' = 'fro:laborHours');
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN open_date COMMENT 'Open date';
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN open_date SET TAGS ('ontology_property' = 'fro:openDate');
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN performed_at COMMENT 'Performed at (Station station code).';
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN performed_at SET TAGS ('ontology_property' = 'fro:performedAt');
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN work_order_on COMMENT 'Work order on (Aircraft tail number).';
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN work_order_on SET TAGS ('ontology_property' = 'fro:workOrderOn');
ALTER TABLE fleet_reliability.maintenance.fact_work_order ALTER COLUMN work_order_number SET NOT NULL;
ALTER TABLE fleet_reliability.maintenance.fact_work_order ADD CONSTRAINT fact_work_order_pk PRIMARY KEY (work_order_number);

-- fact_component_removal: ontology class fro:ComponentRemoval
CREATE TABLE IF NOT EXISTS fleet_reliability.maintenance.fact_component_removal USING DELTA LOCATION 's3://<data-bucket>/lakehouse/delta/fact_component_removal';
COMMENT ON TABLE fleet_reliability.maintenance.fact_component_removal IS 'The removal of a serialized component from an aircraft during a work order, with the hours it flew since installation and what the repair shop found.';
ALTER TABLE fleet_reliability.maintenance.fact_component_removal SET TAGS ('ontology_class' = 'fro:ComponentRemoval', 'ontology_iri' = 'https://fleet.example.com/ontology#ComponentRemoval');
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN removal_number COMMENT 'Removal number';
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN removal_number SET TAGS ('ontology_property' = 'fro:removalNumber');
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN after_repair_by COMMENT 'The shop that last repaired the unit before the installation that ended in this removal. The basis for repair-shop reliability. (Vendor vendor code).';
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN after_repair_by SET TAGS ('ontology_property' = 'fro:afterRepairBy');
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN during_work_order COMMENT 'During work order (Work Order work order number).';
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN during_work_order SET TAGS ('ontology_property' = 'fro:duringWorkOrder');
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN hours_since_install COMMENT 'Flight hours the unit flew between installation and this removal (time since installation, TSI).';
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN hours_since_install SET TAGS ('ontology_property' = 'fro:hoursSinceInstall');
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN removal_date COMMENT 'Removal date';
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN removal_date SET TAGS ('ontology_property' = 'fro:removalDate');
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN removal_reason COMMENT 'Removal reason';
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN removal_reason SET TAGS ('ontology_property' = 'fro:removalReason');
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN removed_from COMMENT 'Removed from (Aircraft tail number).';
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN removed_from SET TAGS ('ontology_property' = 'fro:removedFrom');
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN removed_unit COMMENT 'Removed unit (Component serial number).';
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN removed_unit SET TAGS ('ontology_property' = 'fro:removedUnit');
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN shop_finding COMMENT 'Confirmed failure, or No fault found (NFF): the shop could not reproduce the fault.';
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN shop_finding SET TAGS ('ontology_property' = 'fro:shopFinding');
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN unscheduled COMMENT 'Unscheduled';
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN unscheduled SET TAGS ('ontology_property' = 'fro:unscheduled');
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ALTER COLUMN removal_number SET NOT NULL;
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ADD CONSTRAINT fact_component_removal_pk PRIMARY KEY (removal_number);

-- fact_flight_impact: ontology class fro:FlightLeg
CREATE TABLE IF NOT EXISTS fleet_reliability.maintenance.fact_flight_impact USING DELTA LOCATION 's3://<data-bucket>/lakehouse/delta/fact_flight_impact';
COMMENT ON TABLE fleet_reliability.maintenance.fact_flight_impact IS 'One scheduled flight on one date. In this pilot, only flights delayed or cancelled by a maintenance defect are recorded.';
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact SET TAGS ('ontology_class' = 'fro:FlightLeg', 'ontology_iri' = 'https://fleet.example.com/ontology#FlightLeg');
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN flight_leg_id COMMENT 'Flight leg ID';
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN flight_leg_id SET TAGS ('ontology_property' = 'fro:flightLegId');
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN cancelled COMMENT 'Cancelled';
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN cancelled SET TAGS ('ontology_property' = 'fro:cancelled');
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN delay_minutes COMMENT 'Delay minutes';
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN delay_minutes SET TAGS ('ontology_property' = 'fro:delayMinutes');
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN delayed_by COMMENT 'Delayed by (Defect defect number).';
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN delayed_by SET TAGS ('ontology_property' = 'fro:delayedBy');
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN departed_from COMMENT 'Departs from (Station station code).';
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN departed_from SET TAGS ('ontology_property' = 'fro:departedFrom');
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN flight_date COMMENT 'Flight date';
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN flight_date SET TAGS ('ontology_property' = 'fro:flightDate');
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN flight_number COMMENT 'Flight number';
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN flight_number SET TAGS ('ontology_property' = 'fro:flightNumber');
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN operated_by COMMENT 'Operated by (Aircraft tail number).';
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN operated_by SET TAGS ('ontology_property' = 'fro:operatedBy');
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ALTER COLUMN flight_leg_id SET NOT NULL;
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ADD CONSTRAINT fact_flight_impact_pk PRIMARY KEY (flight_leg_id);

-- Relationships: informational foreign keys, one per single-valued ontology relationship
ALTER TABLE fleet_reliability.maintenance.dim_ata_chapter ADD CONSTRAINT dim_ata_chapter_system_group_fk FOREIGN KEY (system_group) REFERENCES fleet_reliability.maintenance.dim_ata_chapter (ata_code);
ALTER TABLE fleet_reliability.maintenance.dim_part ADD CONSTRAINT dim_part_in_ata_chapter_fk FOREIGN KEY (in_ata_chapter) REFERENCES fleet_reliability.maintenance.dim_ata_chapter (ata_code);
ALTER TABLE fleet_reliability.maintenance.dim_part ADD CONSTRAINT dim_part_manufactured_by_fk FOREIGN KEY (manufactured_by) REFERENCES fleet_reliability.maintenance.dim_vendor (vendor_code);
ALTER TABLE fleet_reliability.maintenance.dim_aircraft ADD CONSTRAINT dim_aircraft_home_base_fk FOREIGN KEY (home_base) REFERENCES fleet_reliability.maintenance.dim_station (station_code);
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ADD CONSTRAINT dim_component_unit_installed_on_fk FOREIGN KEY (installed_on) REFERENCES fleet_reliability.maintenance.dim_aircraft (tail_number);
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ADD CONSTRAINT dim_component_unit_last_repaired_by_fk FOREIGN KEY (last_repaired_by) REFERENCES fleet_reliability.maintenance.dim_vendor (vendor_code);
ALTER TABLE fleet_reliability.maintenance.dim_component_unit ADD CONSTRAINT dim_component_unit_of_part_fk FOREIGN KEY (of_part) REFERENCES fleet_reliability.maintenance.dim_part (part_number);
ALTER TABLE fleet_reliability.maintenance.dim_airworthiness_directive ADD CONSTRAINT dim_airworthiness_directive_in_ata_chapter_fk FOREIGN KEY (in_ata_chapter) REFERENCES fleet_reliability.maintenance.dim_ata_chapter (ata_code);
ALTER TABLE fleet_reliability.maintenance.fact_defect ADD CONSTRAINT fact_defect_defect_on_fk FOREIGN KEY (defect_on) REFERENCES fleet_reliability.maintenance.dim_aircraft (tail_number);
ALTER TABLE fleet_reliability.maintenance.fact_defect ADD CONSTRAINT fact_defect_in_ata_chapter_fk FOREIGN KEY (in_ata_chapter) REFERENCES fleet_reliability.maintenance.dim_ata_chapter (ata_code);
ALTER TABLE fleet_reliability.maintenance.fact_defect ADD CONSTRAINT fact_defect_reported_at_fk FOREIGN KEY (reported_at) REFERENCES fleet_reliability.maintenance.dim_station (station_code);
ALTER TABLE fleet_reliability.maintenance.fact_deferral ADD CONSTRAINT fact_deferral_deferral_on_fk FOREIGN KEY (deferral_on) REFERENCES fleet_reliability.maintenance.dim_aircraft (tail_number);
ALTER TABLE fleet_reliability.maintenance.fact_deferral ADD CONSTRAINT fact_deferral_defers_fk FOREIGN KEY (defers) REFERENCES fleet_reliability.maintenance.fact_defect (defect_number);
ALTER TABLE fleet_reliability.maintenance.fact_work_order ADD CONSTRAINT fact_work_order_accomplishes_fk FOREIGN KEY (accomplishes) REFERENCES fleet_reliability.maintenance.dim_airworthiness_directive (ad_number);
ALTER TABLE fleet_reliability.maintenance.fact_work_order ADD CONSTRAINT fact_work_order_corrects_fk FOREIGN KEY (corrects) REFERENCES fleet_reliability.maintenance.fact_defect (defect_number);
ALTER TABLE fleet_reliability.maintenance.fact_work_order ADD CONSTRAINT fact_work_order_performed_at_fk FOREIGN KEY (performed_at) REFERENCES fleet_reliability.maintenance.dim_station (station_code);
ALTER TABLE fleet_reliability.maintenance.fact_work_order ADD CONSTRAINT fact_work_order_work_order_on_fk FOREIGN KEY (work_order_on) REFERENCES fleet_reliability.maintenance.dim_aircraft (tail_number);
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ADD CONSTRAINT fact_component_removal_after_repair_by_fk FOREIGN KEY (after_repair_by) REFERENCES fleet_reliability.maintenance.dim_vendor (vendor_code);
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ADD CONSTRAINT fact_component_removal_during_work_order_fk FOREIGN KEY (during_work_order) REFERENCES fleet_reliability.maintenance.fact_work_order (work_order_number);
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ADD CONSTRAINT fact_component_removal_removed_from_fk FOREIGN KEY (removed_from) REFERENCES fleet_reliability.maintenance.dim_aircraft (tail_number);
ALTER TABLE fleet_reliability.maintenance.fact_component_removal ADD CONSTRAINT fact_component_removal_removed_unit_fk FOREIGN KEY (removed_unit) REFERENCES fleet_reliability.maintenance.dim_component_unit (serial_number);
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ADD CONSTRAINT fact_flight_impact_delayed_by_fk FOREIGN KEY (delayed_by) REFERENCES fleet_reliability.maintenance.fact_defect (defect_number);
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ADD CONSTRAINT fact_flight_impact_departed_from_fk FOREIGN KEY (departed_from) REFERENCES fleet_reliability.maintenance.dim_station (station_code);
ALTER TABLE fleet_reliability.maintenance.fact_flight_impact ADD CONSTRAINT fact_flight_impact_operated_by_fk FOREIGN KEY (operated_by) REFERENCES fleet_reliability.maintenance.dim_aircraft (tail_number);
