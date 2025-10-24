Self-Learning WAF - Setup Guide
Prerequisites
Windows 10/11

Python 3.8+

Docker Desktop

Setup Steps
1. Install Docker Desktop
Download from https://www.docker.com/products/docker-desktop

2. Setup Redis
Create docker-compose.yml:

text
version: '3.8'

services:
  redis:
    image: redis:alpine
    container_name: redis-waf
    ports:
      - "6379:6379"
    command: redis-server --appendonly yes --stop-writes-on-bgsave-error no
    volumes:
      - redis-data:/data
    restart: unless-stopped

volumes:
  redis-data:
Start Redis:

powershell
docker-compose up -d
Redis runs on: localhost:6379

3. Install OpenResty
Download:

Go to https://openresty.org/en/download.html

Download Windows 64-bit version (e.g., openresty-1.25.3.1-win64.zip)

Extract to C:\openresty

Install lua-resty-http:

powershell
cd C:\openresty
New-Item -Path "C:\openresty\lualib\resty" -ItemType Directory -Force

Invoke-WebRequest -Uri "https://raw.githubusercontent.com/ledgetech/lua-resty-http/master/lib/resty/http.lua" -OutFile "C:\openresty\lualib\resty\http.lua"

Invoke-WebRequest -Uri "https://raw.githubusercontent.com/ledgetech/lua-resty-http/master/lib/resty/http_headers.lua" -OutFile "C:\openresty\lualib\resty\http_headers.lua"

Invoke-WebRequest -Uri "https://raw.githubusercontent.com/ledgetech/lua-resty-http/master/lib/resty/http_connect.lua" -OutFile "C:\openresty\lualib\resty\http_connect.lua"
Setup files:

powershell
# Copy nginx.conf to C:\openresty\conf\nginx.conf
# Copy waf_chain.lua to C:\openresty\nginx\lua\waf_chain.lua

New-Item -Path "C:\openresty\nginx\lua" -ItemType Directory -Force
4. Install Python Dependencies
powershell
python -m venv venv
.\venv\Scripts\Activate
pip install -r requirements.txt
Running the WAF
Terminal 1 - FastAPI:

powershell
.\venv\Scripts\Activate
python main.py
Runs on: localhost:8001

Terminal 2 - OpenResty:

powershell
cd C:\openresty
.\nginx.exe
Runs on: localhost:80

Terminal 3 - Your Backend App:

powershell
npm run dev  # or whatever command
Should run on: localhost:3000

Service Ports Summary
Service	Port	URL
Redis	6379	localhost:6379
FastAPI	8001	http://localhost:8001
OpenResty	80	http://localhost:80
Backend App	3000	http://localhost:3000
Quick Test
text
GET http://localhost:80/products
Files Needed
main.py - FastAPI analyzer

requirements.txt - Python packages

nginx.conf - Goes to C:\openresty\conf\

waf_chain.lua - Goes to C:\openresty\nginx\lua\

docker-compose.yml - Redis setup