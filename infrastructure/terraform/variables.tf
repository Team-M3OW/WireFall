variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment name"
  type        = string
  default     = "production"
}

variable "vpc_cidr" {
  description = "VPC CIDR range"
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "Public subnet CIDR range"
  type        = string
  default     = "10.0.1.0/24"
}

variable "instance_type" {
  description = "EC2 Instance Type (Free tier: t2.micro or t3.micro)"
  type        = string
  default     = "t3.micro"
}

variable "allowed_ssh_cidr" {
  description = "IP CIDR allowed for SSH access"
  type        = string
  default     = "0.0.0.0/0"
}

variable "key_name" {
  description = "SSH key pair name"
  type        = string
  default     = ""
}
