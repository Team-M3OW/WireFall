# 🛡️ WAF Dashboard - API Quick Reference

## Backend Endpoints

### Base URL: `http://localhost:8001`

---

## 📡 Analysis Endpoint

### POST `/analyze`
Analyze incoming requests for security threats using ML model.

**Request Body:**
```json
{
  "method": "GET|POST|PUT|DELETE",
  "path": "/api/endpoint",
  "protocol": "HTTP/1.1",
  "request_body": "request payload or query string"
}
```

**Response (Benign):**
```json
{
  "allow": true,
  "reason": "Passed transformer model analysis."
}
```

**Response (Malicious):**
```json
{
  "allow": false,
  "reason": "Blocked by transformer model (loss: 5.1234)",
  "auto_learned_rule": "(?i)malicious_pattern"
}
```

**PowerShell Example:**
```powershell
$body = @{
    method = "POST"
    path = "/api/login"
    protocol = "HTTP/1.1"
    request_body = "username=admin&password=test123"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8001/analyze" -Method Post -Body $body -ContentType "application/json"
```

---

## 🎛️ WAF Mode Control

### POST `/set-mode/{mode_name}`
Change the WAF operational mode.

**Parameters:**
- `mode_name`: `off` | `fast` | `full`

**Modes:**
- `off`: Disable all WAF protection
- `fast`: Rules-based detection only (faster)
- `full`: Complete ML + rules protection (slower, more accurate)

**Response:**
```json
{
  "status": "success",
  "mode": "fast",
  "message": "WAF mode set to fast"
}
```

**PowerShell Examples:**
```powershell
# Turn off WAF
Invoke-RestMethod -Uri "http://localhost:8001/set-mode/off" -Method Post

# Enable fast mode
Invoke-RestMethod -Uri "http://localhost:8001/set-mode/fast" -Method Post

# Enable full protection
Invoke-RestMethod -Uri "http://localhost:8001/set-mode/full" -Method Post
```

---

## ✅ Whitelist Management

### POST `/pass-request`
Add a blocked request to the whitelist.

**Request Body:**
```json
{
  "mongo_id": "507f1f77bcf86cd799439011"
}
```

**Response:**
```json
{
  "status": "success",
  "message": "Request added to whitelist",
  "mongo_id": "507f1f77bcf86cd799439011",
  "whitelisted_data": "request_body preview (first 100 chars)..."
}
```

**PowerShell Example:**
```powershell
$body = @{
    mongo_id = "67890abcdef12345"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8001/pass-request" -Method Post -Body $body -ContentType "application/json"
```

---

## 🩺 Health Check

### GET `/health`
Check the status of all WAF components.

**Response:**
```json
{
  "status": "healthy",
  "redis_connected": true,
  "mongodb_connected": true,
  "anomaly_model_loaded": true
}
```

**PowerShell Example:**
```powershell
Invoke-RestMethod -Uri "http://localhost:8001/health" -Method Get
```

---

## 🔌 WebSocket Endpoint

### WS `/ws/logs`
Real-time log streaming endpoint.

**Connection URL:** `ws://localhost:8001/ws/logs`

**Message Format:**
```json
{
  "_id": "507f1f77bcf86cd799439011",
  "timestamp": "2025-10-15T10:30:45.123Z",
  "method": "POST",
  "path": "/api/login",
  "request_body": "username=admin",
  "action_taken": "BLOCK",
  "is_malicious": true,
  "reconstruction_loss": 5.1234,
  "perplexity": 167.89,
  "auto_learned_rule": "(?i)suspicious_pattern"
}
```

**JavaScript Example:**
```javascript
const ws = new WebSocket('ws://localhost:8001/ws/logs');

ws.onopen = () => console.log('Connected to WAF logs');
ws.onmessage = (event) => {
  const log = JSON.parse(event.data);
  console.log('New request:', log);
};
```

---

## 📊 Testing Commands

### Send Multiple Test Requests

