output "compartment_ids" {
  description = "OCID của cây compartment vừa tạo."
  value = {
    oe             = oci_identity_compartment.oe.id
    common         = oci_identity_compartment.common.id
    common_infra   = oci_identity_compartment.common_infra.id
    common_network = oci_identity_compartment.common_network.id
    development    = oci_identity_compartment.development.id
    sensitive_data = oci_identity_compartment.sensitive_data.id
  }
}

output "network" {
  description = "Các OCID mạng dùng cho bước triển khai OKE/workload."
  value = {
    vcn_id             = oci_core_vcn.oe.id
    nat_gateway_id     = oci_core_nat_gateway.oe.id
    service_gateway_id = oci_core_service_gateway.oe.id
    drg_attachment_id  = oci_core_drg_attachment.oe.id
    route_table_id     = oci_core_route_table.spoke.id
    subnet_ids         = { for name, subnet in oci_core_subnet.private : name => subnet.id }
    nsg_ids            = { for name, nsg in oci_core_network_security_group.workload : name => nsg.id }
  }
}

output "iam_group_name" {
  description = "IAM group vận hành OE, hoặc null nếu không tạo."
  value       = try(oci_identity_group.oe_admins[0].name, null)
}

output "security_zone_id" {
  description = "Security Zone OCID, hoặc null nếu không bật."
  value       = try(oci_cloud_guard_security_zone.sensitive_data[0].id, null)
}
