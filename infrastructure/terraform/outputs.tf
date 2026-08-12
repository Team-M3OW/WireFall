output "wirefall_public_ip" {
  description = "Public Elastic IP of WireFall WAF deployment"
  value       = module.compute.public_ip
}

output "waf_api_endpoint" {
  description = "WireFall WAF API URL"
  value       = "http://${module.compute.public_ip}:8001"
}

output "logs_service_endpoint" {
  description = "WireFall Logs Service URL"
  value       = "http://${module.compute.public_ip}:8002"
}

output "dashboard_url" {
  description = "WireFall Dashboard & Hacker Mode URL"
  value       = "http://${module.compute.public_ip}"
}
