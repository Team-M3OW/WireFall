data "aws_ami" "ubuntu" {
  most_recent = true

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }

  owners = ["099720109477"] # Canonical
}

resource "aws_instance" "wirefall_ec2" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.instance_type # Strictly t2.micro or t3.micro (Free Tier)
  subnet_id              = var.subnet_id
  vpc_security_group_ids = [var.security_group_id]
  key_name               = var.key_name != "" ? var.key_name : null

  user_data = file("${path.module}/../../user_data.sh")

  root_block_device {
    volume_size           = 30 # AWS Free Tier allows up to 30 GB EBS
    volume_type           = "gp3"
    delete_on_termination = true
  }

  tags = {
    Name        = "${var.environment}-wirefall-instance"
    Environment = var.environment
    Project     = "WireFall-as-a-Service"
  }
}

resource "aws_eip" "wirefall_eip" {
  domain   = "vpc"
  instance = aws_instance.wirefall_ec2.id

  tags = {
    Name        = "${var.environment}-wirefall-eip"
    Environment = var.environment
  }
}
