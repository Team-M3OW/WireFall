// WAF Dashboard API - Pure REST API (No WebSocket)
export default class WAFDashboardAPI {
  constructor(baseUrl = 'http://localhost:8002') {
    this.baseUrl = baseUrl
    console.log('[API] Initialized with base URL:', this.baseUrl)
  }

  // ===================================================================
  // LOGS ENDPOINTS
  // ===================================================================
  
  async getHistoricalLogs(limit = 50, skip = 0) {
    try {
      const response = await fetch(`https://waf-backend-x2kz.onrender.com/logs?limit=${limit}&skip=${skip}`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      console.log('[API] ✅ Fetched', data.count, 'logs')
      return data
    } catch (error) {
      console.error('[API] ❌ Failed to fetch logs:', error)
      return { logs: [], count: 0, total: 0, error: error.message }
    }
  }

  async getLogStats() {
    try {
      const response = await fetch(`${this.baseUrl}/logs/stats`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      console.log('[API] ✅ Log stats fetched:', data)
      return data
    } catch (error) {
      console.error('[API] ❌ Failed to fetch log stats:', error)
      return null
    }
  }

  async getLogById(logId) {
    try {
      const response = await fetch(`${this.baseUrl}/logs/${logId}`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      return await response.json()
    } catch (error) {
      console.error('[API] ❌ Failed to fetch log:', error)
      return null
    }
  }

  // ===================================================================
  // WAF MODE & DASHBOARD
  // ===================================================================
  
  async setWAFMode(mode) {
    const validModes = ['off', 'fast', 'full']
    if (!validModes.includes(mode)) {
      throw new Error(`Invalid mode: ${mode}. Must be one of: ${validModes.join(', ')}`)
    }
    
    try {
      const response = await fetch(`${this.baseUrl}/set-mode/${mode}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      console.log('[API] ✅ WAF mode set to:', mode)
      return data
    } catch (error) {
      console.error('[API] ❌ Failed to set WAF mode:', error)
      throw error
    }
  }

  async whitelistRequest(mongoId) {
    try {
      const response = await fetch(`${this.baseUrl}/pass-request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mongo_id: mongoId })
      })
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      console.log('[API] ✅ Request whitelisted:', mongoId)
      return data
    } catch (error) {
      console.error('[API] ❌ Failed to whitelist request:', error)
      return null
    }
  }

  // ===================================================================
  // HEALTH CHECK
  // ===================================================================
  
  async checkHealth() {
    try {
      const response = await fetch(`${this.baseUrl}/health`)
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      console.log('[API] ✅ Health check:', data.status)
      return data
    } catch (error) {
      console.error('[API] ❌ Health check failed:', error)
      return { 
        status: 'error', 
        redis_connected: false,
        mongodb_connected: false,
        anomaly_model_loaded: false,
        error: error.message 
      }
    }
  }

  // ===================================================================
  // TEST REQUESTS
  // ===================================================================
  
  async sendTestRequest(method, path, requestBody) {
    try {
      const response = await fetch(`${this.baseUrl}/analyze`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          method: method,
          path: path,
          protocol: 'HTTP/1.1',
          request_body: requestBody
        })
      })
      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }
      const data = await response.json()
      console.log('[API] ✅ Test request analyzed:', data)
      return data
    } catch (error) {
      console.error('[API] ❌ Test request failed:', error)
      throw error
    }
  }
}
