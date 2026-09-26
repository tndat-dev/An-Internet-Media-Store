data "oci_core_services" "all_services" {
  filter {
    name   = "name"
    values = ["All .* Services In Oracle Services Network"]
    regex  = true
  }
}

resource "oci_core_vcn" "oe" {
  compartment_id = oci_identity_compartment.common_network.id
  cidr_blocks    = [var.vcn_cidr]
  display_name   = "${local.prefix}-vcn"
  dns_label      = local.dns
  freeform_tags  = local.common_tags
}

resource "oci_core_nat_gateway" "oe" {
  compartment_id = oci_identity_compartment.common_network.id
  vcn_id         = oci_core_vcn.oe.id
  display_name   = "${local.prefix}-natgw"
  freeform_tags  = local.common_tags
}

resource "oci_core_service_gateway" "oe" {
  compartment_id = oci_identity_compartment.common_network.id
  vcn_id         = oci_core_vcn.oe.id
  display_name   = "${local.prefix}-sgw"
  freeform_tags  = local.common_tags

  services {
    service_id = data.oci_core_services.all_services.services[0].id
  }
}

resource "oci_core_route_table" "spoke" {
  compartment_id = oci_identity_compartment.common_network.id
  vcn_id         = oci_core_vcn.oe.id
  display_name   = "rt-${local.prefix}-spoke"
  freeform_tags  = local.common_tags

  route_rules {
    destination       = data.oci_core_services.all_services.services[0].cidr_block
    destination_type  = "SERVICE_CIDR_BLOCK"
    network_entity_id = oci_core_service_gateway.oe.id
    description       = "OCI services through Service Gateway"
  }

  route_rules {
    destination       = var.hub_vcn_cidr
    destination_type  = "CIDR_BLOCK"
    network_entity_id = var.drg_id
    description       = "Shared Hub through DRG"
  }

  route_rules {
    destination       = "0.0.0.0/0"
    destination_type  = "CIDR_BLOCK"
    network_entity_id = oci_core_nat_gateway.oe.id
    description       = "Internet egress through the OE-local NAT Gateway"
  }
}

resource "oci_core_security_list" "private" {
  compartment_id = oci_identity_compartment.common_network.id
  vcn_id         = oci_core_vcn.oe.id
  display_name   = "sl-${local.prefix}-private"
  freeform_tags  = local.common_tags

  ingress_security_rules {
    protocol    = "1"
    source      = var.vcn_cidr
    description = "ICMP path MTU discovery inside the OE VCN"
    icmp_options {
      type = 3
      code = 4
    }
  }

  egress_security_rules {
    protocol    = "all"
    destination = "0.0.0.0/0"
    description = "Workload egress; NSGs apply workload-specific restrictions"
  }
}

resource "oci_core_subnet" "private" {
  for_each = local.subnet_cidrs

  compartment_id             = oci_identity_compartment.common_network.id
  vcn_id                     = oci_core_vcn.oe.id
  cidr_block                 = each.value
  display_name               = "sn-${local.prefix}-${each.key}"
  dns_label                  = substr("${local.dns}${each.key}", 0, 15)
  prohibit_internet_ingress  = true
  prohibit_public_ip_on_vnic = true
  route_table_id             = oci_core_route_table.spoke.id
  security_list_ids          = [oci_core_security_list.private.id]
  freeform_tags              = local.common_tags
}

resource "oci_core_network_security_group" "workload" {
  for_each = toset(["api", "workers", "pods", "lb"])

  compartment_id = oci_identity_compartment.common_network.id
  vcn_id         = oci_core_vcn.oe.id
  display_name   = "nsg-${local.prefix}-${each.key}"
  freeform_tags  = local.common_tags
}

resource "oci_core_network_security_group_security_rule" "internal_ingress" {
  for_each = oci_core_network_security_group.workload

  network_security_group_id = each.value.id
  direction                 = "INGRESS"
  protocol                  = "all"
  source                    = var.vcn_cidr
  source_type               = "CIDR_BLOCK"
  description               = "Internal traffic inside the OE VCN"
}

resource "oci_core_network_security_group_security_rule" "egress" {
  for_each = oci_core_network_security_group.workload

  network_security_group_id = each.value.id
  direction                 = "EGRESS"
  protocol                  = "all"
  destination               = "0.0.0.0/0"
  destination_type          = "CIDR_BLOCK"
  description               = "Egress controlled by route tables and downstream controls"
}

resource "oci_core_network_security_group_security_rule" "lb_from_hub_http" {
  network_security_group_id = oci_core_network_security_group.workload["lb"].id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = var.hub_vcn_cidr
  source_type               = "CIDR_BLOCK"
  description               = "HTTP from the shared Hub"

  tcp_options {
    destination_port_range {
      min = 80
      max = 80
    }
  }
}

resource "oci_core_network_security_group_security_rule" "lb_from_hub_https" {
  network_security_group_id = oci_core_network_security_group.workload["lb"].id
  direction                 = "INGRESS"
  protocol                  = "6"
  source                    = var.hub_vcn_cidr
  source_type               = "CIDR_BLOCK"
  description               = "HTTPS from the shared Hub"

  tcp_options {
    destination_port_range {
      min = 443
      max = 443
    }
  }
}

resource "oci_core_drg_attachment" "oe" {
  drg_id             = var.drg_id
  drg_route_table_id = var.drg_route_table_id
  display_name       = "att-${local.prefix}"
  freeform_tags      = local.common_tags

  network_details {
    id             = oci_core_vcn.oe.id
    type           = "VCN"
    vcn_route_type = "VCN_CIDRS"
  }
}

resource "oci_core_drg_route_table_route_rule" "hub_return_to_oe" {
  count = var.hub_drg_route_table_id == null ? 0 : 1

  drg_route_table_id         = var.hub_drg_route_table_id
  destination                = var.vcn_cidr
  destination_type           = "CIDR_BLOCK"
  next_hop_drg_attachment_id = oci_core_drg_attachment.oe.id
}

check "vcn_does_not_overlap_hub" {
  assert {
    condition     = cidrhost(var.vcn_cidr, 0) != cidrhost(var.hub_vcn_cidr, 0)
    error_message = "vcn_cidr không được chồng lấn hub_vcn_cidr."
  }
}
