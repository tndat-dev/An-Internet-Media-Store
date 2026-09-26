data "oci_cloud_guard_security_recipes" "maximum" {
  count = var.create_security_zone && var.security_zone_recipe_id == null ? 1 : 0

  compartment_id = var.tenancy_ocid
}

locals {
  oracle_security_zone_recipes = try([
    for recipe in data.oci_cloud_guard_security_recipes.maximum[0].security_recipe_collection[0].items : recipe
    if recipe.owner == "ORACLE" && strcontains(lower(recipe.display_name), "maximum")
  ], [])
  discovered_security_zone_recipe_id = try(
    local.oracle_security_zone_recipes[0].id,
    null
  )
  effective_security_zone_recipe_id = try(coalesce(
    var.security_zone_recipe_id,
    local.discovered_security_zone_recipe_id
  ), null)
}

resource "oci_cloud_guard_target" "oe" {
  count = var.create_cloud_guard_target ? 1 : 0

  compartment_id       = oci_identity_compartment.oe.id
  display_name         = "cg-${local.prefix}"
  description          = "Cloud Guard target for ${local.prefix}"
  target_resource_id   = oci_identity_compartment.oe.id
  target_resource_type = "COMPARTMENT"
  state                = "ACTIVE"
  freeform_tags        = local.common_tags
}

resource "oci_cloud_guard_security_zone" "sensitive_data" {
  count = var.create_security_zone ? 1 : 0

  compartment_id                      = oci_identity_compartment.sensitive_data.id
  display_name                        = "sz-${local.prefix}-sensitive-data"
  description                         = "Maximum Security Zone for sensitive data"
  security_zone_recipe_id             = local.effective_security_zone_recipe_id
  is_inheritance_after_delete_enabled = false
  freeform_tags                       = local.common_tags
}
