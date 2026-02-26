# SparkPilot Security Overview (Template)

Version:
Date:
Contact:

## 1. Architecture Overview

SparkPilot is a BYOC control plane. Customer data processing remains in the customer AWS account.  
SparkPilot control plane stores operational metadata only (tenants, environment config, run states, audit records).  
Cross-account access is performed through STS `AssumeRole` with `ExternalId`.

Diagram:

`[SparkPilot Control Plane] --STS AssumeRole--> [Customer AWS Account: EKS + EMR + S3 + CloudWatch]`

## 2. Cross-Account Access Model

- One IAM role per customer account.
- SparkPilot assumes role using short-lived credentials.
- No long-lived customer credentials are stored by SparkPilot.
- Access is scoped to explicit actions/resources in customer-provided template.
- Runtime access uses `emr-containers`, `logs`, and `iam:PassRole` only for job execution path (BYOC-Lite mode).

## 3. IAM Permission Inventory

| Action | Why needed | Resource scope | Condition |
|---|---|---|---|
| emr-containers:CreateVirtualCluster | Create EMR virtual cluster in customer account | `*` | `aws:RequestTag/sparkpilot:managed=true` |
| emr-containers:DeleteVirtualCluster | Remove managed virtual cluster | same | tag-scoped |
| emr-containers:DescribeVirtualCluster | Read virtual cluster state | same | tag-scoped |
| emr-containers:ListVirtualClusters | Enumerate managed clusters | same | tag-scoped |
| emr-containers:StartJobRun | Submit Spark job | same | tag-scoped |
| emr-containers:CancelJobRun | Cancel Spark job | same | tag-scoped |
| emr-containers:DescribeJobRun | Poll run status | same | tag-scoped |
| emr-containers:ListJobRuns | Enumerate runs | same | tag-scoped |
| logs:CreateLogGroup | Initialize deterministic SparkPilot log groups | `arn:aws:logs:*:<acct>:log-group:/sparkpilot/*` | none |
| logs:PutRetentionPolicy | Set retention | same | none |
| logs:DescribeLogGroups | Discover log groups | same | none |
| logs:DescribeLogStreams | Discover log streams | same | none |
| logs:FilterLogEvents | Proxy logs in API/UI | same | none |
| iam:PassRole | Pass EMR execution role on job submission | `arn:aws:iam::<acct>:role/SparkPilotEmrExecution*` | `iam:PassedToService=emr-containers.amazonaws.com` |

## 4. Data Handling

SparkPilot stores:
- Tenant metadata
- Environment and job configuration
- Run lifecycle state
- Audit events

SparkPilot does not store:
- Customer Spark dataset payloads
- Customer S3 data outputs
- Persistent copies of raw application logs

Log retrieval is proxied from customer CloudWatch to client response and is not persisted in SparkPilot control plane storage.

## 5. Encryption

- In transit: TLS 1.2+ for API access.
- At rest (control plane): encrypted database storage.
- At rest (customer data plane): customer-managed encryption controls for S3/EBS/KMS remain in customer account.

## 6. Audit and Incident Response

- Mutating operations are audited with actor, action, timestamp, source IP, entity, and metadata.
- Security or reliability incidents are triaged by severity:
  - P1 response target: 4 hours
  - P2 response target: 24 hours
- Incident communication uses predefined contact channels and update cadence.
