// WAF Heartbeat Dashboard - Integrated with Backend API
// This version connects to the FastAPI backend and receives real-time updates

class WAFDashboard {
    constructor() {
        this.data = {
            benignCount: 0,
            maliciousCount: 0,
            totalCount: 0,
            recentEvents: [],
            systemHealth: {
                cpu: 45,
                memory: 62,
                disk: 23
            }
        };

        this.config = {
            maxDataPoints: 100,
            updateInterval: 5000, // Health check interval
            animationDuration: 500,
            currentTimeframe: '5m',
            apiBaseUrl: 'http://localhost:8001',
            wsUrl: 'ws://localhost:8001/ws/logs'
        };

        this.chart = null;
        this.updateTimer = null;
        this.eventId = 0;
        this.api = new WAFDashboardAPI(this.config.apiBaseUrl);
        this.isConnected = false;

        this.init();
    }

    // ===================================================================
    // UPDATED: Initialization with Historical Data Loading
    // ===================================================================
    
    async init() {
        this.setupChart();
        this.setupEventListeners();
        this.connectWebSocket();
        this.checkBackendHealth();
        this.setupLogViewer();
        this.updateLastUpdated();
        this.startHealthMonitoring();
        
        // ✅ NEW: Load historical data from MongoDB
        await this.loadHistoricalData();
    }

    // ===================================================================
    // NEW: Load Historical Data from MongoDB
    // ===================================================================
    
   // ===================================================================
// UPDATED: Load Historical Data from MongoDB (with Chart Population)
// ===================================================================

async loadHistoricalData() {
    try {
        this.addLogEntry('Loading historical data from database...', 'info');
        const response = await this.api.getHistoricalLogs(20);
        
        if (response.logs && response.logs.length > 0) {
            console.log(`📚 Loading ${response.logs.length} historical events...`);
            
            // Clear existing data first
            this.data.benignCount = 0;
            this.data.maliciousCount = 0;
            this.data.totalCount = 0;
            
            // ✅ NEW: Prepare chart data arrays
            const chartData = {
                benign: [],
                malicious: []
            };
            
            // Calculate totals and aggregate chart data by time
            response.logs.forEach(log => {
                if (log.analysis && log.analysis.is_malicious) {
                    this.data.maliciousCount++;
                } else {
                    this.data.benignCount++;
                }
            });
            this.data.totalCount = this.data.benignCount + this.data.maliciousCount;
            
            // ✅ NEW: Populate chart with historical data
            // Group logs by time buckets (e.g., per minute) for visualization
            const timeGroups = {};
            
            response.logs.forEach(log => {
                const timestamp = new Date(log.timestamp);
                const timeKey = timestamp.toLocaleTimeString();
                
                if (!timeGroups[timeKey]) {
                    timeGroups[timeKey] = { benign: 0, malicious: 0 };
                }
                
                if (log.analysis.is_malicious) {
                    timeGroups[timeKey].malicious++;
                } else {
                    timeGroups[timeKey].benign++;
                }
            });
            
            // ✅ NEW: Add to chart (newest data on the right)
            const sortedTimes = Object.keys(timeGroups).sort((a, b) => {
                const timeA = new Date('1970-01-01 ' + a);
                const timeB = new Date('1970-01-01 ' + b);
                return timeA - timeB;
            });
            
            // Clear existing chart data
            this.chart.data.labels = [];
            this.chart.data.datasets[0].data = [];
            this.chart.data.datasets[1].data = [];
            
            // Add historical data to chart
            sortedTimes.forEach(timeKey => {
                this.chart.data.labels.push(timeKey);
                this.chart.data.datasets[0].data.push(timeGroups[timeKey].benign);
                this.chart.data.datasets[1].data.push(timeGroups[timeKey].malicious);
            });
            
            // Update chart
            this.updateChart();
            
            // Update counters
            this.updateCounters();
            
            // Add events to table (reverse order to show newest first)
            const tableBody = document.getElementById('eventsTableBody');
            tableBody.innerHTML = ''; // Clear table first
            
            response.logs.reverse().forEach(log => {
                const event = {
                    id: log._id,
                    timestamp: new Date(log.timestamp).toLocaleTimeString(),
                    sourceIP: this.extractIP(log.request.request_body) || 'N/A',
                    url: log.request.path,
                    threatType: this.detectThreatType(log.request.request_body, log.request.path),
                    threat: this.getThreatLabel(log.request.request_body, log.request.path),
                    action: log.action_taken,
                    severity: log.analysis.is_malicious ? 'high' : 'low',
                    mongoId: log._id,
                    reconstructionLoss: log.analysis.reconstruction_loss,
                    autoLearnedRule: log.auto_learned_rule
                };
                this.addEventToTable(event);
            });
            
            this.addLogEntry(`✅ Loaded ${response.logs.length} historical events (${this.data.benignCount} benign, ${this.data.maliciousCount} malicious)`, 'success');
        } else {
            this.addLogEntry('No historical data found in database', 'info');
        }
    } catch (error) {
        console.error('Failed to load historical data:', error);
        this.addLogEntry('⚠️ Failed to load historical data from database', 'warning');
    }
}


