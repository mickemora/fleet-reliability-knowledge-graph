"""Core stack: network, Neptune Serverless, the S3 data lake, the lakehouse and the pipeline.

    S3 (raw CSV, ontology, reference, shapes)
      -> Step Functions: transform -> SHACL validate -> in parallel:
           graph:     bulk load -> materialize -> competency questions   -> Neptune Serverless
           lakehouse: project tables -> Glue (Delta Lake) -> Glue crawler -> Delta tables in S3,
                      Glue Data Catalog / Athena, and Unity Catalog SQL for Databricks
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from aws_cdk import (
    Aws, CfnOutput, Duration, RemovalPolicy, Stack,
    aws_athena as athena,
    aws_ec2 as ec2,
    aws_glue as glue,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_neptune as neptune,
    aws_s3 as s3,
    aws_s3_assets as s3_assets,
    aws_s3_deployment as s3deploy,
    aws_stepfunctions as sfn,
    aws_stepfunctions_tasks as tasks,
    custom_resources as cr,
)
from constructs import Construct

from fleet_kg.lakehouse import TABLE_NAMES

ROOT = Path(__file__).resolve().parent.parent

# Neptune data-plane actions used by the admin (read/write) and explorer (read-only) functions.
ADMIN_ACTIONS = ["neptune-db:ReadDataViaQuery", "neptune-db:WriteDataViaQuery",
                 "neptune-db:DeleteDataViaQuery", "neptune-db:StartLoaderJob",
                 "neptune-db:GetLoaderJobStatus", "neptune-db:ListLoaderJobs",
                 "neptune-db:GetEngineStatus"]
READ_ACTIONS = ["neptune-db:ReadDataViaQuery"]
# Unity Catalog's AWS role, which assumes a customer role to read S3 (Databricks documentation).
DATABRICKS_UC_ROLE = "arn:aws:iam::414351767826:role/unity-catalog-prod-UCMasterRole-14S5ZJVKOTYTL"
DELTA_PREFIX = "lakehouse/delta"


def source_hash(*paths: Path) -> str:
    """Hash of every file the pipeline consumes, so a deploy reruns it only when they change."""
    h = hashlib.sha256()
    for base in paths:
        files = [base] if base.is_file() else sorted(p for p in base.rglob("*") if p.is_file())
        for f in files:
            if "__pycache__" in f.parts:
                continue
            h.update(str(f.relative_to(ROOT) if f.is_relative_to(ROOT) else f.name).encode())
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


class FleetCoreStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, *, raw_data_dir: Path,
                 core_code: Path, rdf_code: Path, engine_version: str, min_ncu: float,
                 max_ncu: float, auto_load: bool = True, lakehouse: bool = True,
                 glue_database: str = "fleet_reliability",
                 databricks_external_id: str | None = None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ---------------------------------------------------------------- network
        # Isolated subnets only (no NAT gateway, no internet path). The S3 gateway endpoint lets
        # Neptune's bulk loader read the data bucket.
        vpc = ec2.Vpc(
            self, "Vpc", max_azs=2, nat_gateways=0,
            subnet_configuration=[ec2.SubnetConfiguration(
                name="isolated", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24)],
            gateway_endpoints={"S3": ec2.GatewayVpcEndpointOptions(
                service=ec2.GatewayVpcEndpointAwsService.S3)},
        )
        isolated = vpc.select_subnets(subnet_type=ec2.SubnetType.PRIVATE_ISOLATED)
        client_sg = ec2.SecurityGroup(self, "GraphClientSg", vpc=vpc, allow_all_outbound=True,
                                      description="Lambda functions that query Neptune")
        neptune_sg = ec2.SecurityGroup(self, "NeptuneSg", vpc=vpc, allow_all_outbound=True,
                                       description="Neptune cluster")
        neptune_sg.add_ingress_rule(client_sg, ec2.Port.tcp(8182), "Graph clients")

        # ---------------------------------------------------------------- data bucket
        bucket = s3.Bucket(
            self, "DataBucket",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED, enforce_ssl=True, versioned=False,
            removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=True,
        )
        deployments = []
        for prefix, path in (("raw", raw_data_dir), ("ontology", ROOT / "ontology"),
                             ("reference", ROOT / "reference"), ("shapes", ROOT / "shapes")):
            deployments.append(s3deploy.BucketDeployment(
                self, f"Deploy{prefix.title()}",
                sources=[s3deploy.Source.asset(str(path))],
                destination_bucket=bucket, destination_key_prefix=f"{prefix}/",
                memory_limit=512))

        loader_role = iam.Role(self, "NeptuneLoaderRole",
                               assumed_by=iam.ServicePrincipal("rds.amazonaws.com"),
                               description="Neptune bulk loader: read the fleet data bucket")
        bucket.grant_read(loader_role)

        # ---------------------------------------------------------------- Neptune Serverless
        subnet_group = neptune.CfnDBSubnetGroup(
            self, "SubnetGroup", db_subnet_group_description="Fleet reliability knowledge graph",
            subnet_ids=isolated.subnet_ids)
        cluster = neptune.CfnDBCluster(
            self, "Cluster",
            engine_version=engine_version,
            db_subnet_group_name=subnet_group.ref,
            vpc_security_group_ids=[neptune_sg.security_group_id],
            iam_auth_enabled=True, storage_encrypted=True, deletion_protection=False,
            serverless_scaling_configuration=neptune.CfnDBCluster.ServerlessScalingConfigurationProperty(
                min_capacity=min_ncu, max_capacity=max_ncu),
            associated_roles=[neptune.CfnDBCluster.DBClusterRoleProperty(
                role_arn=loader_role.role_arn)],
        )
        cluster.apply_removal_policy(RemovalPolicy.DESTROY)   # demo: no final snapshot
        writer = neptune.CfnDBInstance(self, "Writer", db_instance_class="db.serverless",
                                       db_cluster_identifier=cluster.ref)
        writer.add_dependency(cluster)
        writer.apply_removal_policy(RemovalPolicy.DESTROY)
        cluster_data_arn = (f"arn:{Aws.PARTITION}:neptune-db:{Aws.REGION}:{Aws.ACCOUNT_ID}:"
                            f"{cluster.attr_cluster_resource_id}/*")

        # ---------------------------------------------------------------- functions
        core_asset = lambda_.Code.from_asset(str(core_code))
        rdf_asset = lambda_.Code.from_asset(str(rdf_code))

        def log_group(name: str) -> logs.LogGroup:
            return logs.LogGroup(self, f"{name}Logs", retention=logs.RetentionDays.ONE_MONTH,
                                 removal_policy=RemovalPolicy.DESTROY)

        admin = lambda_.Function(
            self, "GraphAdmin",
            description="Fleet KG admin: bulk load, materialize inferences, smoke test",
            runtime=lambda_.Runtime.PYTHON_3_13, architecture=lambda_.Architecture.ARM_64,
            handler="functions.admin.handler.handler", code=core_asset,
            timeout=Duration.minutes(5), memory_size=512,
            vpc=vpc, vpc_subnets=ec2.SubnetSelection(subnets=isolated.subnets),
            security_groups=[client_sg], log_group=log_group("GraphAdmin"),
            environment={"NEPTUNE_ENDPOINT": cluster.attr_endpoint,
                         "NEPTUNE_PORT": cluster.attr_port,
                         "LOADER_ROLE_ARN": loader_role.role_arn,
                         "DATA_BUCKET": bucket.bucket_name})
        admin.add_to_role_policy(iam.PolicyStatement(actions=ADMIN_ACTIONS,
                                                     resources=[cluster_data_arn]))
        admin.node.add_dependency(writer)

        rdf_tools = lambda_.Function(
            self, "RdfTools",
            description="Fleet KG: CSV-to-RDF transform and SHACL validation (rdflib, pySHACL)",
            runtime=lambda_.Runtime.PYTHON_3_13, architecture=lambda_.Architecture.ARM_64,
            handler="functions.rdf_tools.handler.handler", code=rdf_asset,
            timeout=Duration.minutes(10), memory_size=3008, log_group=log_group("RdfTools"),
            environment={"DATA_BUCKET": bucket.bucket_name})
        bucket.grant_read_write(rdf_tools)

        # ---------------------------------------------------------------- load pipeline
        def invoke(name: str, fn: lambda_.IFunction, payload: dict, result_path: str):
            return tasks.LambdaInvoke(
                self, name, lambda_function=fn, payload=sfn.TaskInput.from_object(payload),
                payload_response_only=True, result_path=result_path,
                retry_on_service_exceptions=True)

        transform = invoke("Transform CSV to RDF", rdf_tools, {"action": "transform"}, "$.transform")
        validate = invoke("Validate with SHACL", rdf_tools,
                          {"action": "validate", "execution.$": "$$.Execution.Name"}, "$.validation")
        load = invoke("Start bulk load", admin, {"action": "load"}, "$.load")
        wait = sfn.Wait(self, "Wait for load", time=sfn.WaitTime.duration(Duration.seconds(20)))
        status = invoke("Check load status", admin,
                        {"action": "load_status", "loadIds.$": "$.load.loadIds"}, "$.loadStatus")
        materialize = invoke("Materialize inferences", admin, {"action": "materialize"},
                             "$.materialize")
        smoke = invoke("Run competency questions", admin, {"action": "smoke_test"}, "$.smokeTest")

        dq_failed = sfn.Fail(self, "Data quality check failed",
                             error="DataQualityViolations",
                             cause="SHACL validation found violations. Nothing was loaded. "
                                   "See reports/latest.json in the data bucket.")
        load_failed = sfn.Fail(self, "Bulk load failed", error="LoadFailed",
                               cause="A Neptune bulk-load job failed. Run `python scripts/kg.py "
                                     "diagnose` for the loader errors.")
        smoke_failed = sfn.Fail(self, "Competency questions failed", error="SmokeTestFailed",
                                cause="At least one competency question returned no rows.")

        graph_branch = load.next(wait).next(status).next(
            sfn.Choice(self, "Load finished?")
            .when(sfn.Condition.string_equals("$.loadStatus.status", "COMPLETED"),
                  materialize.next(smoke).next(
                      sfn.Choice(self, "All questions answered?")
                      .when(sfn.Condition.boolean_equals("$.smokeTest.passed", True),
                            sfn.Succeed(self, "Knowledge graph ready"))
                      .otherwise(smoke_failed)))
            .when(sfn.Condition.string_equals("$.loadStatus.status", "FAILED"), load_failed)
            .otherwise(wait))
        publish = sfn.Parallel(self, "Publish to graph and lakehouse", result_path="$.publish")
        publish.branch(graph_branch)

        # ---------------------------------------------------------------- lakehouse (Databricks)
        # The same validated RDF, projected into ontology-shaped tables (fleet_kg/lakehouse.py)
        # and written as Delta Lake by a small Glue Spark job; a Glue crawler registers them in the
        # Glue Data Catalog (queryable from Athena), and the export step writes Unity Catalog SQL
        # so Databricks can register the same tables with the ontology's definitions.
        if lakehouse:
            glue_role = iam.Role(
                self, "GlueRole", assumed_by=iam.ServicePrincipal("glue.amazonaws.com"),
                managed_policies=[iam.ManagedPolicy.from_aws_managed_policy_name(
                    "service-role/AWSGlueServiceRole")],
                description="Glue Delta export job and crawler for the fleet lakehouse")
            bucket.grant_read_write(glue_role)
            script = s3_assets.Asset(self, "DeltaExportScript",
                                     path=str(ROOT / "glue" / "delta_export.py"))
            script.grant_read(glue_role)
            job = glue.CfnJob(
                self, "DeltaExportJob",
                description="Write ontology-shaped staging rows as Delta Lake tables",
                role=glue_role.role_arn, glue_version="5.0", worker_type="G.1X",
                number_of_workers=2, timeout=30, max_retries=0,
                command=glue.CfnJob.JobCommandProperty(
                    name="glueetl", python_version="3", script_location=script.s3_object_url),
                default_arguments={
                    "--datalake-formats": "delta",
                    "--conf": "spark.sql.extensions=io.delta.sql.DeltaSparkSessionExtension "
                              "--conf spark.sql.catalog.spark_catalog="
                              "org.apache.spark.sql.delta.catalog.DeltaCatalog "
                              "--conf spark.delta.logStore.class="
                              "org.apache.spark.sql.delta.storage.S3SingleDriverLogStore",
                    "--bucket": bucket.bucket_name,
                    "--staging_prefix": "lakehouse/staging",
                    "--delta_prefix": DELTA_PREFIX,
                    "--enable-continuous-cloudwatch-log": "true",
                    "--job-language": "python",
                })
            database = glue.CfnDatabase(
                self, "LakehouseDatabase", catalog_id=Aws.ACCOUNT_ID,
                database_input=glue.CfnDatabase.DatabaseInputProperty(
                    name=glue_database,
                    description="Fleet reliability Delta tables (generated from the ontology)"))
            crawler = glue.CfnCrawler(
                self, "DeltaCrawler", role=glue_role.role_arn, database_name=glue_database,
                description="Registers the fleet reliability Delta tables as native Delta tables",
                targets=glue.CfnCrawler.TargetsProperty(delta_targets=[
                    glue.CfnCrawler.DeltaTargetProperty(
                        delta_tables=[f"s3://{bucket.bucket_name}/{DELTA_PREFIX}/{t}/"
                                      for t in TABLE_NAMES],
                        write_manifest=False, create_native_delta_table=True)]),
                schema_change_policy=glue.CfnCrawler.SchemaChangePolicyProperty(
                    update_behavior="UPDATE_IN_DATABASE", delete_behavior="LOG"))
            crawler.add_dependency(database)
            athena.CfnWorkGroup(
                self, "AthenaWg", name=f"{glue_database}-wg", recursive_delete_option=True,
                description="Query the fleet reliability Delta tables",
                work_group_configuration=athena.CfnWorkGroup.WorkGroupConfigurationProperty(
                    result_configuration=athena.CfnWorkGroup.ResultConfigurationProperty(
                        output_location=f"s3://{bucket.bucket_name}/athena-results/")))

            export = invoke("Project lakehouse tables", rdf_tools, {"action": "export_lakehouse"},
                            "$.lakehouse")
            write_delta = tasks.GlueStartJobRun(
                self, "Write Delta tables (Glue)", glue_job_name=job.ref,
                integration_pattern=sfn.IntegrationPattern.RUN_JOB, result_path="$.glueRun")
            crawl = tasks.CallAwsService(
                self, "Register tables in Glue Data Catalog", service="glue",
                action="startCrawler", parameters={"Name": crawler.ref},
                iam_resources=[f"arn:{Aws.PARTITION}:glue:{Aws.REGION}:{Aws.ACCOUNT_ID}:"
                               f"crawler/{crawler.ref}"],
                result_path=sfn.JsonPath.DISCARD)
            lakehouse_ready = sfn.Succeed(self, "Lakehouse ready")
            crawl.add_catch(sfn.Pass(self, "Crawler already running").next(lakehouse_ready),
                            errors=["Glue.CrawlerRunningException"])
            publish.branch(export.next(write_delta).next(crawl).next(lakehouse_ready))

            CfnOutput(self, "DeltaLocation", value=f"s3://{bucket.bucket_name}/{DELTA_PREFIX}")
            CfnOutput(self, "GlueDatabase", value=glue_database)
            CfnOutput(self, "AthenaWorkGroup", value=f"{glue_database}-wg")
            CfnOutput(self, "UnityCatalogSql",
                      value=f"s3://{bucket.bucket_name}/lakehouse/databricks/unity_catalog.sql")

            # Optional: the IAM role a Databricks Unity Catalog storage credential uses to read the
            # Delta tables (read-only). Deploy with -c databricksExternalId=<external ID shown when
            # you create the storage credential in Databricks>; see docs/databricks.md.
            if databricks_external_id:
                role_name = f"{self.stack_name}-databricks-uc"
                self_arn = f"arn:{Aws.PARTITION}:iam::{Aws.ACCOUNT_ID}:role/{role_name}"
                uc_role = iam.Role(
                    self, "DatabricksUnityCatalogRole", role_name=role_name,
                    description="Databricks Unity Catalog storage credential: read fleet Delta tables",
                    assumed_by=iam.ArnPrincipal(DATABRICKS_UC_ROLE).with_conditions(
                        {"StringEquals": {"sts:ExternalId": databricks_external_id}}))
                # Unity Catalog requires the role to be self-assuming.
                uc_role.assume_role_policy.add_statements(iam.PolicyStatement(
                    principals=[iam.AccountRootPrincipal()], actions=["sts:AssumeRole"],
                    conditions={"ArnEquals": {"aws:PrincipalArn": self_arn},
                                "StringEquals": {"sts:ExternalId": databricks_external_id}}))
                uc_role.add_to_policy(iam.PolicyStatement(actions=["sts:AssumeRole"],
                                                          resources=[self_arn]))
                uc_role.add_to_policy(iam.PolicyStatement(
                    actions=["s3:GetObject", "s3:GetObjectVersion"],
                    resources=[bucket.arn_for_objects(f"{DELTA_PREFIX}/*")]))
                uc_role.add_to_policy(iam.PolicyStatement(
                    actions=["s3:ListBucket", "s3:GetBucketLocation"], resources=[bucket.bucket_arn],
                    conditions={"StringLike": {"s3:prefix": [f"{DELTA_PREFIX}/*", DELTA_PREFIX, ""]}}))
                CfnOutput(self, "DatabricksRoleArn", value=uc_role.role_arn)

        definition = transform.next(validate).next(
            sfn.Choice(self, "Data conforms?")
            .when(sfn.Condition.boolean_equals("$.validation.conforms", True),
                  publish.next(sfn.Succeed(self, "Published")))
            .otherwise(dq_failed))

        pipeline = sfn.StateMachine(
            self, "LoadPipeline",
            definition_body=sfn.DefinitionBody.from_chainable(definition),
            timeout=Duration.hours(1),
            logs=sfn.LogOptions(destination=log_group("LoadPipeline"), level=sfn.LogLevel.ERROR),
            tracing_enabled=False)

        # Run the pipeline on deploy, and again whenever the data, ontology, shapes or mapping
        # code change. Fire-and-forget: the deploy does not wait for the load to finish.
        if auto_load:
            digest = source_hash(raw_data_dir, ROOT / "ontology", ROOT / "reference",
                                 ROOT / "shapes", ROOT / "fleet_kg", ROOT / "glue")
            call = cr.AwsSdkCall(
                service="SFN", action="startExecution",
                parameters={"stateMachineArn": pipeline.state_machine_arn,
                            "input": json.dumps({"trigger": "cdk-deploy", "sourceHash": digest})},
                physical_resource_id=cr.PhysicalResourceId.of(f"load-{digest}"))
            start = cr.AwsCustomResource(
                self, "StartLoadOnDeploy", on_create=call, on_update=call,
                policy=cr.AwsCustomResourcePolicy.from_statements([iam.PolicyStatement(
                    actions=["states:StartExecution"], resources=[pipeline.state_machine_arn])]),
                install_latest_aws_sdk=False)
            start.node.add_dependency(writer, admin, rdf_tools, *deployments)

        # ---------------------------------------------------------------- exports
        self.vpc = vpc
        self.isolated_subnets = isolated.subnets
        self.client_sg = client_sg
        self.neptune_sg = neptune_sg
        self.cluster = cluster
        self.writer = writer
        self.cluster_data_arn = cluster_data_arn
        self.loader_role = loader_role
        self.bucket = bucket
        self.core_asset_path = core_code
        self.rdf_asset_path = rdf_code

        CfnOutput(self, "StateMachineArn", value=pipeline.state_machine_arn)
        CfnOutput(self, "AdminFunctionName", value=admin.function_name)
        CfnOutput(self, "RdfToolsFunctionName", value=rdf_tools.function_name)
        CfnOutput(self, "DataBucketName", value=bucket.bucket_name)
        CfnOutput(self, "NeptuneEndpoint", value=cluster.attr_endpoint)
        CfnOutput(self, "ValidationReport", value=f"s3://{bucket.bucket_name}/reports/latest.json")
