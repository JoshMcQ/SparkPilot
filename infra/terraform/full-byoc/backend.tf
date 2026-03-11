terraform {
  backend "s3" {
    # These values are intentionally left as empty defaults so that the backend
    # block is valid HCL.  The SparkPilot orchestrator initialises Terraform
    # with `-backend-config` flags that override all of these values:
    #
    #   terraform init \
    #     -backend-config="bucket=<tf-state-bucket>" \
    #     -backend-config="key=sparkpilot/full-byoc/<tenant_id>/<env_id>/terraform.tfstate" \
    #     -backend-config="region=<aws_region>" \
    #     -backend-config="role_arn=<customer_role_arn>" \
    #     -reconfigure
    #
    # Do NOT hard-code bucket names or account IDs here.

    bucket         = "CONFIGURE_VIA_BACKEND_CONFIG"
    key            = "sparkpilot/full-byoc/bootstrap/terraform.tfstate"
    region         = "us-east-1"
    encrypt        = true
    use_path_style = false
  }
}
