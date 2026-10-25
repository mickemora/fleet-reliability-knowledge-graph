CREATE OR REPLACE VIEW fleet_reliability.maintenance.mv_operational_impact
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Flights delayed or cancelled by maintenance defects. Source: fro:FlightLeg."
source: fleet_reliability.maintenance.fact_flight_impact
joins:
  - name: defect
    source: fleet_reliability.maintenance.fact_defect
    'on': delayed_by = defect_number
    joins:
      - name: chapter
        source: fleet_reliability.maintenance.dim_ata_chapter
        'on': in_ata_chapter = ata_code
dimensions:
  - name: Flight Month
    expr: DATE_TRUNC('MONTH', flight_date)
  - name: Departure Station
    expr: departed_from
  - name: ATA Chapter
    expr: CONCAT(defect.chapter.ata_code, ' ', defect.chapter.name)
measures:
  - name: Flights Impacted
    expr: COUNT(1)
  - name: Delay Minutes
    expr: SUM(delay_minutes)
  - name: Cancellations
    expr: COUNT(1) FILTER (WHERE cancelled)
$$;
