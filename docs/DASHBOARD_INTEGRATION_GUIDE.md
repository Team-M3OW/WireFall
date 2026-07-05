# 🚀 WAF Dashboard Integration Guide

## Overview
Your WAF Dashboard is now fully integrated with the FastAPI backend. It receives real-time security event updates via WebSocket and provides interactive controls for WAF management.

## 🔧 Setup Instructions

### 1. **Prerequisites**
Make sure you have the following running:

- **Redis** (for WAF mode storage and whitelisting)
- **MongoDB** (for logging analysis results)
- **Python FastAPI Backend** (main.py)

### 2. **Environment Variables**
Ensure your `.env` file contains:

```env
REDIS_URL=redis://localhost:6379
MONGO_URI=mongodb://localhost:27017/
```

### 3. **Start the Backend**

```powershell
# Navigate to your project directory
cd C:\Users\nilam\team_m3ow

# Start the FastAPI backend
python main.py
```

The backend will start on `http://localhost:8001`

### 4. **Open the Dashboard**

Simply open `waf_heartbeat_dashboard.html` in your web browser:

```powershell
# Open with default browser
start waf_heartbeat_dashboard.html

# Or specify a browser
start chrome waf_heartbeat_dashboard.html
start firefox waf_heartbeat_dashboard.html
```

---

## 🎯 Features

### **Real-Time Updates**
- ✅ **WebSocket Connection**: Receives live security events from the backend
- ✅ **Auto-Reconnect**: Automatically reconnects if connection is lost
- ✅ **Live Chart**: Updates in real-time as requests are analyzed
- ✅ **Event Table**: Shows recent security events with full details

### **WAF Control**
- 🔧 **Mode Switching**: 
  - **Transformer Only** (fast): ML-based detection
  - **Full WAF** (full): ML + rules-based detection
  - **WAF Off** (off): Disable protection
- ✅ **Whitelist Management**: Click "Allow" to whitelist blocked requests
- 🚫 **Permanent Blocking**: Click "Block" to add rules

### **Monitoring**
- 📊 **Live Metrics**: Track benign, malicious, and total requests
- 💓 **Health Indicators**: Monitor system CPU, memory, and disk I/O
- 📝 **System Logs**: View detailed operation logs
- 🔄 **Manual Refresh**: Click refresh button or press Ctrl+R

---

## 🧪 Testing the Integration

### **Test 1: Send Benign Request**

```powershell
$body = @{
    method = "GET"
    path = "/api/users"
    protocol = "HTTP/1.1"
    request_body = "page=1&limit=10"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8001/analyze" -Method Post -Body $body -ContentType "application/json"
```

**Expected Result**: Dashboard shows green benign request

### **Test 2: Send Malicious Request**

```powershell
$body = @{
    method = "POST"
    path = "/admin/shell"
    protocol = "HTTP/1.1"
    request_body = "'; DROP TABLE users; --"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:8001/analyze" -Method Post -Body $body -ContentType "application/json"
```

**Expected Result**: Dashboard shows red malicious request in table

### **Test 3: Stress Test (Send 50 Requests)**

```powershell
1..50 | ForEach-Object {
    $isMalicious = (Get-Random -Minimum 0 -Maximum 2) -eq 1
    $body = @{
        method = "POST"
        path = if ($isMalicious) { "/admin/shell" } else { "/api/data" }
        protocol = "HTTP/1.1"
        request_body = if ($isMalicious) { "'; DROP TABLE test; --" } else { "normal data" }
    } | ConvertTo-Json
    
    Invoke-RestMethod -Uri "http://localhost:8001/analyze" -Method Post -Body $body -ContentType "application/json" | Out-Null
    
    Start-Sleep -Milliseconds 200
}

Write-Host "✅ Sent 50 requests!" -ForegroundColor Green
```

**Expected Result**: Dashboard graph fills with activity, metrics update

### **Test 4: Change WAF Mode**

```powershell
# Set to Fast Mode (Transformer Only)
Invoke-RestMethod -Uri "http://localhost:8001/set-mode/fast" -Method Post

# Set to Full WAF
Invoke-RestMethod -Uri "http://localhost:8001/set-mode/full" -Method Post

# Turn Off WAF
Invoke-RestMethod -Uri "http://localhost:8001/set-mode/off" -Method Post
```

**Expected Result**: Dashboard UI updates, log entry shows mode change

