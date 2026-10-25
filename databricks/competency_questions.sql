-- Competency questions in Databricks SQL, over the ontology-shaped Delta tables.
--
-- The same business questions as queries/competency/*.rq (SPARQL on Neptune), answered from the
-- lakehouse. Table and column names are the ontology's classes and properties, so the two
-- versions read alike. Aggregate questions are natural in SQL; multi-hop questions (CQ01 Tail 360,
-- CQ10 fleet exposure) are where the graph is the better tool, and the explorer uses it for them.
--
-- Run after databricks/unity_catalog.sql has registered the tables.

USE CATALOG fleet_reliability;
USE SCHEMA maintenance;

-- CQ03 Rogue units: removed 3+ times, short time on wing, often "no fault found"
SELECT r.removed_unit                                   AS serial_number,
       p.name                                           AS part,
       COUNT(*)                                         AS removals,
       COUNT(DISTINCT r.removed_from)                   AS aircraft,
       ROUND(AVG(r.hours_since_install))                AS avg_hours_since_install,
       SUM(CASE WHEN r.shop_finding = 'No fault found' THEN 1 ELSE 0 END) AS no_fault_found,
       FIRST(v.name)                                    AS last_repaired_by
FROM fact_component_removal r
JOIN dim_component_unit u ON u.serial_number = r.removed_unit
JOIN dim_part p           ON p.part_number = u.of_part
LEFT JOIN dim_vendor v    ON v.vendor_code = u.last_repaired_by
WHERE r.unscheduled
GROUP BY r.removed_unit, p.name
HAVING COUNT(*) >= 3 AND AVG(r.hours_since_install) <= 1500
ORDER BY removals DESC, avg_hours_since_install;

-- CQ04 Defects per 1,000 departures by aircraft model and ATA chapter
WITH departures AS (
  SELECT aircraft_model, SUM(cycles_in_period) AS departures FROM dim_aircraft GROUP BY aircraft_model
)
SELECT a.aircraft_model,
       g.name                                           AS system_group,
       CONCAT('ATA ', c.ata_code, ' ', c.name)          AS chapter,
       COUNT(*)                                         AS defects,
       d.departures,
       ROUND(1000 * COUNT(*) / d.departures, 2)         AS per_1000_departures
FROM fact_defect f
JOIN dim_aircraft a     ON a.tail_number = f.defect_on
JOIN dim_ata_chapter c  ON c.ata_code = f.in_ata_chapter
JOIN dim_ata_chapter g  ON g.ata_code = c.system_group
JOIN departures d       ON d.aircraft_model = a.aircraft_model
GROUP BY a.aircraft_model, g.name, c.ata_code, c.name, d.departures
ORDER BY per_1000_departures DESC
LIMIT 25;

-- CQ05 Repair shop reliability for the bleed air pressure regulating valve
SELECT v.vendor_code, v.name AS vendor, v.vendor_type,
       COUNT(*)                                         AS unscheduled_removals,
       ROUND(AVG(r.hours_since_install))                AS mean_hours_to_removal,
       ROUND(100 * AVG(CASE WHEN r.shop_finding = 'No fault found' THEN 1 ELSE 0 END)) AS no_fault_found_pct
FROM fact_component_removal r
JOIN dim_component_unit u ON u.serial_number = r.removed_unit
JOIN dim_vendor v         ON v.vendor_code = r.after_repair_by
WHERE r.unscheduled AND u.of_part = 'BV3611-04'
GROUP BY v.vendor_code, v.name, v.vendor_type
ORDER BY mean_hours_to_removal;

-- CQ08 Fix effectiveness by station: ATA 21 fixes followed by another ATA 21 write-up within 3 days
WITH fixes AS (
  SELECT w.work_order_number, w.performed_at, w.work_order_on, w.close_date, d.defect_number
  FROM fact_work_order w
  JOIN fact_defect d ON d.defect_number = w.corrects
  WHERE d.in_ata_chapter = '21'
),
repeats AS (
  SELECT DISTINCT f.work_order_number
  FROM fixes f
  JOIN fact_defect d2
    ON d2.defect_on = f.work_order_on AND d2.in_ata_chapter = '21'
   AND d2.defect_number <> f.defect_number
   AND d2.reported_date BETWEEN f.close_date AND date_add(f.close_date, 3)
)
SELECT f.performed_at                                   AS station_code,
       COUNT(*)                                         AS fixes,
       COUNT(r.work_order_number)                       AS repeated_within_3_days,
       ROUND(100 * COUNT(r.work_order_number) / COUNT(*)) AS repeat_pct
FROM fixes f
LEFT JOIN repeats r ON r.work_order_number = f.work_order_number
GROUP BY f.performed_at
HAVING COUNT(*) >= 5
ORDER BY repeat_pct DESC;

-- CQ09 Operational impact by ATA chapter
SELECT CONCAT('ATA ', c.ata_code, ' ', c.name)          AS chapter,
       COUNT(*)                                         AS flights_impacted,
       SUM(f.delay_minutes)                             AS delay_minutes,
       SUM(CASE WHEN f.cancelled THEN 1 ELSE 0 END)     AS cancellations
FROM fact_flight_impact f
JOIN fact_defect d     ON d.defect_number = f.delayed_by
JOIN dim_ata_chapter c ON c.ata_code = d.in_ata_chapter
GROUP BY c.ata_code, c.name
ORDER BY delay_minutes DESC;

-- The same KPIs through the governed metric views (databricks/metric_views/)
SELECT `Repaired By`, MEASURE(`Unscheduled Removals`), MEASURE(`Mean Hours To Removal`),
       MEASURE(`No Fault Found Rate`)
FROM mv_component_removals
WHERE `Part` LIKE 'BV3611-04%'
GROUP BY ALL
ORDER BY 3;
