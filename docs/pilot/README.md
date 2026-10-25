# Pilot playbook: six weeks, week by week

The working material for each week of the pilot, and where this repository already produces the
deliverable from the synthetic dataset.

## Week 1: Business discovery

**Problem statement.** Defects, MEL deferrals, work orders, component removals, shop findings,
airworthiness directives and delays live in separate systems. Linking a write-up to the unit
that was removed, the shop that last repaired it, the other aircraft that unit flew on and the
flights it delayed takes hours of manual lookups. Rogue units, weak repair shops and fixes that
don't hold are found late, and engineering, maintenance control and the data team each define
"repeat defect" or "MTBUR" a little differently.

**Target use case: Fleet Reliability Explorer.** Let reliability engineers and maintenance
control follow any defect to its aircraft, deferral, work order, removed unit, repair shop and
operational impact through one ontology, and give the data platform (Databricks) the same
definitions as governed tables and metrics.

**Discovery workshop (2 hours: reliability engineering, maintenance control, technical records,
data platform).** Walk through the last chronic-defect investigation (systems, lookups, time) ·
brainstorm the questions people wish took one step · prioritize the top ten · agree success
metrics and the synthetic-data approach.

**Competency questions:** the ten in [`queries/competency/`](../../queries/competency/), listed in
the [README](../../README.md#the-ten-competency-questions).

**Success metrics.** SME-approved glossary and ontology · all ten questions answered and signed
off · a pipeline run that conforms, loads and passes the smoke test · graph and lakehouse answers
identical · stakeholder demo · agreed next phase. Optional: time to assemble a tail 360 and to find
rogue units today versus in the explorer.

**Stakeholders.** Sponsor (VP Maintenance & Engineering or Reliability) · reliability engineers and
maintenance controllers (SMEs) · ontology engineer · cloud/data engineer · Databricks platform
owner · security/architecture review · system owners of the maintenance information system.

## Week 2: Ontology modeling

Artifacts: [`ontology/fleet.ttl`](../../ontology/fleet.ttl) (OWL), [`reference/ata-chapters.ttl`](../../reference/ata-chapters.ttl)
(SKOS), [`shapes/fleet-shapes.ttl`](../../shapes/fleet-shapes.ttl) (SHACL), and the generated
[lakehouse model](../lakehouse-model.md), which shows how each class becomes a table.

**Glossary**

| Term | Definition | Ontology term |
|---|---|---|
| Aircraft (tail) | One aircraft, identified by its registration | `fro:Aircraft` |
| Defect (write-up) | A reported fault: a pilot report or a maintenance finding | `fro:Defect` |
| MEL deferral | Permission to fly with a defect unrepaired under an MEL item until an expiry date set by its category | `fro:Deferral` |
| Work order | Maintenance performed at a station: correcting a defect or accomplishing a directive | `fro:WorkOrder` |
| Component (serialized unit, rotable) | One physical, serial-numbered instance of a part | `fro:ComponentUnit` |
| Component removal | Removing a unit during a work order, with hours since installation and the shop finding | `fro:ComponentRemoval` |
| Part | A part number: the design, with its ATA chapter and manufacturer | `fro:Part` |
| Vendor | An OEM or a repair station | `fro:Vendor` |
| Station | An airport with line maintenance; some are maintenance bases | `fro:Station` |
| Airworthiness directive | A mandatory action on the models it applies to, by a compliance date | `fro:AirworthinessDirective` |
| ATA chapter | Aircraft system number (iSpec 2200), grouped into system groups | `fro:AtaChapter` |
| Hours since install (TSI) | Flight hours a unit flew between installation and removal | `fro:hoursSinceInstall` |
| No fault found (NFF) | The shop could not reproduce the reported failure | `fro:shopFinding` |
| Mean hours to removal | Average TSI at unscheduled removal; the pilot's MTBUR measure | CQ05, `mv_component_removals` |
| Repeat defect | 3+ write-ups in one ATA chapter on one tail within 10 days | CQ02 |
| Rogue unit | A serial removed 3+ times with short TSI, often NFF | CQ03 |

**Modeling decisions to review with SMEs.** Removal is its own class (not a property of the work
order) because TSI, shop finding and "after repair by" belong to the event · `afterRepairBy`
records the shop that repaired the unit *before* the installation that failed, which is what
shop reliability needs · flights are recorded only when a defect delayed or cancelled them ·
day numbers exist only for interval rules in the graph; the lakehouse uses date functions.

## Week 3: Knowledge graph and lakehouse

`python -m datagen.generate` writes one year of maintenance extracts (1,267 defects, 1,454 work
orders, 317 deferrals, 791 removals, 3,681 serialized units, 245 impacted flights for seed 42).
The Step Functions pipeline transforms them to RDF, validates them with SHACL, then in parallel
loads Neptune (with materialized inferences and the ten-question smoke test) and writes the
Delta tables through Glue. Data-quality report: `python scripts/kg.py report` (deployed) or
`python scripts/kg.py validate --local`; see the README for the eight-defect demonstration.

## Week 4: Query and validation

Results: [`docs/competency-results.md`](../competency-results.md). SQL versions:
[`databricks/competency_questions.sql`](../../databricks/competency_questions.sql), checked
against the SPARQL answers by `tests/test_lakehouse.py`.

| CQ | Answer correct? | Useful as presented? | Changes requested | SME | Date |
|---|---|---|---|---|---|
| CQ01–CQ10 | | | | | |

## Week 5: Business user experience

**Key workflows in the explorer.**

1. *Chronic defect:* search `DF-100245` → deferral, delay, work order, removed unit BV10457 and
   its shop → "View defects in this chapter" shows three in nine days.
2. *Rogue unit:* click BV10457 → three removals from three aircraft, all "no fault found" →
   CQ03 for the fleet-wide list.
3. *Shop review:* CQ05 → Gulf Coast Aero Components → CQ10 for the tails flying with its units.
4. *Station support:* CQ08 → BWI's ATA 21 repeats → click BWI.
5. *Planning:* CQ06 (deferrals expiring) and CQ07 (directive gaps) for maintenance control.

**Databricks.** The same KPIs as metric views (`mv_component_removals`, `mv_defects`,
`mv_operational_impact`) for dashboards and Genie; see [databricks.md](../databricks.md).

| Date | User / role | Workflow | Feedback | Change made |
|---|---|---|---|---|
| | | | | |

## Week 6: Demonstration and evaluation

**Demo script (15 minutes).**

| Min | Show | Say |
|---|---|---|
| 0 | Infographic | Maintenance data in many systems; one ontology for graph and lakehouse |
| 2 | Explorer → `DF-100245` | One write-up, and everything connected to it, in one view |
| 4 | Click BV10457 | The same unit came off three aircraft, "no fault found" each time |
| 6 | CQ03 → CQ05 | A rogue population, and the shop behind it: ~550 hours versus ~6,000 |
| 8 | CQ10 | Nine tails flying with that shop's valves today: a targeted removal campaign |
| 9 | CQ09 | What it cost: 88 flights and almost 8,000 delay minutes in ATA 36 |
| 10 | CQ08 | A different kind of finding: BWI's air conditioning fixes don't hold |
| 11 | Databricks: `unity_catalog.sql`, a metric view, CQ05 in SQL | Same definitions, comments, keys and answer in the lakehouse |
| 13 | Ontology, SHACL report, pipeline | The reusable foundation, 100% AWS CDK |
| 14 | Next phase | |

**Scorecard.** Validated concepts · 10 questions answered · graph and Delta tables from one
ontology, with identical answers · demonstration delivered · next phase agreed.

**Next-phase options.** Real data from the maintenance information system through the same
mapping → SHACL → graph ∥ lakehouse pipeline · supplier and repair-shop quality (shop visit
reports, warranty recovery) · predictive reliability (removal-rate alerting from
`mv_component_removals`, survival curves per part and shop) · an AI reliability assistant that
chains the competency questions · linking to the flight-operations disruption graph through
shared flight and station identifiers.
