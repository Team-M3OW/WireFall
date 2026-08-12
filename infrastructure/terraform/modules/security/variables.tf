variable "vpc_id" {
  description = "VPC ID where the security group will be created"
  type        = string
}

variable "allowed_ssh_cidr" {
  description = "CIDR block permitted for SSH access"
  type        = string
  default     = "0.0.0.0/0"
}

variable "environment" {
  description = "Environment tag"
  type        = string
  default     = "production"
}
