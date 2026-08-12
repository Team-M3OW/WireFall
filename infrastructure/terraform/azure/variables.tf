variable "azure_subscription_id" {
  description = "Azure Subscription ID (optional if logged in via az login)"
  type        = string
  default     = ""
}

variable "resource_group_name" {
  description = "Name of Azure Resource Group"
  type        = string
  default     = "rg-wirefall-prod"
}

variable "location" {
  description = "Azure Region location"
  type        = string
  default     = "eastus"
}

variable "environment" {
  description = "Environment tag"
  type        = string
  default     = "production"
}

variable "vm_size" {
  description = "Azure VM Size (Standard_B2s or Standard_B1ms - Eligible for Azure $100 Student Credits)"
  type        = string
  default     = "Standard_B2s"
}

variable "admin_username" {
  description = "SSH admin username"
  type        = string
  default     = "azureuser"
}

variable "ssh_public_key_path" {
  description = "Path to SSH public key file (e.g. ~/.ssh/id_rsa.pub)"
  type        = string
  default     = "~/.ssh/id_rsa.pub"
}

variable "allowed_ssh_cidr" {
  description = "IP CIDR permitted for SSH access"
  type        = string
  default     = "*"
}
