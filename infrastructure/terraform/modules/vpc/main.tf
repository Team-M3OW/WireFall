terraform {
  required_version = ">= 1.0.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

resource "aws_vpc" "wirefall_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name        = "${var.environment}-wirefall-vpc"
    Environment = var.environment
    Project     = "WireFall-as-a-Service"
  }
}

resource "aws_internet_gateway" "wirefall_igw" {
  vpc_id = aws_vpc.wirefall_vpc.id

  tags = {
    Name        = "${var.environment}-wirefall-igw"
    Environment = var.environment
  }
}

resource "aws_subnet" "public_subnet" {
  vpc_id                  = aws_vpc.wirefall_vpc.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true

  tags = {
    Name        = "${var.environment}-wirefall-public-subnet"
    Environment = var.environment
  }
}

resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.wirefall_vpc.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.wirefall_igw.id
  }

  tags = {
    Name        = "${var.environment}-wirefall-public-rt"
    Environment = var.environment
  }
}

resource "aws_route_table_association" "public_assoc" {
  subnet_id      = aws_subnet.public_subnet.id
  route_table_id = aws_route_table.public_rt.id
}
