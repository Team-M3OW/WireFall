output "vpc_id" {
  description = "ID of the created VPC"
  value       = aws_vpc.wirefall_vpc.id
}

output "public_subnet_id" {
  description = "ID of the public subnet"
  value       = aws_subnet.public_subnet.id
}
