CREATE OR REPLACE VIEW fleet_reliability.maintenance.mv_component_removals
WITH METRICS
LANGUAGE YAML
AS $$
version: 1.1
comment: "Unscheduled removals and time to removal by part and by the shop that last repaired the unit. Source: fro:ComponentRemoval."
source: fleet_reliability.maintenance.fact_component_removal
joins:
  - name: unit
    source: fleet_reliability.maintenance.dim_component_unit
    'on': removed_unit = serial_number
    joins:
      - name: part
        source: fleet_reliability.maintenance.dim_part
        'on': of_part = part_number
  - name: shop
    source: fleet_reliability.maintenance.dim_vendor
    'on': after_repair_by = vendor_code
dimensions:
  - name: Removal Month
    expr: DATE_TRUNC('MONTH', removal_date)
  - name: Part
    expr: CONCAT(unit.part.part_number, ' ', unit.part.name)
  - name: Repaired By
    expr: shop.name
  - name: Shop Finding
    expr: shop_finding
measures:
  - name: Unscheduled Removals
    expr: COUNT(1) FILTER (WHERE unscheduled)
  - name: Mean Hours To Removal
    expr: AVG(hours_since_install)
  - name: No Fault Found Rate
    expr: AVG(CASE WHEN shop_finding = 'No fault found' THEN 1.0 ELSE 0.0 END)
$$;
