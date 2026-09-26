variable "tenancy_ocid" {
  description = "OCID của OCI tenancy."
  type        = string
}

variable "landing_zone_compartment_id" {
  description = "OCID của compartment gốc Landing Zone, ví dụ tndat-lz-cmp."
  type        = string
}

variable "region" {
  description = "OCI region triển khai."
  type        = string
  default     = "ap-tokyo-1"
}

variable "oci_profile" {
  description = "Profile trong ~/.oci/config dùng để xác thực."
  type        = string
  default     = "DEFAULT"
}

variable "oe_code" {
  description = "Mã OE ngắn, chỉ gồm chữ thường và số, ví dụ oe01."
  type        = string

  validation {
    condition     = can(regex("^oe[0-9]{2}[a-z0-9-]*$", var.oe_code))
    error_message = "oe_code phải có dạng oe01 hoặc oe02-tf-test."
  }
}

variable "name_suffix" {
  description = "Hậu tố tùy chọn để cô lập bài test, ví dụ tf-test. Để trống cho OE thật."
  type        = string
  default     = ""

  validation {
    condition     = var.name_suffix == "" || can(regex("^[a-z0-9-]+$", var.name_suffix))
    error_message = "name_suffix chỉ được gồm chữ thường, số và dấu gạch ngang."
  }
}

variable "vcn_cidr" {
  description = "CIDR /16 riêng của OE; không được trùng Hub hoặc OE khác."
  type        = string

  validation {
    condition     = can(cidrhost(var.vcn_cidr, 0)) && try(split("/", var.vcn_cidr)[1] == "16", false)
    error_message = "vcn_cidr phải là CIDR IPv4 /16 hợp lệ."
  }
}

variable "hub_vcn_cidr" {
  description = "CIDR của Hub VCN để tạo route riêng qua DRG."
  type        = string
  default     = "10.0.0.0/16"
}

variable "drg_id" {
  description = "OCID DRG dùng chung. Terraform chỉ tạo attachment, không sở hữu DRG."
  type        = string
}

variable "drg_route_table_id" {
  description = "DRG route table dành cho spoke. Để null để OCI dùng bảng mặc định."
  type        = string
  default     = null
  nullable    = true
}

variable "hub_drg_route_table_id" {
  description = "DRG route table dùng cho traffic xuất phát từ Hub. Nếu đặt, Terraform thêm đúng một route trả về CIDR của OE."
  type        = string
  default     = null
  nullable    = true
}

variable "deployment_acknowledgement" {
  description = "Chốt chống apply nhầm. Phải bằng CREATE-<PREFIX> viết hoa, ví dụ CREATE-OE02-TF-TEST."
  type        = string
}

variable "create_iam_group" {
  description = "Tạo IAM group vận hành OE. Tắt nếu tenancy dùng nhóm tập trung khác."
  type        = bool
  default     = true
}

variable "create_cloud_guard_target" {
  description = "Tạo Cloud Guard target cho toàn bộ cây OE."
  type        = bool
  default     = false
}

variable "create_security_zone" {
  description = "Tạo Security Zone trong compartment sensitive-data."
  type        = bool
  default     = true
}

variable "security_zone_recipe_id" {
  description = "OCID Security Zone recipe. Nếu null, code tự tìm Oracle Maximum Security Zone Recipe."
  type        = string
  default     = null
  nullable    = true
}

variable "freeform_tags" {
  description = "Tag chung cho tài nguyên OE."
  type        = map(string)
  default = {
    ManagedBy = "Terraform"
  }
}