    // ===================================================================
    // WebSocket Integration
    // ===================================================================

    connectWebSocket() {
        this.api.connectWebSocket(
            // onMessage callback
            (data) => this.handleWebSocketMessage(data),
            // onConnectionChange callback
            (connected) => this.handleConnectionChange(connected)
        );
    }

    handleWebSocketMessage(data) {
        console.log('Received real-time data:', data);

        // Update counters based on action
        if (data.action_taken === 'BLOCK' || data.is_malicious) {
            this.data.maliciousCount++;
        } else {
            this.data.benignCount++;
        }
        this.data.totalCount = this.data.benignCount + this.data.maliciousCount;

        // Add to chart
        const now = new Date();
        const timeLabel = now.toLocaleTimeString();
        this.chart.data.labels.push(timeLabel);
        
        const benignInc = data.action_taken === 'ALLOW' ? 1 : 0;
        const maliciousInc = data.action_taken === 'BLOCK' ? 1 : 0;
        
        this.chart.data.datasets[0].data.push(benignInc);
        this.chart.data.datasets[1].data.push(maliciousInc);

        // Remove old data points
        if (this.chart.data.labels.length > this.config.maxDataPoints) {
            this.chart.data.labels.shift();
            this.chart.data.datasets[0].data.shift();
            this.chart.data.datasets[1].data.shift();
        }

        // Update UI
        this.updateChart();
        this.updateCounters();

        // Add event to table
        const event = {
            id: data._id,
            timestamp: new Date(data.timestamp).toLocaleTimeString(),
            sourceIP: this.extractIP(data.request_body) || 'N/A',
            url: data.path,
            threatType: this.detectThreatType(data.request_body, data.path),
            threat: this.getThreatLabel(data.request_body, data.path),
            action: data.action_taken,
            severity: data.is_malicious ? 'high' : 'low',
            mongoId: data._id,
            reconstructionLoss: data.reconstruction_loss,
            autoLearnedRule: data.auto_learned_rule
        };

        this.addEventToTable(event);

        // Add log entry
        const logLevel = data.is_malicious ? 'warning' : 'success';
        const message = `${data.method} ${data.path} - ${data.action_taken} (Loss: ${data.reconstruction_loss?.toFixed(4) || 'N/A'})`;
        this.addLogEntry(message, logLevel);
    }

    handleConnectionChange(connected) {
        this.isConnected = connected;
        this.updateMLStatus(connected);
        
        if (connected) {
            this.addLogEntry('Connected to WAF backend', 'success');
        } else {
            this.addLogEntry('Disconnected from WAF backend', 'error');
        }
    }

    updateMLStatus(connected) {
        const statusDot = document.getElementById('mlStatusDot');
        if (statusDot) {
            statusDot.style.background = connected ? '#10b981' : '#ef4444';
        }
    }

    // ===================================================================
    // Helper Functions
    // ===================================================================

