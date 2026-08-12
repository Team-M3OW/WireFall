terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

module "vpc" {
  source             = "./modules/vpc"
  vpc_cidr           = var.vpc_cidr
  public_subnet_cidr = var.public_subnet_cidr
  availability_zone  = "${var.aws_region}a"
  environment        = var.environment
}

module "security" {
  source           = "./modules/security"
  vpc_id           = module.vpc.vpc_id
  allowed_ssh_cidr = var.allowed_ssh_cidr
  environment      = var.environment
}

module "compute" {
  source            = "./modules/compute"
  instance_type     = var.instance_type # Strictly Free Tier (t2.micro/t3.micro)
  subnet_id         = module.vpc.public_subnet_id
  security_group_id = module.security.security_group_id
  key_name          = var.key_name
  environment       = var.environment
}