---

## 🔍 Troubleshooting

### **WebSocket Not Connecting**

```powershell
# Check if backend is running
Invoke-RestMethod -Uri "http://localhost:8001/health" -Method Get
```

**Solutions:**
- Ensure `main.py` is running on port 8001
- Check for firewall blocking WebSocket connections
- Look for errors in browser console (F12)

### **No Events Appearing**

1. **Check Backend Logs**: Look for errors in the terminal running `main.py`
2. **Test API Directly**: Send a test request using PowerShell
3. **Check MongoDB Connection**: Ensure MongoDB is running
4. **Check Redis Connection**: Ensure Redis is running

```powershell
# Test MongoDB
mongosh --eval "db.runCommand({ping:1})"

# Test Redis
redis-cli ping
```

### **CORS Errors**

If you see CORS errors in the browser console:

1. Check that CORS middleware is configured in `main.py`
2. Ensure you're opening the HTML from the correct origin
3. Try serving the HTML via a local server:

```powershell
# Using Python
python -m http.server 8080

# Then open: http://localhost:8080/waf_heartbeat_dashboard.html
```

### **Backend Not Responding**

```powershell
# Check if port 8001 is in use
netstat -ano | findstr :8001

# Kill process if needed
taskkill /PID <PID> /F

# Restart backend
python main.py
```

---

## 📊 Dashboard Components

### **File Structure**
```
team_m3ow/
├── waf_heartbeat_dashboard.html  # Main dashboard HTML
├── styles.css                     # Light theme styles
├── dashboard-api.js               # API integration module
├── dashboard-integrated.js        # Main dashboard logic
├── main.py                        # FastAPI backend
└── requirements.txt               # Python dependencies
```

### **API Endpoints Used**

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/health` | GET | Check backend status |
| `/analyze` | POST | Analyze request (used by NGINX) |
| `/set-mode/{mode}` | POST | Change WAF mode |
| `/pass-request` | POST | Whitelist a blocked request |
| `/ws/logs` | WebSocket | Real-time event streaming |

### **Data Flow**

```
NGINX → /analyze → Backend ML Model → MongoDB
                                    ↓
                              WebSocket
                                    ↓
                              Dashboard
```

---

## 🎨 UI Features

### **Color Coding**
- 🟢 **Green**: Benign requests, success messages
- 🔴 **Red**: Malicious requests, errors
- 🔵 **Blue**: Informational messages
- 🟡 **Orange**: Warnings

### **Interactive Elements**
- Click **WAF Mode buttons** to change protection level
- Click **Timeframe buttons** (1M, 5M, 15M, 1H) to adjust chart view
- Click **Allow button** to whitelist a request
- Click **Block button** to permanently block
- Click **Refresh button** or press Ctrl+R to refresh data
- Press **Ctrl+L** to toggle log viewer

---

## 📈 Performance Tips

1. **Adjust Update Interval**: Modify `config.updateInterval` in `dashboard-integrated.js`
2. **Limit Data Points**: Change `config.maxDataPoints` for better performance
3. **Filter Events**: Use table filter buttons to focus on specific event types
4. **Close Other Tabs**: For best performance, keep dashboard as active tab

---

## 🔐 Security Notes

- Dashboard connects to `localhost:8001` by default
- WebSocket uses `ws://` protocol (not encrypted)
- For production, use HTTPS/WSS with proper authentication
- Configure CORS settings in `main.py` based on your deployment

---

## 📞 Support & Debugging

### **Browser Console**
Press F12 and check the Console tab for:
- WebSocket connection status
- API call responses
- JavaScript errors

### **Network Tab**
Check the Network tab (F12) for:
- Failed API requests
- WebSocket messages
- Response times

### **Backend Logs**
Monitor the terminal running `main.py` for:
- Request analysis results
- MongoDB/Redis connection issues
- WebSocket connections

---

## 🎯 Next Steps

1. **Test the integration** with the provided PowerShell commands
2. **Customize the dashboard** colors/styles in `styles.css`
3. **Add more features** like:
   - Historical data views
   - Advanced filtering
   - Export to CSV
   - Alert notifications

---

**🎉 Your WAF Dashboard is now fully integrated and ready to use!**

For more information, check:
- `API_REFERENCE.md` - Complete API documentation
- `TROUBLESHOOTING.md` - Common issues and solutions
- Backend logs - Real-time operation details
