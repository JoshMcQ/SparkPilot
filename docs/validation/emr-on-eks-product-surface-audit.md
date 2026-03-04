# EMR-on-EKS Product Surface Audit (R18)

Date: March 3, 2026  
Issue: [R18](https://github.com/JoshMcQ/SparkPilot/issues/31)

## Scope

This audit maps EMR-on-EKS capabilities to current SparkPilot status (`built`, `planned`, `not_covered`) and ties each planned/missing item to a GitHub issue.

## Evidence Collected

1. EMR-on-EKS Development Guide crawl:
   - `artifacts/r18-devguide-pages-20260303.tsv` (275 pages discovered from the tutorials index and linked sections)
2. EMR Containers API operations inventory:
   - `https://docs.aws.amazon.com/emr-on-eks/latest/APIReference/API_Operations.html`
3. AWS Big Data blog + announcement sources (last 2 years relevant to EMR on EKS):
   - https://aws.amazon.com/blogs/big-data/centralize-apache-spark-observability-on-amazon-emr-on-eks-with-external-spark-history-server/
   - https://aws.amazon.com/blogs/big-data/use-batch-processing-gateway-to-automate-job-management-in-multi-cluster-amazon-emr-on-eks-environments/
   - https://aws.amazon.com/about-aws/whats-new/2025/04/amazon-emr-eks-native-support-ebs-gp3-storage-volumes/
   - https://aws.amazon.com/about-aws/whats-new/2024/12/amazon-emr-eks-spark-operator/
4. DoEKS blueprint inventory:
   - `artifacts/r18-doeks-sitemap-emr-related-20260303.txt` (50 EMR/Spark-related pages from sitemap)
   - Includes blueprints such as:
     - https://awslabs.github.io/data-on-eks/docs/blueprints/amazon-emr-on-eks
     - https://awslabs.github.io/data-on-eks/docs/blueprints/amazon-emr-on-eks/emr-eks-karpenter
     - https://awslabs.github.io/data-on-eks/docs/blueprints/data-analytics/spark-operator-yunikorn

## Key Source Pages Used for Capability Mapping

1. Core + setup:
   - https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/emr-eks.html
   - https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/setting-up.html
   - https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/virtual-cluster.html
2. Identity/security:
   - https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/setting-up-enable-IAM.html
   - https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/setting-up-enable-IAM-service-accounts.html
   - https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/security-best-practices.html
3. Spark/Flink/operators/scheduling:
   - https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/spark-operator.html
   - https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/run-flink-jobs.html
   - https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/tutorial-yunikorn.html
4. Pod templates + customization:
   - https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/pod-templates.html
   - https://docs.aws.amazon.com/emr/latest/EMR-on-EKS-DevelopmentGuide/docker-custom-images-multi-architecture.html
5. API surface:
   - https://docs.aws.amazon.com/emr-on-eks/latest/APIReference/API_Operations.html

## Mapping Artifact

Full matrix:

- [emr-on-eks-product-surface-matrix.csv](../../docs/validation/emr-on-eks-product-surface-matrix.csv)

## Coverage Summary

1. Built and validated in SparkPilot now:
   - BYOC-Lite virtual cluster provisioning, prerequisite checks, run submission, logs, cancellation/retry, real-AWS isolation and smoke evidence.
2. Planned in active roadmap issues:
   - Spot/Graviton, cost chargeback, golden paths, RBAC/policy, orchestrator integrations, diagnostics, Karpenter, YuniKorn, Spark UI history integration, e2e/load.
3. Gaps found by this audit and added as new issues:
   - [R22](https://github.com/JoshMcQ/SparkPilot/issues/51): EMR Job Template management
   - [R23](https://github.com/JoshMcQ/SparkPilot/issues/52): Pod Identity + EKS access entries onboarding path
   - [R24](https://github.com/JoshMcQ/SparkPilot/issues/53): EMR SecurityConfiguration support
   - [R25](https://github.com/JoshMcQ/SparkPilot/issues/54): Flink-on-EMR-on-EKS scope decision and implementation path
   - [R26](https://github.com/JoshMcQ/SparkPilot/issues/55): Vertical autoscaling operator support decision/integration
   - [R27](https://github.com/JoshMcQ/SparkPilot/issues/56): Apache Livy support strategy
   - [R28](https://github.com/JoshMcQ/SparkPilot/issues/57): S3 Express One Zone workload guidance and guardrails

## Findings

1. Current SparkPilot tracks the core Spark submit path (`StartJobRun`) but does not yet expose several first-class EMR control-plane entities (`JobTemplate`, `SecurityConfiguration`, `ManagedEndpoint`) as product resources.
2. EMR docs now clearly support Pod Identity / access-entry style setup in addition to IRSA; SparkPilot should support and prefer the modern path.
3. EMR-on-EKS documentation now spans Spark + Flink + operators + autoscaling; SparkPilot roadmap needed explicit Flink scope governance to avoid accidental product drift.
