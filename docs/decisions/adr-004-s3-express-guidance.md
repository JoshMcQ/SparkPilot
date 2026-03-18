# ADR-004: S3 Express One Zone — Guidance and Validation

**Status:** Accepted
**Date:** 2026-03-17
**Deciders:** SparkPilot product and engineering leadership
**Issues:** #57

---

## Problem

Amazon S3 Express One Zone is a high-performance, single-AZ storage class optimized for low-latency, high-throughput workloads. It is well-suited for Spark shuffle storage on EMR on EKS — but only under specific conditions. Misconfigured S3 Express usage can result in cross-AZ charges, unexpected latency, and cost model breakdowns.

This ADR defines when to use S3 Express One Zone for Spark shuffle, documents incompatibilities and caveats, and establishes a preflight validation hook to catch common misconfigurations.

---

## When to Use S3 Express One Zone

S3 Express One Zone is recommended for Spark workloads on EMR on EKS when **all** of the following conditions are met:

1. **Shuffle volume exceeds 1TB per job.** At lower shuffle volumes, the throughput benefit does not offset the higher storage cost ($0.16/GB-month vs $0.023/GB-month for standard S3).
2. **Pods are pinned to the same AZ as the S3 Express bucket.** S3 Express buckets are single-AZ. Cross-AZ access negates the latency benefit and incurs inter-AZ data transfer charges. Node affinity must be configured to enforce co-location.
3. **The workload is shuffle-intensive.** Jobs with high shuffle ratios (wide transformations, aggregations, large joins) benefit most. Workloads that read/write primarily from standard S3 see minimal benefit.
4. **Latency-sensitive pipelines.** S3 Express One Zone delivers single-digit millisecond latency vs. 100ms+ for standard S3. Pipelines with tight SLA requirements benefit from reduced shuffle I/O latency.
5. **Graviton (ARM) instance types are preferred.** S3 Express One Zone delivers the best throughput-per-dollar on Graviton instances. SparkPilot environments configured with `instance_architecture: arm64` or `mixed` are good candidates.

---

## Incompatibilities and Caveats

### AZ co-location is mandatory

S3 Express buckets are bound to a single Availability Zone. If Spark executor pods run in a different AZ from the S3 Express bucket, every shuffle read/write crosses an AZ boundary, incurring additional latency and inter-AZ transfer costs. This eliminates the cost and performance benefits of S3 Express.

**SparkPilot mitigation:** Set `spark.kubernetes.node.selector.topology.kubernetes.io/zone` in your Spark configuration to pin all pods to the same AZ as the bucket. SparkPilot's preflight check (`_check_s3_express_config`) will emit a warning if S3 Express is configured without this node selector.

### S3 Express uses a distinct URI scheme

S3 Express buckets use the `s3express://` URI scheme, not `s3://`. Spark must be explicitly configured to use the S3 Express filesystem implementation:

```
spark.hadoop.fs.s3express.impl=com.amazon.ws.emr.hadoop.fs.EmrFileSystem
```

Standard S3A or EMR filesystem configurations do not route `s3express://` URIs correctly. Ensure your job's `spark.sql.shuffle.partitions` output path and shuffle spill path reference `s3express://` URIs.

### Not compatible with S3 versioning or cross-region replication

S3 Express One Zone buckets do not support:
- **Object versioning.** Do not use S3 Express buckets as the target for versioned data lakes.
- **Cross-region replication (CRR).** S3 Express buckets cannot be replicated to other regions. Do not use S3 Express for data that requires geographic redundancy.
- **S3 Lifecycle policies.** TTL-based cleanup of shuffle data must be managed via bucket deletion or explicit object deletion after the job completes.

### Cost model: only cost-effective at high shuffle volumes

| Storage class | Cost | Best for |
|---|---|---|
| S3 Standard | $0.023/GB-month | General-purpose, replicated |
| S3 Express One Zone | $0.16/GB-month | High-throughput shuffle, single-AZ |

S3 Express One Zone costs approximately 7x more per GB than standard S3. The cost model is only favorable when the reduced compute time from lower shuffle latency more than offsets the storage premium. As a rule of thumb, jobs that spend >20% of their wall-clock time on shuffle I/O are strong candidates; jobs with <10% shuffle time are not.

### Single-AZ durability

S3 Express One Zone stores data redundantly within a single AZ. It does not provide the 11-nines durability of S3 Standard (which replicates across three AZs). Do not use S3 Express for output data that must survive an AZ failure. Use it only for ephemeral shuffle data that is regenerated if lost.

---

## Golden-Path: `s3express_shuffle` Preset

For teams adopting S3 Express shuffle, SparkPilot provides the following golden-path configuration preset. Add these keys to your job's `spark_conf` in the SparkPilot run submission:

```json
{
  "spark.hadoop.fs.s3express.impl": "com.amazon.ws.emr.hadoop.fs.EmrFileSystem",
  "spark.local.dir": "/tmp/spark-shuffle",
  "spark.kubernetes.node.selector.topology.kubernetes.io/zone": "<your-az>",
  "spark.sql.shuffle.partitions": "200",
  "spark.shuffle.service.enabled": "false",
  "spark.dynamicAllocation.shuffleTracking.enabled": "true"
}
```

Replace `<your-az>` with the AZ of your S3 Express bucket (e.g., `us-east-1a`).

**Checkpoint:** Before enabling S3 Express shuffle in production, verify the following with SparkPilot preflight:

1. `spark.kubernetes.node.selector.topology.kubernetes.io/zone` is set and matches the bucket AZ.
2. The `s3express://` URI scheme is used in your shuffle output path.
3. The SparkPilot preflight check `s3_express_config` returns `status: pass`.

---

## Preflight Validation

A preflight check (`_check_s3_express_config`) is implemented in `src/sparkpilot/services/preflight.py` and wired into the preflight pipeline. The check:

- Scans `spark_conf` keys and values for `s3express` references.
- If S3 Express is detected, verifies that `spark.kubernetes.node.selector.topology.kubernetes.io/zone` is also set.
- Emits `status: warn` with an actionable message if AZ affinity is missing.
- Returns `status: pass` if S3 Express is not configured (check is skipped cleanly).
- Returns `status: pass` if S3 Express is configured with the required AZ affinity selector.

The check is a **warning** (not a block) because some environments pin AZ affinity at the node group level rather than in Spark conf. The warning prompts operators to verify co-location is enforced by their infrastructure if not by Spark conf.

---

## Acceptance Criteria

- [x] When-to-use guidance is documented with quantitative thresholds (>1TB shuffle, >20% shuffle time)
- [x] All incompatibilities are documented (AZ co-location, URI scheme, no versioning/CRR, cost model)
- [x] Cost comparison table is included
- [x] Golden-path `s3express_shuffle` preset is defined
- [x] Preflight check `_check_s3_express_config` is implemented and wired into the pipeline
- [x] Tests for the preflight check are passing
