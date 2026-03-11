terraform {
  required_version = ">= 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

locals {
  name_prefix = "sp-${substr(var.tenant_id, 0, 8)}-${substr(var.environment_id, 0, 8)}"

  # Strip the ARN prefix so IAM condition keys become:
  # oidc.eks.<region>.amazonaws.com/id/<id>:sub and :aud
  # oidc_provider_arn example:
  # arn:aws:iam::123456789012:oidc-provider/oidc.eks.us-east-1.amazonaws.com/id/ABCDEF
  oidc_provider_bare = try(element(split("oidc-provider/", var.oidc_provider_arn), 1), var.oidc_provider_arn)
}

# ---------------------------------------------------------------------------
# EMR on EKS namespace
# ---------------------------------------------------------------------------

resource "aws_emrcontainers_virtual_cluster" "this" {
  name = local.name_prefix

  container_provider {
    id   = var.eks_cluster_name
    type = "EKS"

    info {
      eks_info {
        namespace = var.eks_namespace
      }
    }
  }
}

# ---------------------------------------------------------------------------
# EMR execution role
# ---------------------------------------------------------------------------

data "aws_iam_policy_document" "emr_execution_trust" {
  statement {
    sid     = "AllowEMRonEKSServiceAccount"
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated"
      identifiers = [var.oidc_provider_arn]
    }

    condition {
      test     = "StringLike"
      variable = "${local.oidc_provider_bare}:sub"
      values   = ["system:serviceaccount:${var.eks_namespace}:emr-containers-sa-*"]
    }

    condition {
      test     = "StringEquals"
      variable = "${local.oidc_provider_bare}:aud"
      values   = ["sts.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "emr_execution" {
  name               = "${local.name_prefix}-emr-exec"
  assume_role_policy = data.aws_iam_policy_document.emr_execution_trust.json

  tags = {
    "sparkpilot:role" = "emr-execution"
  }
}

data "aws_iam_policy_document" "emr_execution_policy" {
  statement {
    sid    = "AllowS3Access"
    effect = "Allow"
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:ListBucket",
      "s3:GetBucketLocation",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "AllowCloudWatchLogs"
    effect = "Allow"
    actions = [
      "logs:CreateLogGroup",
      "logs:CreateLogStream",
      "logs:PutLogEvents",
      "logs:DescribeLogGroups",
      "logs:DescribeLogStreams",
    ]
    resources = ["*"]
  }

  statement {
    sid    = "AllowECRAccess"
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken",
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
    ]
    resources = ["*"]
  }
}

resource "aws_iam_role_policy" "emr_execution_inline" {
  name   = "${local.name_prefix}-emr-exec-policy"
  role   = aws_iam_role.emr_execution.id
  policy = data.aws_iam_policy_document.emr_execution_policy.json
}
