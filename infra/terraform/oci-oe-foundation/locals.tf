locals {
  prefix = join("-", compact([var.oe_code, var.name_suffix]))
  dns    = substr(replace(local.prefix, "-", ""), 0, 13)

  subnet_cidrs = {
    api     = cidrsubnet(var.vcn_cidr, 8, 0)
    workers = cidrsubnet(var.vcn_cidr, 8, 1)
    lb      = cidrsubnet(var.vcn_cidr, 8, 2)
    bastion = cidrsubnet(var.vcn_cidr, 12, 48)
    pods    = cidrsubnet(var.vcn_cidr, 4, 1)
  }

  common_tags = merge(var.freeform_tags, {
    OperatingEntity = var.oe_code
    Environment     = "development"
  })
}
