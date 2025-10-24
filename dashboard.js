// WAF Heartbeat Dashboard - JavaScript Controller
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
            updateInterval: 1000,
            animationDuration: 500,
            currentTimeframe: '5m',
            apiBaseUrl: 'http://localhost:8001',
            wsUrl: 'ws://localhost:8001/ws/logs'
        };

        this.chart = null;
        this.updateTimer = null;
        this.eventId = 0;
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;

        this.init();
    }

    init() {
        this.setupChart();
        this.setupEventListeners();
        this.connectWebSocket();
        this.checkBackendHealth();
        this.setupLogViewer();
        this.updateLastUpdated();
        this.startSystemHealthMonitoring();
    }

    setupChart() {
        const ctx = document.getElementById('ecgChart').getContext('2d');
        const chartContainer = document.querySelector('.ecg-chart-container');
        
        // Add smooth entrance animation
        chartContainer.classList.add('chart-animate-in');
        
        // Create initial data points
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
                            font: {
                                size: 14,
                                weight: '600'
                            },
                            color: '#374151'
                        },
                        grid: {
                            display: true,
                            color: 'rgba(0, 0, 0, 0.05)'
                        },
                        ticks: {
                            maxRotation: 45,
                            minRotation: 45,
                            font: {
                                size: 11
                            },
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
                            font: {
                                size: 14,
                                weight: '600'
                            },
                            color: '#374151'
                        },
                        grid: {
                            display: true,
                            color: 'rgba(0, 0, 0, 0.05)'
                        },
                        ticks: {
                            font: {
                                size: 11
                            },
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
                            font: {
                                size: 13,
                                weight: '600'
                            },
                            color: '#374151'
                        }
                    },
                    tooltip: {
                        backgroundColor: 'rgba(0, 0, 0, 0.8)',
                        padding: 12,
                        titleFont: {
                            size: 14,
                            weight: 'bold'
                        },
                        bodyFont: {
                            size: 13
                        },
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

    switchWAFMode(mode) {
        // Update UI with smooth transitions
        document.querySelectorAll('.toggle-option').forEach(opt => {
            opt.classList.remove('active');
            // Add subtle fade effect
            opt.style.transition = 'all 0.3s cubic-bezier(0.4, 0.0, 0.2, 1)';
        });
        
        const newActiveOption = document.querySelector(`[data-mode="${mode}"]`);
        newActiveOption.classList.add('active');
        
        // Add emphasis animation
        newActiveOption.style.transform = 'scale(1.02)';
        setTimeout(() => {
            newActiveOption.style.transform = 'scale(1)';
        }, 200);

        // Log the mode change
        this.addLogEntry(`WAF mode switched to: ${mode.toUpperCase()}`, 'info');

        // Simulate different behavior based on mode
        switch(mode) {
            case 'fast':
                this.config.updateInterval = 800;
                break;
            case 'full':
                this.config.updateInterval = 1000;
                break;
            case 'off':
                this.config.updateInterval = 2000;
                break;
        }

        this.restartUpdates();
    }

    switchTimeframe(timeframe) {
        // Update UI
        document.querySelectorAll('.graph-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.querySelector(`[data-timeframe="${timeframe}"]`).classList.add('active');

        this.config.currentTimeframe = timeframe;
        
        // Adjust data points based on timeframe
        switch(timeframe) {
            case '1m':
                this.config.maxDataPoints = 60;
                break;
            case '5m':
                this.config.maxDataPoints = 100;
                break;
            case '15m':
                this.config.maxDataPoints = 150;
                break;
            case '1h':
                this.config.maxDataPoints = 200;
                break;
        }

        this.addLogEntry(`Timeframe changed to: ${timeframe}`, 'info');
    }

    filterTable(filterId) {
        // Update UI
        document.querySelectorAll('.table-btn').forEach(btn => {
            btn.classList.remove('active');
        });
        document.getElementById(filterId).classList.add('active');

        // Filter logic would go here
        this.addLogEntry(`Table filtered by: ${filterId.replace('filter', '')}`, 'info');
    }

    startRealTimeUpdates() {
        this.updateTimer = setInterval(() => {
            this.generateRealtimeData();
            this.updateChart();
            this.updateCounters();
            this.updateSystemHealth();
            this.updateLastUpdated();
            
            // Randomly generate new security events
            if (Math.random() < 0.3) {
                this.generateSecurityEvent();
            }
        }, this.config.updateInterval);
    }

    restartUpdates() {
        if (this.updateTimer) {
            clearInterval(this.updateTimer);
        }
        this.startRealTimeUpdates();
    }

    generateRealtimeData() {
        const now = new Date();
        const timeLabel = now.toLocaleTimeString();

        // Generate realistic request patterns
        const baseRequests = 15 + Math.sin(Date.now() / 10000) * 10;
        const benignRequests = Math.floor(baseRequests + Math.random() * 20);
        
        // Malicious requests - occasional spikes
        let maliciousRequests = 0;
        if (Math.random() < 0.15) {
            maliciousRequests = Math.floor(Math.random() * 8) + 1;
        } else if (Math.random() < 0.05) {
            // Bigger attack spike
            maliciousRequests = Math.floor(Math.random() * 25) + 10;
        }

        // Update totals
        this.data.benignCount += benignRequests;
        this.data.maliciousCount += maliciousRequests;
        this.data.totalCount = this.data.benignCount + this.data.maliciousCount;

        // Add to chart data
        this.chart.data.labels.push(timeLabel);
        this.chart.data.datasets[0].data.push(benignRequests);
        this.chart.data.datasets[1].data.push(maliciousRequests);

        // Remove old data points
        if (this.chart.data.labels.length > this.config.maxDataPoints) {
            this.chart.data.labels.shift();
            this.chart.data.datasets[0].data.shift();
            this.chart.data.datasets[1].data.shift();
        }
    }

    updateChart() {
        // Use smooth animation for chart updates
        this.chart.update('active', {
            duration: 400,
            easing: 'easeOutCubic'
        });
    }

    updateCounters() {
        // Animate counter updates
        this.animateCounter('benignCount', this.data.benignCount);
        this.animateCounter('maliciousCount', this.data.maliciousCount);
        this.animateCounter('totalCount', this.data.totalCount);
        
        // Update graph counters too
        this.animateCounter('graphBenignCount', this.data.benignCount);
        this.animateCounter('graphMaliciousCount', this.data.maliciousCount);
        this.animateCounter('graphTotalCount', this.data.totalCount);
    }

    animateCounter(elementId, targetValue) {
        const element = document.getElementById(elementId);
        const currentValue = parseInt(element.textContent.replace(/,/g, '')) || 0;
        
        // Skip animation if no change
        if (currentValue === targetValue) return;
        
        // Add updating animation class
        element.classList.add('updating');
        
        const difference = targetValue - currentValue;
        const duration = 600; // ms
        const startTime = performance.now();
        
        const animate = (currentTime) => {
            const elapsed = currentTime - startTime;
            const progress = Math.min(elapsed / duration, 1);
            
            // Use easing function for smooth animation
            const easeOutCubic = 1 - Math.pow(1 - progress, 3);
            const newValue = Math.floor(currentValue + (difference * easeOutCubic));
            
            element.textContent = newValue.toLocaleString();
            
            if (progress < 1) {
                requestAnimationFrame(animate);
            } else {
                element.textContent = targetValue.toLocaleString();
                element.classList.remove('updating');
            }
        };
        
        requestAnimationFrame(animate);
    }

    updateSystemHealth() {
        // Simulate system health fluctuations
        this.data.systemHealth.cpu = Math.max(20, Math.min(90, 
            this.data.systemHealth.cpu + (Math.random() - 0.5) * 10));
        this.data.systemHealth.memory = Math.max(30, Math.min(95, 
            this.data.systemHealth.memory + (Math.random() - 0.5) * 8));
        this.data.systemHealth.disk = Math.max(10, Math.min(80, 
            this.data.systemHealth.disk + (Math.random() - 0.5) * 5));

        // Update health bars
        document.getElementById('cpuUsage').style.width = `${this.data.systemHealth.cpu}%`;
        document.getElementById('memoryUsage').style.width = `${this.data.systemHealth.memory}%`;
        document.getElementById('diskUsage').style.width = `${this.data.systemHealth.disk}%`;
    }

    generateSecurityEvent() {
        const eventTypes = [
            { type: 'sql-injection', threat: 'SQL Injection', severity: 'high' },
            { type: 'xss', threat: 'XSS Attack', severity: 'medium' },
            { type: 'ddos', threat: 'DDoS Attack', severity: 'high' },
            { type: 'brute-force', threat: 'Brute Force', severity: 'medium' }
        ];

        const ips = [
            '192.168.1.100', '10.0.0.55', '172.16.0.24', 
            '203.0.113.42', '198.51.100.78', '93.184.216.34'
        ];

        const urls = [
            '/admin/login', '/api/users', '/wp-admin/', 
            '/login.php', '/api/auth', '/dashboard'
        ];

        const eventType = eventTypes[Math.floor(Math.random() * eventTypes.length)];
        const sourceIP = ips[Math.floor(Math.random() * ips.length)];
        const url = urls[Math.floor(Math.random() * urls.length)];

        const event = {
            id: ++this.eventId,
            timestamp: new Date().toLocaleTimeString(),
            sourceIP: sourceIP,
            url: url,
            threatType: eventType.type,
            threat: eventType.threat,
            action: Math.random() > 0.7 ? 'Blocked' : 'Detected',
            severity: eventType.severity
        };

        this.addEventToTable(event);
        
        // Log the event
        this.addLogEntry(`${event.threat} detected from ${event.sourceIP}`, 
            event.severity === 'high' ? 'warning' : 'info');
    }

    addEventToTable(event) {
        const tableBody = document.getElementById('eventsTableBody');
        const row = document.createElement('tr');
        
        if (event.action === 'Blocked' || event.severity === 'high') {
            row.classList.add('malicious');
        }
        
        // Add smooth entrance animation
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
                    <button class="action-btn allow" onclick="dashboard.allowRequest('${event.id}')">
                        <i class="fas fa-check"></i> Allow
                    </button>
                    <button class="action-btn block" onclick="dashboard.blockRequest('${event.id}')">
                        <i class="fas fa-times"></i> Block
                    </button>
                </div>
            </td>
        `;

        // Insert at top
        tableBody.insertBefore(row, tableBody.firstChild);

        // Trigger smooth entrance animation
        requestAnimationFrame(() => {
            row.style.opacity = '1';
            row.style.transform = 'translateX(0)';
        });

        // Keep only last 20 events with fade-out animation
        while (tableBody.children.length > 20) {
            const lastRow = tableBody.lastChild;
            lastRow.style.transition = 'all 0.3s ease-out';
            lastRow.style.opacity = '0';
            lastRow.style.transform = 'translateX(-50px)';
            
            setTimeout(() => {
                if (lastRow.parentNode) {
                    tableBody.removeChild(lastRow);
                }
            }, 300);
        }
    }

    allowRequest(eventId) {
        this.addLogEntry(`Request ${eventId} whitelisted by user`, 'success');
        // Additional logic would go here
    }

    blockRequest(eventId) {
        this.addLogEntry(`Request ${eventId} permanently blocked by user`, 'warning');
        // Additional logic would go here
    }

    refreshData() {
        const refreshBtn = document.getElementById('refreshBtn');
        refreshBtn.style.transform = 'rotate(360deg)';
        
        setTimeout(() => {
            refreshBtn.style.transform = 'rotate(0deg)';
        }, 500);

        this.addLogEntry('Dashboard data refreshed', 'info');
        this.updateLastUpdated();
    }

    updateLastUpdated() {
        const now = new Date();
        document.getElementById('lastUpdated').textContent = 
            `Last Updated: ${now.toLocaleTimeString()}`;
    }

    setupLogViewer() {
        // Initially collapsed
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

        // Keep only last 50 entries
        while (logContent.children.length > 50) {
            logContent.removeChild(logContent.lastChild);
        }

        // Auto-scroll to top for new entries
        logContent.scrollTop = 0;
    }

    generateInitialData() {
        // Generate some initial data
        for (let i = 0; i < 20; i++) {
            this.generateRealtimeData();
        }
        
        // Generate some initial events
        for (let i = 0; i < 5; i++) {
            setTimeout(() => {
                this.generateSecurityEvent();
            }, i * 200);
        }

        this.updateChart();
        this.updateCounters();
        
        // Add some initial log entries
        setTimeout(() => {
            this.addLogEntry('WAF Dashboard initialized successfully', 'success');
            this.addLogEntry('Real-time monitoring started', 'info');
            this.addLogEntry('ML threat detection engine online', 'success');
        }, 500);
    }

    // API Integration methods (for future use)
    async fetchRealTimeData() {
        try {
            const response = await fetch('/api/dashboard/metrics');
            const data = await response.json();
            return data;
        } catch (error) {
            console.error('Failed to fetch real-time data:', error);
            this.addLogEntry('Failed to fetch real-time data from API', 'error');
            return null;
        }
    }

    async updateWAFSettings(mode) {
        try {
            const response = await fetch('/api/waf/settings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ mode: mode })
            });
            
            if (response.ok) {
                this.addLogEntry(`WAF settings updated: ${mode}`, 'success');
            } else {
                throw new Error('Failed to update WAF settings');
            }
        } catch (error) {
            console.error('Failed to update WAF settings:', error);
            this.addLogEntry('Failed to update WAF settings', 'error');
        }
    }
}

// Initialize dashboard when DOM is loaded
let dashboard;
document.addEventListener('DOMContentLoaded', () => {
    dashboard = new WAFDashboard();
    
    // Add some subtle UI enhancements
    setTimeout(() => {
        document.body.classList.add('loaded');
    }, 100);
});

// Handle visibility change to pause/resume updates
document.addEventListener('visibilitychange', () => {
    if (dashboard) {
        if (document.hidden) {
            if (dashboard.updateTimer) {
                clearInterval(dashboard.updateTimer);
            }
        } else {
            dashboard.startRealTimeUpdates();
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