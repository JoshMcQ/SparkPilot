# Outputs are defined in main.tf alongside the module declarations so that
# conditional expressions can reference module outputs directly.
#
# The key outputs consumed by the SparkPilot provisioning worker are:
#   - eks_cluster_arn       (from provisioning_eks + pass-through in provisioning_emr)
#   - emr_virtual_cluster_id (from provisioning_emr)
#
# See main.tf for the full output block definitions.
