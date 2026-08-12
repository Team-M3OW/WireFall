output "azure_public_ip" {
  description = "Public IP address of the deployed Azure VM"
  value       = azurerm_public_ip.pip.ip_address
}

output "dashboard_url" {
  description = "Cloudflare-Style Security Dashboard & Hacker Mode URL"
  value       = "http://${azurerm_public_ip.pip.ip_address}/dashboard/"
}

output "hacker_mode_demo_url" {
  description = "Playable Hacker Mode Sandbox URL"
  value       = "http://${azurerm_public_ip.pip.ip_address}/dashboard/hacker.html"
}

output "waf_api_endpoint" {
  description = "WireFall Core WAF API Endpoint"
  value       = "http://${azurerm_public_ip.pip.ip_address}:8001"
}

output "logs_service_endpoint" {
  description = "WireFall Logs Service Endpoint"
  value       = "http://${azurerm_public_ip.pip.ip_address}:8002"
}
