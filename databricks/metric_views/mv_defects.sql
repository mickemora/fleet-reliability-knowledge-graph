CREATE OR REPLACE VIEW fleet_reliability.maintenance.mv_defects
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Defects by fleet type, ATA chapter and station. Source: fro:Defect."
source: fleet_reliability.maintenance.fact_defect
joins:
  - name: aircraft
    source: fleet_reliability.maintenance.dim_aircraft
    'on': defect_on = tail_number
  - name: chapter
    source: fleet_reliability.maintenance.dim_ata_chapter
    'on': in_ata_chapter = ata_code
dimensions:
  - name: Reported Month
    expr: DATE_TRUNC('MONTH', reported_date)
  - name: Aircraft Model
    expr: aircraft.aircraft_model
  - name: ATA Chapter
    expr: CONCAT(chapter.ata_code, ' ', chapter.name)
  - name: System Group
    expr: chapter.system_group
  - name: Station
    expr: reported_at
  - name: Report Source
    expr: report_source
measures:
  - name: Defects
    expr: COUNT(1)
  - name: Pilot Reports
    expr: COUNT(1) FILTER (WHERE report_source = 'Pilot report')
  - name: Open Or Deferred
    expr: COUNT(1) FILTER (WHERE status IN ('OPEN', 'DEFERRED'))
$$;
