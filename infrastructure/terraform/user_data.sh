#!/bin/bash
set -e

# Update and install dependencies
apt-get update -y
apt-get install -y apt-transport-https ca-certificates curl gnupg lsb-release git

# Install Docker
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Enable and start Docker
systemctl enable docker
systemctl start docker

# Create app directory
mkdir -p /opt/wirefall
cd /opt/wirefall

# Clone WireFall repository
git clone https://github.com/Team-M3OW/WireFall.git .

# Start WireFall using Docker Compose
docker compose -f infrastructure/docker-compose.yml up -d

echo "WireFall-as-a-Service successfully deployed!"
