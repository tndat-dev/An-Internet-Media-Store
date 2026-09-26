resource "oci_identity_compartment" "oe" {
  compartment_id = var.landing_zone_compartment_id
  name           = "cmp-${local.prefix}"
  description    = "Operating Entity ${upper(var.oe_code)} managed by Terraform"
  enable_delete  = true
  freeform_tags  = local.common_tags

  lifecycle {
    precondition {
      condition     = var.deployment_acknowledgement == "CREATE-${upper(local.prefix)}"
      error_message = "deployment_acknowledgement không khớp. Giá trị yêu cầu: CREATE-${upper(local.prefix)}"
    }
  }
}

resource "oci_identity_compartment" "common" {
  compartment_id = oci_identity_compartment.oe.id
  name           = "cmp-${local.prefix}-common"
  description    = "Shared resources owned by ${upper(var.oe_code)}"
  enable_delete  = true
  freeform_tags  = local.common_tags
}

resource "oci_identity_compartment" "common_infra" {
  compartment_id = oci_identity_compartment.common.id
  name           = "cmp-${local.prefix}-common-infra"
  description    = "Shared infrastructure owned by ${upper(var.oe_code)}"
  enable_delete  = true
  freeform_tags  = local.common_tags
}

resource "oci_identity_compartment" "common_network" {
  compartment_id = oci_identity_compartment.common.id
  name           = "cmp-${local.prefix}-common-network"
  description    = "VCN, gateways and network controls for ${upper(var.oe_code)}"
  enable_delete  = true
  freeform_tags  = local.common_tags
}

resource "oci_identity_compartment" "development" {
  compartment_id = oci_identity_compartment.oe.id
  name           = "cmp-${local.prefix}-development"
  description    = "Development workloads for ${upper(var.oe_code)}"
  enable_delete  = true
  freeform_tags  = local.common_tags
}

resource "oci_identity_compartment" "sensitive_data" {
  compartment_id = oci_identity_compartment.development.id
  name           = "cmp-${local.prefix}-sensitive-data"
  description    = "Security Zone for sensitive data of ${upper(var.oe_code)}"
  enable_delete  = true
  freeform_tags  = local.common_tags
}
