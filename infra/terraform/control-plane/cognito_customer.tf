# Customer Cognito user pool — used by tenant admins / customer end-users.
#
# The existing "SparkPilotDevUsers" pool (us-east-1_m6veGu9gU) is unmanaged
# (created outside Terraform) and serves as the internal-admin pool. Its
# clean internal-admin app client is also declared below so both audiences
# are visible in code; we reference the unmanaged pool by literal ID rather
# than importing the pool itself, so we own only the new client and not the
# pool's full lifecycle.

resource "aws_cognito_user_pool" "customer" {
  name = "sparkpilot-customer-pool"

  username_attributes      = ["email"]
  auto_verified_attributes = ["email"]

  password_policy {
    minimum_length    = 12
    require_lowercase = true
    require_uppercase = true
    require_numbers   = true
    require_symbols   = true
  }

  admin_create_user_config {
    allow_admin_create_user_only = true
  }

  account_recovery_setting {
    recovery_mechanism {
      name     = "verified_email"
      priority = 1
    }
  }

  mfa_configuration = "OPTIONAL"
  software_token_mfa_configuration {
    enabled = true
  }

  email_configuration {
    email_sending_account = "COGNITO_DEFAULT"
  }

  deletion_protection = "INACTIVE"

  tags = {
    Component = "control-plane"
    Purpose   = "customer-auth"
    ManagedBy = "terraform"
  }
}

resource "aws_cognito_user_pool_domain" "customer" {
  domain       = "sparkpilot-customers"
  user_pool_id = aws_cognito_user_pool.customer.id
}

resource "aws_cognito_user_pool_client" "customer_spa" {
  name         = "sparkpilot-customer-spa-client"
  user_pool_id = aws_cognito_user_pool.customer.id

  generate_secret = false

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["email", "openid", "profile"]

  callback_urls = ["https://app.sparkpilot.cloud/auth/callback"]
  logout_urls   = ["https://app.sparkpilot.cloud/"]

  supported_identity_providers = ["COGNITO"]

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}

# New internal-admin app client on the unmanaged SparkPilotDevUsers pool.
# The pool itself is not imported into Terraform; we own only this client.
# Existing legacy clients on this pool (sparkpilot-dev-client,
# sparkpilot-staging-public-client) are intentionally left alone for a
# post-launch cleanup PR.
resource "aws_cognito_user_pool_client" "internal_admin" {
  name         = "sparkpilot-internal-admin-client"
  user_pool_id = "us-east-1_m6veGu9gU"

  generate_secret = false

  allowed_oauth_flows                  = ["code"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = ["email", "openid", "profile"]

  callback_urls = ["https://app.sparkpilot.cloud/auth/callback"]
  logout_urls   = ["https://app.sparkpilot.cloud/"]

  supported_identity_providers = ["COGNITO"]

  prevent_user_existence_errors = "ENABLED"
  enable_token_revocation       = true

  explicit_auth_flows = [
    "ALLOW_USER_SRP_AUTH",
    "ALLOW_REFRESH_TOKEN_AUTH",
  ]

  access_token_validity  = 60
  id_token_validity      = 60
  refresh_token_validity = 30
  token_validity_units {
    access_token  = "minutes"
    id_token      = "minutes"
    refresh_token = "days"
  }
}
