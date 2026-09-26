resource "oci_logging_log_group" "network" {
  compartment_id = oci_identity_compartment.common_network.id
  display_name   = "log-${local.prefix}-network"
  description    = "VCN flow logs for ${local.prefix}"
  freeform_tags  = local.common_tags
}

resource "oci_logging_log" "subnet_flow" {
  for_each = oci_core_subnet.private

  display_name       = "flow-${local.prefix}-${each.key}"
  log_group_id       = oci_logging_log_group.network.id
  log_type           = "SERVICE"
  is_enabled         = true
  retention_duration = 30
  freeform_tags      = local.common_tags

  configuration {
    compartment_id = oci_identity_compartment.common_network.id
    source {
      category    = "all"
      resource    = each.value.id
      service     = "flowlogs"
      source_type = "OCISERVICE"
    }
  }
}
