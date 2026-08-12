// WAF Dashboard - Backend API Integration Module
// This file contains all API integration functions for the WAF Dashboard

class WAFDashboardAPI {
    constructor(baseUrl = null) {
        const origin = typeof window !== 'undefined' ? window.location.origin : 'http://localhost';
        const wsProtocol = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsHost = typeof window !== 'undefined' ? window.location.host : 'localhost';
        
        this.baseUrl = baseUrl || origin;
        this.wsUrl = `${wsProtocol}//${wsHost}/ws/logs`;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 3000;
        this.onMessageCallback = null;
        this.onConnectionChange = null;
    }

    // ===================================================================
    // WebSocket Connection Management
    // ===================================================================
    
    connectWebSocket(onMessage, onConnectionChange) {
        this.onMessageCallback = onMessage;
        this.onConnectionChange = onConnectionChange;

        try {
            console.log(`[WebSocket] Connecting to ${this.wsUrl}...`);
            this.ws = new WebSocket(this.wsUrl);

            this.ws.onopen = () => {
                console.log('[WebSocket] ✅ Connected successfully');
                this.reconnectAttempts = 0;
                if (this.onConnectionChange) {
                    this.onConnectionChange(true);
                }
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    console.log('[WebSocket] 📨 Received message:', data);
                    if (this.onMessageCallback) {
                        this.onMessageCallback(data);
                    }
                } catch (error) {
                    console.error('[WebSocket] ❌ Error parsing message:', error);
                }
            };

            this.ws.onclose = (event) => {
                console.log('[WebSocket] 🔌 Connection closed', event);
                if (this.onConnectionChange) {
                    this.onConnectionChange(false);
                }
                this.attemptReconnect();
            };

            this.ws.onerror = (error) => {
                console.error('[WebSocket] ❌ Error:', error);
                if (this.onConnectionChange) {
                    this.onConnectionChange(false);
                }
            };
        } catch (error) {
            console.error('[WebSocket] ❌ Connection error:', error);
            this.attemptReconnect();
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`[WebSocket] 🔄 Attempting reconnect ${this.reconnectAttempts}/${this.maxReconnectAttempts}...`);
            
            setTimeout(() => {
                if (this.onMessageCallback && this.onConnectionChange) {
                    this.connectWebSocket(this.onMessageCallback, this.onConnectionChange);
                }
            }, this.reconnectDelay);
        } else {
            console.error('[WebSocket] ❌ Max reconnection attempts reached');
        }
    }

    disconnectWebSocket() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
    }

    // ===================================================================
    // Health Check
    // ===================================================================
    
    async checkHealth() {
        try {
            const response = await fetch(`${this.baseUrl}/health`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            console.log('[API] ✅ Health check:', data);
            return data;
        } catch (error) {
            console.error('[API] ❌ Health check failed:', error);
            return {
                status: 'error',
                redis_connected: false,
                mongodb_connected: false,
                anomaly_model_loaded: false,
                error: error.message
            };
        }
    }

    // ===================================================================
    // Historical Data Loading (NEW)
    // ===================================================================
    
    async getHistoricalLogs(limit = 20) {
        try {
            const response = await fetch(`${this.baseUrl}/logs?limit=${limit}`);
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            const data = await response.json();
            console.log('[API] ✅ Historical logs fetched:', data);
            return data;
        } catch (error) {
            console.error('[API] ❌ Failed to fetch historical logs:', error);
            return { logs: [], count: 0, error: error.message };
        }
    }

    // ===================================================================
    // WAF Mode Control
    // ===================================================================
    
    async setWAFMode(mode) {
        try {
            const validModes = ['off', 'fast', 'full'];
            if (!validModes.includes(mode)) {
                throw new Error(`Invalid mode: ${mode}. Must be one of: ${validModes.join(', ')}`);
            }

            const response = await fetch(`${this.baseUrl}/set-mode/${mode}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                }
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
                throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('[API] ✅ WAF mode set:', data);
            return data;
        } catch (error) {
            console.error('[API] ❌ Failed to set WAF mode:', error);
            throw error;
        }
    }

    // ===================================================================
    // Whitelist Management
    // ===================================================================
    
    async whitelistRequest(mongoId) {
        try {
            const response = await fetch(`${this.baseUrl}/pass-request`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ mongo_id: mongoId })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
                throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('[API] ✅ Request whitelisted:', data);
            return data;
        } catch (error) {
            console.error('[API] ❌ Failed to whitelist request:', error);
            throw error;
        }
    }

    // ===================================================================
    // Test Request (for demonstration)
    // ===================================================================
    
    async sendTestRequest(method, path, requestBody) {
        try {
            const response = await fetch(`${this.baseUrl}/analyze`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    method: method,
                    path: path,
                    protocol: 'HTTP/1.1',
                    request_body: requestBody
                })
            });

            if (!response.ok) {
                const errorData = await response.json().catch(() => ({ detail: 'Unknown error' }));
                throw new Error(errorData.detail || `HTTP error! status: ${response.status}`);
            }

            const data = await response.json();
            console.log('[API] ✅ Request analyzed:', data);
            return data;
        } catch (error) {
            console.error('[API] ❌ Failed to analyze request:', error);
            throw error;
        }
    }
}

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = WAFDashboardAPI;
}