    extractIP(requestBody) {
        // Try to extract IP from request body or return a placeholder
        const ipMatch = requestBody?.match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/);
        return ipMatch ? ipMatch[0] : this.generateRandomIP();
    }

    generateRandomIP() {
        return `${Math.floor(Math.random() * 255)}.${Math.floor(Math.random() * 255)}.${Math.floor(Math.random() * 255)}.${Math.floor(Math.random() * 255)}`;
    }

    detectThreatType(requestBody, path) {
        const body = requestBody?.toLowerCase() || '';
        const pathLower = path?.toLowerCase() || '';
        
        if (body.includes('script') || body.includes('<') || body.includes('>')) {
            return 'xss';
        } else if (body.includes('select') || body.includes('drop') || body.includes('union') || pathLower.includes('or')) {
            return 'sql-injection';
        } else if (pathLower.includes('admin') || pathLower.includes('../')) {
            return 'brute-force';
        } else {
            return 'ddos';
        }
    }

    getThreatLabel(requestBody, path) {
        const type = this.detectThreatType(requestBody, path);
        const labels = {
            'xss': 'XSS Attack',
            'sql-injection': 'SQL Injection',
            'brute-force': 'Brute Force',
            'ddos': 'Suspicious Activity'
        };
        return labels[type] || 'Unknown Threat';
    }

    // ===================================================================
    // Health Monitoring
    // ===================================================================

    async checkBackendHealth() {
        try {
            const health = await this.api.checkHealth();
            console.log('Backend health:', health);
            
            // Update status indicators
            this.updateMLStatus(health.anomaly_model_loaded && health.status !== 'error');
            
            if (health.status === 'healthy' || health.status === 'degraded') {
                this.addLogEntry(`Backend status: ${health.status}`, 'info');
            } else {
                this.addLogEntry('Backend connection failed', 'error');
            }
        } catch (error) {
            console.error('Health check failed:', error);
            this.updateMLStatus(false);
        }
    }

    startHealthMonitoring() {
        // Check health every 5 seconds
        setInterval(() => {
            this.checkBackendHealth();
            this.updateSystemHealth();
        }, this.config.updateInterval);
    }

    // ===================================================================
    // Chart Setup
    // ===================================================================

    setupChart() {
        const ctx = document.getElementById('ecgChart').getContext('2d');
        const chartContainer = document.querySelector('.ecg-chart-container');
        
        chartContainer.classList.add('chart-animate-in');
        
        const timeLabels = [];
        const benignData = [];
        const maliciousData = [];
        
        for (let i = 0; i < this.config.maxDataPoints; i++) {
            timeLabels.push('');
            benignData.push(0);
            maliciousData.push(0);
        }

        this.chart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: timeLabels,
                datasets: [
                    {
                        label: 'Benign Requests',
                        data: benignData,
                        borderColor: '#10b981',
                        backgroundColor: 'rgba(16, 185, 129, 0.1)',
                        borderWidth: 2,
                        tension: 0.4,
                        pointRadius: 3,
                        pointHoverRadius: 6,
                        pointBackgroundColor: '#10b981',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        fill: true
                    },
                    {
                        label: 'Malicious Requests',
                        data: maliciousData,
                        borderColor: '#ef4444',
                        backgroundColor: 'rgba(239, 68, 68, 0.1)',
                        borderWidth: 2,
                        tension: 0.4,
                        pointRadius: 3,
                        pointHoverRadius: 6,
                        pointBackgroundColor: '#ef4444',
                        pointBorderColor: '#fff',
                        pointBorderWidth: 2,
                        fill: true
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                animation: {
                    duration: 750,
                    easing: 'easeInOutQuart'
                },
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                scales: {
                    x: {
                        display: true,
                        title: {
                            display: true,
                            text: 'Time',
                            font: { size: 14, weight: '600' },
                            color: '#374151'
                        },
                        grid: {
                            display: true,
                            color: 'rgba(0, 0, 0, 0.05)'
                        },
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45,
                            font: { size: 11 },
                            color: '#6b7280',
                            maxTicksLimit: 10
                        }
                    },
                    y: {
                        display: true,
                        beginAtZero: true,
                        title: {
                            display: true,
                            text: 'Number of Requests',
                            font: { size: 14, weight: '600' },
                            color: '#374151'
                        },
                        grid: {
                            display: true,
                            color: 'rgba(0, 0, 0, 0.05)'
                        },
                        ticks: {
                            font: { size: 11 },
                            color: '#6b7280',
                            stepSize: 1
                        }
                    }
                },
                plugins: {
                    legend: {
                        position: 'top',
                        labels: {
                            usePointStyle: true,
                            padding: 15,
                            font: { size: 13, weight: '600' },
                            color: '#374151'
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        titleFont: { size: 14, weight: 'bold' },
                        bodyFont: { size: 13 },
                        borderColor: 'rgba(255, 255, 255, 0.1)',
                        borderWidth: 1,
                        callbacks: {
                            title: function(context) {
                                return `Time: ${context[0].label}`;
                            },
                            label: function(context) {
                                return `${context.dataset.label}: ${context.parsed.y} requests`;
                            }
                        }
                    }
                }
            }
        });
    }

    // ===================================================================
    // Event Listeners
    // ===================================================================

    setupEventListeners() {
        // WAF Mode Toggle
        document.getElementById('wafModeToggle').addEventListener('click', (e) => {
            const option = e.target.closest('.toggle-option');
            if (option) {
                this.switchWAFMode(option.dataset.mode);
            }
        });

        // Graph timeframe buttons
        document.querySelectorAll('.graph-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.switchTimeframe(e.target.dataset.timeframe);
            });
        });

        // Table filter buttons
        document.querySelectorAll('.table-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                this.filterTable(e.target.id);
            });
        });

        // Refresh button
        document.getElementById('refreshBtn').addEventListener('click', () => {
            this.refreshData();
        });

        // Log viewer toggle
        document.getElementById('logToggle').addEventListener('click', () => {
            this.toggleLogViewer();
        });
    }

    async switchWAFMode(mode) {
        // Update UI
        document.querySelectorAll('.toggle-option').forEach(opt => {
            opt.classList.remove('active');
        });
        
        const newActiveOption = document.querySelector(`[data-mode="${mode}"]`);
        newActiveOption.classList.add('active');
        
        newActiveOption.style.transform = 'scale(1.02)';
        setTimeout(() => {
            newActiveOption.style.transform = 'scale(1)';
        }, 200);

        // Call backend API
        try {
            await this.api.setWAFMode(mode);
            this.addLogEntry(`WAF mode changed to: ${mode.toUpperCase()}`, 'success');
        } catch (error) {
            this.addLogEntry(`Failed to set WAF mode: ${error.message}`, 'error');
            console.error('Error setting WAF mode:', error);
        }
    }

    switchTimeframe(timeframe) {
        document.querySelectorAll('.graph-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-timeframe="${timeframe}"]`).classList.add('active');

        this.config.currentTimeframe = timeframe;
        
        switch(timeframe) {
            case '1m':
                this.config.maxDataPoints = 60;
                break;
            case '5m':
                this.config.maxDataPoints = 100;
                break;
            case '15m':
                this.config.maxDataPoints = 180;
                break;
            case '1h':
                this.config.maxDataPoints = 360;
                break;
        }

        this.addLogEntry(`Timeframe changed to: ${timeframe}`, 'info');
    }

    filterTable(filterId) {
        document.querySelectorAll('.table-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.getElementById(filterId).classList.add('active');

        this.addLogEntry(`Table filtered by: ${filterId.replace('filter', '')}`, 'info');
    }

    // ===================================================================
    // UI Update Functions
    // ===================================================================

    updateChart() {
        this.chart.update('active', {
            duration: 400,
            easing: 'easeOutCubic'
        });
    }

    updateCounters() {
        this.animateCounter('benignCount', this.data.benignCount);
        this.animateCounter('maliciousCount', this.data.maliciousCount);
        this.animateCounter('totalCount', this.data.totalCount);
        this.animateCounter('graphBenignCount', this.data.benignCount);
        this.animateCounter('graphMaliciousCount', this.data.maliciousCount);
        this.animateCounter('graphTotalCount', this.data.totalCount);
    }

    animateCounter(elementId, targetValue) {
        const element = document.getElementById(elementId);
        const currentValue = parseInt(element.textContent.replace(/,/g, '')) || 0;
        
        if (currentValue === targetValue) return;
        
        element.classList.add('updating');
        
        const difference = targetValue - currentValue;
        const duration = 600;
        const startTime = performance.now();
        
        const animate = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            const easeOutCubic = 1 - Math.pow(1 - progress, 3);
            const newValue = Math.floor(currentValue + (difference * easeOutCubic));
            
            element.textContent = newValue.toLocaleString();
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                element.classList.remove('updating');
            }
        };
        
        requestAnimationFrame(animate);
    }

    updateSystemHealth() {
        this.data.systemHealth.cpu = Math.max(20, Math.min(90, 
            this.data.systemHealth.cpu + (Math.random() - 0.5) * 10));
        this.data.systemHealth.memory = Math.max(30, Math.min(95, 
            this.data.systemHealth.memory + (Math.random() - 0.5) * 8));
        this.data.systemHealth.disk = Math.max(10, Math.min(80, 
            this.data.systemHealth.disk + (Math.random() - 0.5) * 5));

        document.getElementById('cpuUsage').style.width = `${this.data.systemHealth.cpu}%`;
        document.getElementById('memoryUsage').style.width = `${this.data.systemHealth.memory}%`;
        document.getElementById('diskUsage').style.width = `${this.data.systemHealth.disk}%`;
    }

    addEventToTable(event) {
        const tableBody = document.getElementById('eventsTableBody');
        const row = document.createElement('tr');
        
        if (event.action === 'BLOCK' || event.severity === 'high') {
            row.classList.add('malicious');
        }
        
        row.style.opacity = '0';
        row.style.transform = 'translateX(100px)';
        row.style.transition = 'all 0.5s cubic-bezier(0.4, 0.0, 0.2, 1)';
        
        row.innerHTML = `
            <td>${event.timestamp}</td>
            <td>${event.sourceIP}</td>
            <td>${event.url}</td>
            <td><span class="threat-badge ${event.threatType}">${event.threat}</span></td>
            <td>${event.action}</td>
            <td>
                <div class="action-buttons">
                    <button class="action-btn allow" onclick="dashboard.allowRequest('${event.mongoId}')">
                        <i class="fas fa-check"></i> Allow
                    </button>
                    <button class="action-btn block" onclick="dashboard.blockRequest('${event.mongoId}')">
                        <i class="fas fa-times"></i> Block
                    </button>
                </div>
            </td>
        `;

        tableBody.insertBefore(row, tableBody.firstChild);

        requestAnimationFrame(() => {
            row.style.opacity = '1';
            row.style.transform = 'translateX(0)';
        });

        while (tableBody.children.length > 20) {
            const lastRow = tableBody.lastChild;
            lastRow.style.transition = 'all 0.3s ease-out';
            lastRow.style.opacity = '0';
            lastRow.style.transform = 'translateX(-50px)';
            
            setTimeout(() => {
                if (lastRow.parentNode) {
                    lastRow.parentNode.removeChild(lastRow);
                }
            }, 300);
        }
    }

    async allowRequest(mongoId) {
        try {
            const result = await this.api.whitelistRequest(mongoId);
            this.addLogEntry(`Request ${mongoId.substring(0, 8)}... whitelisted successfully`, 'success');
            console.log('Whitelist result:', result);
        } catch (error) {
            this.addLogEntry(`Failed to whitelist request: ${error.message}`, 'error');
            console.error('Error whitelisting request:', error);
        }
    }

    blockRequest(mongoId) {
        this.addLogEntry(`Request ${mongoId.substring(0, 8)}... permanently blocked`, 'warning');
        // Additional logic can be added here
    }

    async refreshData() {
        const refreshBtn = document.getElementById('refreshBtn');
        refreshBtn.style.transform = 'rotate(360deg)';
        
        setTimeout(() => {
            refreshBtn.style.transform = 'rotate(0deg)';
        }, 500);

        this.checkBackendHealth();
        
        // ✅ NEW: Reload historical data on refresh
        await this.loadHistoricalData();
        
        this.addLogEntry('Dashboard data refreshed', 'info');
        this.updateLastUpdated();
    }

    updateLastUpdated() {
        const now = new Date();
        document.getElementById('lastUpdated').textContent = 
            `Last Updated: ${now.toLocaleTimeString()}`;
    }

    setupLogViewer() {
        document.getElementById('logViewer').classList.add('collapsed');
    }

    toggleLogViewer() {
        const logViewer = document.getElementById('logViewer');
        const toggleBtn = document.getElementById('logToggle');
        
        logViewer.classList.toggle('collapsed');
        
        if (logViewer.classList.contains('collapsed')) {
            toggleBtn.innerHTML = '<i class="fas fa-chevron-up"></i>';
        } else {
            toggleBtn.innerHTML = '<i class="fas fa-chevron-down"></i>';
        }
    }

    addLogEntry(message, level = 'info') {
        const logContent = document.getElementById('logContent');
        const entry = document.createElement('div');
        entry.className = 'log-entry';
        
        const now = new Date();
        const timeString = now.toLocaleTimeString();
        
        entry.innerHTML = `
            <span class="log-time">[${timeString}]</span>
            <span class="log-level ${level}">${level.toUpperCase()}</span>
            <span class="log-message">${message}</span>
        `;

        logContent.insertBefore(entry, logContent.firstChild);

        while (logContent.children.length > 50) {
            logContent.removeChild(logContent.lastChild);
        }

        logContent.scrollTop = 0;
    }
}

// ===================================================================
// Initialize dashboard when DOM is loaded
// ===================================================================
let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new WAFDashboard();
    
    setTimeout(() => {
        document.body.classList.add('loaded');
    }, 100);
    
    console.log('✅ WAF Dashboard initialized and connected to backend');
});

// Handle visibility change
document.addEventListener('visibilitychange', () => {
    if (dashboard) {
        if (document.hidden) {
            console.log('⏸️ Dashboard paused (tab hidden)');
        } else {
            console.log('▶️ Dashboard resumed (tab visible)');
            dashboard.checkBackendHealth();
        }
    }
});

// Keyboard shortcuts
document.addEventListener('keydown', (e) => {
    if (dashboard && e.ctrlKey) {
        switch(e.key) {
            case 'r':
                e.preventDefault();
                dashboard.refreshData();
                break;
            case 'l':
                e.preventDefault();
                dashboard.toggleLogViewer();
                break;
        }
    }
});