```powershell
# Function to send test requests
function Send-TestRequest {
    param($Method, $Path, $Body, $IsMalicious)
    
    $requestBody = @{
        method = $Method
        path = $Path
        protocol = "HTTP/1.1"
        request_body = $Body
    } | ConvertTo-Json
    
    $label = if ($IsMalicious) { "MALICIOUS" } else { "BENIGN" }
    Write-Host "Sending $label request to $Path..." -ForegroundColor $(if ($IsMalicious) { "Red" } else { "Green" })
    
    $response = Invoke-RestMethod -Uri "http://localhost:8001/analyze" -Method Post -Body $requestBody -ContentType "application/json"
    Write-Host "Response: $($response | ConvertTo-Json -Compress)`n" -ForegroundColor Gray
}

# Benign requests
Send-TestRequest -Method "GET" -Path "/api/users" -Body "" -IsMalicious $false
Send-TestRequest -Method "POST" -Path "/api/login" -Body "username=john&password=secret" -IsMalicious $false

# Malicious requests
Send-TestRequest -Method "POST" -Path "/admin" -Body "'; DROP TABLE users; --" -IsMalicious $true
Send-TestRequest -Method "GET" -Path "/api/files" -Body "../../../etc/passwd" -IsMalicious $true
Send-TestRequest -Method "POST" -Path "/search" -Body "<script>alert('XSS')</script>" -IsMalicious $true
```

### Stress Test (100 requests)

```powershell
1..100 | ForEach-Object {
    $isMalicious = (Get-Random -Minimum 0 -Maximum 2) -eq 1
    $body = if ($isMalicious) { "'; DROP TABLE test; --" } else { "normal data" }
    $path = if ($isMalicious) { "/admin/shell" } else { "/api/data" }
    
    $requestBody = @{
        method = "POST"
        path = $path
        protocol = "HTTP/1.1"
        request_body = $body
    } | ConvertTo-Json
    
    Invoke-RestMethod -Uri "http://localhost:8001/analyze" -Method Post -Body $requestBody -ContentType "application/json" | Out-Null
    
    if ($_ % 10 -eq 0) {
        Write-Host "Sent $_/100 requests..." -ForegroundColor Yellow
    }
}

Write-Host "✅ Stress test complete!" -ForegroundColor Green
```

---

## 🔑 Redis Keys

The WAF uses the following Redis keys:

- `waf:mode` - Current operational mode (string)
- `waf:whitelist` - Set of whitelisted request patterns (set)
- `waf:rules:regex` - Set of learned regex patterns (set)

**Check current mode:**
```powershell
redis-cli GET waf:mode
```

**View whitelist:**
```powershell
redis-cli SMEMBERS waf:whitelist
```

---

## 📚 MongoDB Collections

**Database:** `waf_db`
**Collection:** `analysis_logs`

**Document Structure:**
```json
{
  "_id": ObjectId("..."),
  "timestamp": ISODate("2025-10-15T10:30:45.123Z"),
  "request": {
    "method": "POST",
    "path": "/api/login",
    "protocol": "HTTP/1.1",
    "request_body": "username=admin"
  },
  "analysis": {
    "is_malicious": true,
    "reconstruction_loss": 5.1234,
    "perplexity": 167.89
  },
  "action_taken": "BLOCK",
  "auto_learned_rule": "(?i)pattern"
}
```

**Query recent logs:**
```javascript
db.analysis_logs.find().sort({timestamp: -1}).limit(10)
```

---

## 🎯 Error Responses

### 400 Bad Request
```json
{
  "detail": "Invalid mode. Must be one of: ['off', 'fast', 'full']"
}
```

### 404 Not Found
```json
{
  "detail": "Request not found in database"
}
```

### 500 Internal Server Error
```json
{
  "detail": "Internal server error: connection timeout"
}
```

### 503 Service Unavailable
```json
{
  "detail": "Redis service unavailable"
}
```

---

## 📞 Support

For issues or questions, check:
1. Backend logs in the terminal
2. Frontend console (F12 in browser)
3. Redis connection: `redis-cli ping`
4. MongoDB connection: `mongosh --eval "db.runCommand({ping:1})"`

---

**Happy monitoring! 🛡️**
