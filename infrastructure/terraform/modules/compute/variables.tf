variable "instance_type" {
  description = "AWS EC2 instance type (Free tier eligible: t2.micro or t3.micro)"
  type        = string
  default     = "t3.micro"
}

variable "subnet_id" {
  description = "Public Subnet ID"
  type        = string
}

variable "security_group_id" {
  description = "Security Group ID"
  type        = string
}

variable "key_name" {
  description = "SSH key pair name (optional)"
  type        = string
  default     = ""
}

variable "environment" {
  description = "Environment tag"
  type        = string
  default     = "production"
}
