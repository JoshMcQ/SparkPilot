"""Tests for the _check_s3_express_config preflight check (ADR-004)."""

import sparkpilot.services.preflight as preflight


def test_s3_express_warns_without_az_affinity() -> None:
    """S3 Express URI in spark_conf without AZ node selector should return status=warn."""
    spark_conf = {
        "spark.hadoop.fs.s3express.impl": "com.amazon.ws.emr.hadoop.fs.EmrFileSystem",
        "spark.sql.shuffle.partitions": "200",
    }
    result = preflight._check_s3_express_config(spark_conf)
    assert result["status"] == "warn"
    assert result["check"] == "s3_express_config"
    assert len(result["issues"]) == 1
    assert "AZ affinity" in result["issues"][0] or "node selector" in result["issues"][0]


def test_s3_express_warns_without_az_affinity_via_value() -> None:
    """S3 Express detected via value reference (output path) also triggers the check."""
    spark_conf = {
        "spark.local.dir": "/tmp/spark-shuffle",
        "spark.sql.warehouse.dir": "s3express://my-bucket--use1-az1--x-s3/warehouse",
    }
    result = preflight._check_s3_express_config(spark_conf)
    assert result["status"] == "warn"
    assert result["check"] == "s3_express_config"
    assert len(result["issues"]) >= 1


def test_s3_express_passes_with_az_affinity() -> None:
    """S3 Express configured with AZ node selector should return status=pass."""
    spark_conf = {
        "spark.hadoop.fs.s3express.impl": "com.amazon.ws.emr.hadoop.fs.EmrFileSystem",
        "spark.kubernetes.node.selector.topology.kubernetes.io/zone": "us-east-1a",
        "spark.sql.shuffle.partitions": "200",
    }
    result = preflight._check_s3_express_config(spark_conf)
    assert result["status"] == "pass"
    assert result["check"] == "s3_express_config"


def test_s3_express_skips_when_not_configured() -> None:
    """No s3express in spark_conf should return status=pass without issues key populated."""
    spark_conf = {
        "spark.executor.memory": "4g",
        "spark.executor.cores": "2",
        "spark.sql.shuffle.partitions": "200",
    }
    result = preflight._check_s3_express_config(spark_conf)
    assert result["status"] == "pass"
    assert result["check"] == "s3_express_config"


def test_s3_express_skips_on_empty_spark_conf() -> None:
    """Empty spark_conf should return status=pass (nothing to check)."""
    result = preflight._check_s3_express_config({})
    assert result["status"] == "pass"
    assert result["check"] == "s3_express_config"


def test_s3_express_case_insensitive_detection() -> None:
    """S3Express detection should be case-insensitive."""
    spark_conf = {
        "spark.shuffle.output": "S3EXPRESS://my-bucket--use1-az1--x-s3/shuffle",
    }
    result = preflight._check_s3_express_config(spark_conf)
    # Detected (case-insensitive), no AZ affinity set → warn
    assert result["status"] == "warn"
