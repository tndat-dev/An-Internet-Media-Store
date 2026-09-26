resource "oci_identity_group" "oe_admins" {
  count = var.create_iam_group ? 1 : 0

  compartment_id = var.tenancy_ocid
  name           = "grp-${local.prefix}-admins"
  description    = "Administrators restricted to ${local.prefix}"
  freeform_tags  = local.common_tags
}

resource "oci_identity_policy" "oe_admins" {
  count = var.create_iam_group ? 1 : 0

  compartment_id = var.landing_zone_compartment_id
  name           = "pol-${local.prefix}-admins"
  description    = "Permissions for grp-${local.prefix}-admins inside its OE only"
  statements = [
    "Allow group ${oci_identity_group.oe_admins[0].name} to inspect compartments in compartment id ${var.landing_zone_compartment_id}",
    "Allow group ${oci_identity_group.oe_admins[0].name} to manage all-resources in compartment id ${oci_identity_compartment.oe.id}",
  ]
  freeform_tags = local.common_tags
}
