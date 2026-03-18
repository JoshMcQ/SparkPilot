"""Reference Structured Streaming workload for SparkPilot validation.

This job intentionally runs until externally cancelled. It can be used to
validate long-running run lifecycle behavior (health heartbeat, logs, cancel).
"""

from __future__ import annotations

from pyspark.sql import SparkSession


def main() -> None:
    spark = SparkSession.builder.appName("sparkpilot-structured-streaming-reference").getOrCreate()
    spark.sparkContext.setLogLevel("INFO")

    # Synthetic infinite stream source suitable for validation workloads.
    stream_df = (
        spark.readStream
        .format("rate")
        .option("rowsPerSecond", 5)
        .load()
    )

    query = (
        stream_df.writeStream
        .format("console")
        .option("truncate", "false")
        .option("numRows", 20)
        .option("checkpointLocation", "/tmp/sparkpilot-streaming-checkpoint")
        .start()
    )

    query.awaitTermination()


if __name__ == "__main__":
    main()

