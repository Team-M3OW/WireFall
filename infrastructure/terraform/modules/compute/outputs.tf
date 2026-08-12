output "public_ip" {
  description = "Public Elastic IP of the WireFall EC2 instance"
  value       = aws_eip.wirefall_eip.public_ip
}

output "instance_id" {
  description = "EC2 Instance ID"
  value       = aws_instance.wirefall_ec2.id
}
