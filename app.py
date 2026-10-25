#!/usr/bin/env python3
"""CDK entry point for the Fleet Reliability Connectivity Pilot.

Context overrides (cdk deploy --all -c key=value):
  neptuneEngineVersion   default 1.4.7.1 (Serverless needs 1.2.0.1 or later)
  minNcu / maxNcu        default 1 / 8 (Serverless never scales below 1 NCU)
  autoLoad               default true: run the load pipeline on every deploy that changes data,
                         ontology, shapes or mapping code; -c autoLoad=false to run it by hand
  nlq                    default true: natural-language search with Amazon Bedrock
  nlqModelId             default global.anthropic.claude-sonnet-4-5-20250929-v1:0
                         (Claude Sonnet 4.5; any Bedrock model or
                         inference profile that supports the Converse API)
  lakehouse              default true: Delta Lake export (Glue job + crawler, Athena workgroup)
                         and Unity Catalog SQL for Databricks; -c lakehouse=false to skip
  glueDatabase           default fleet_reliability (Glue Data Catalog database name)
  databricksExternalId   optional: creates a read-only IAM role for a Databricks Unity Catalog
                         storage credential (see docs/databricks.md)
  notebook               default false: Neptune workbench notebook + Graph Explorer
                         (ml.t3.medium, billed while running)

Three stacks; deploy and destroy with --all.
"""

import os
from pathlib import Path

import aws_cdk as cdk

from infra.app_stack import FleetAppStack
from infra.core_stack import FleetCoreStack
from infra.notebook_stack import DEFAULT_PLATFORM, NotebookStack
from scripts.build_assets import build as build_assets
from fleet_kg.local import ensure_dataset

ROOT = Path(__file__).resolve().parent

app = cdk.App()


def flag(key: str, default: bool) -> bool:
    value = app.node.try_get_context(key)
    if value is None:
        return default
    return str(value).lower() not in ("false", "0", "no", "off")


# The synthetic dataset is generated on first synth (python -m datagen.generate to regenerate).
raw_dir = ensure_dataset(ROOT / "data" / "generated") / "raw"
bundles = build_assets()

env = cdk.Environment(account=os.getenv("CDK_DEFAULT_ACCOUNT"), region=os.getenv("CDK_DEFAULT_REGION"))
core = FleetCoreStack(
    app, "FleetKgCoreStack", env=env,
    raw_data_dir=raw_dir, core_code=bundles["core"], rdf_code=bundles["rdf"],
    engine_version=app.node.try_get_context("neptuneEngineVersion") or "1.4.7.1",
    min_ncu=float(app.node.try_get_context("minNcu") or 1),
    max_ncu=float(app.node.try_get_context("maxNcu") or 8),
    auto_load=flag("autoLoad", True),
    lakehouse=flag("lakehouse", True),
    glue_database=app.node.try_get_context("glueDatabase") or "fleet_reliability",
    databricks_external_id=app.node.try_get_context("databricksExternalId"),
    description="Fleet reliability: Neptune Serverless (RDF), S3, Delta lakehouse, load pipeline",
)
FleetAppStack(
    app, "FleetKgAppStack", env=env, core=core,
    nlq_enabled=flag("nlq", True), nlq_model_id=app.node.try_get_context("nlqModelId"),
    description="Fleet Reliability Explorer: CloudFront UI, HTTP API, explorer and NLQ Lambdas",
)
if flag("notebook", False):
    NotebookStack(app, "FleetKgNotebookStack", env=env, core=core,
                  platform=app.node.try_get_context("notebookPlatform") or DEFAULT_PLATFORM,
                  description="Neptune workbench notebook with Graph Explorer for SME sessions")

cdk.Tags.of(app).add("project", "fleet-reliability-knowledge-graph")
app.synth()
