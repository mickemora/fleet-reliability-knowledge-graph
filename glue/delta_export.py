"""AWS Glue job: write the ontology-shaped staging rows as Delta Lake tables.

The rows and the schema document are produced by the rdf-tools Lambda (fleet_kg/lakehouse.py)
from the same SHACL-validated RDF that is loaded into Neptune. This job only does what needs
Spark: read each table's JSON Lines with an explicit schema and overwrite its Delta table.

Job parameters: --bucket, --staging_prefix (lakehouse/staging), --delta_prefix (lakehouse/delta)
Glue enables Delta Lake through --datalake-formats delta and the --conf settings in the stack.
"""

import json
import re
import sys

import boto3
from awsglue.utils import getResolvedOptions
from pyspark.sql import SparkSession
from pyspark.sql import types as T

args = getResolvedOptions(sys.argv, ["bucket", "staging_prefix", "delta_prefix"])
bucket, staging, delta = args["bucket"], args["staging_prefix"].strip("/"), args["delta_prefix"].strip("/")

spark = SparkSession.builder.getOrCreate()
doc = json.loads(boto3.client("s3").get_object(
    Bucket=bucket, Key=f"{staging}/_schema.json")["Body"].read())


def spark_type(name: str):
    if name.startswith("DECIMAL"):
        precision, scale = map(int, re.findall(r"\d+", name))
        return T.DecimalType(precision, scale)
    if name.startswith("ARRAY<"):
        return T.ArrayType(spark_type(name[6:-1]))
    return {"STRING": T.StringType(), "BIGINT": T.LongType(), "DATE": T.DateType(),
            "BOOLEAN": T.BooleanType(), "DOUBLE": T.DoubleType()}[name]


for table in doc["tables"]:
    schema = T.StructType([T.StructField(c["name"], spark_type(c["type"]), True)
                           for c in table["columns"]])
    df = (spark.read.schema(schema).option("dateFormat", "yyyy-MM-dd")
          .json(f"s3://{bucket}/{staging}/{table['name']}.jsonl"))
    (df.write.format("delta").mode("overwrite").option("overwriteSchema", "true")
       .option("userMetadata", f"ontology class {table['ontologyClass']}")
       .save(f"s3://{bucket}/{delta}/{table['name']}"))
    print(f"{table['name']}: {df.count()} rows")
