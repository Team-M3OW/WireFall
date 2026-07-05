import React, { useEffect, useMemo, useRef, useState } from 'react'
import WAFDashboardAPI from '../dashboard-api'
import { Chart, LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Legend, Tooltip } from 'chart.js'

Chart.register(LineController, LineElement, PointElement, LinearScale, CategoryScale, Filler, Legend, Tooltip)

export default function Dashboard() {
  const api = useMemo(() => new WAFDashboardAPI('http://localhost:8001'), [])

  const [benignCount, setBenign] = useState(0)
  const [maliciousCount, setMalicious] = useState(0)
  const totalCount = benignCount + maliciousCount
  const [connected, setConnected] = useState(false)
  const [lastUpdated, setLastUpdated] = useState('--:--:--')
  const [events, setEvents] = useState([])
  const [mode, setModeState] = useState('fast')
  const [logCollapsed, setLogCollapsed] = useState(false)
  const [logs, setLogs] = useState([])
  const [logLimit, setLogLimit] = useState(200)

  const chartRef = useRef(null)
  const chartInstanceRef = useRef(null)
  const pollingIntervalRef = useRef(null)

  // Helper function to convert UTC to IST
  const convertToIST = (utcDateString) => {
    const date = new Date(utcDateString)
    const istOffset = 5.5 * 60 * 60 * 1000
    const istDate = new Date(date.getTime() + istOffset)
    return istDate
  }

  // Format time in IST
  const formatISTTime = (utcDateString) => {
    const istDate = convertToIST(utcDateString)
    return istDate.toLocaleTimeString('en-IN', { 
      hour: '2-digit', 
      minute: '2-digit', 
      second: '2-digit',
      hour12: true 
    })
  }

  // Initialize chart
  useEffect(() => {
    const ctx = chartRef.current?.getContext('2d')
    if (!ctx) return

    chartInstanceRef.current = new Chart(ctx, {
      type: 'line',
      data: {
        labels: [],
        datasets: [
          {
            label: 'Benign',
            data: [],
            borderColor: 'rgba(59, 130, 246, 1)',
            backgroundColor: 'rgba(59, 130, 246, 0.15)',
            tension: 0.35,
            fill: true,
          },
          {
            label: 'Malicious',
            data: [],
            borderColor: 'rgba(239, 68, 68, 1)',
            backgroundColor: 'rgba(239, 68, 68, 0.15)',
            tension: 0.35,
            fill: true,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { beginAtZero: true, ticks: { precision: 0 } },
        },
        plugins: { 
          legend: { display: true }, 
          tooltip: { intersect: false, mode: 'index' } 
        },
      },
    })

    return () => {
      chartInstanceRef.current?.destroy()
      chartInstanceRef.current = null
    }
  }, [])

  // Fetch logs from /logs endpoint
  const fetchLogs = async () => {
    try {
      const response = await api.getHistoricalLogs(logLimit, 0)
      
      if (response.logs && response.logs.length > 0) {
        setConnected(true)
        setLogs(response.logs)
        
        // Calculate totals
        let benign = 0
        let malicious = 0
        const timeGroups = {}
        
        response.logs.forEach(log => {
          if (log.analysis && log.analysis.is_malicious) {
            malicious++
          } else {
            benign++
          }
          
          // Group by time for chart (IST)
          const timeKey = formatISTTime(log.timestamp)
          
          if (!timeGroups[timeKey]) {
            timeGroups[timeKey] = { benign: 0, malicious: 0 }
          }
          
          if (log.analysis && log.analysis.is_malicious) {
            timeGroups[timeKey].malicious++
          } else {
            timeGroups[timeKey].benign++
          }
        })
        
        setBenign(benign)
        setMalicious(malicious)
        
        // Update chart
        const chart = chartInstanceRef.current
        if (chart) {
          const sortedTimes = Object.keys(timeGroups).sort((a, b) => {
            const timeA = new Date('1970-01-01 ' + a.replace(/AM|PM/, '').trim())
            const timeB = new Date('1970-01-01 ' + b.replace(/AM|PM/, '').trim())
            return timeA - timeB
          })
          
          chart.data.labels = sortedTimes
          chart.data.datasets[0].data = sortedTimes.map(t => timeGroups[t].benign)
          chart.data.datasets[1].data = sortedTimes.map(t => timeGroups[t].malicious)
          chart.update('none')
        }
        
        // Update events table
        const recentEvents = response.logs.slice(0, 20).map(log => ({
          id: log._id,
          path: log.request?.path || '/',
          action: log.action_taken || 'ALLOW',
          ip: extractIP(log.request?.request_body) || '0.0.0.0',
          ts: formatISTTime(log.timestamp),
          fullTs: convertToIST(log.timestamp),
        }))
        setEvents(recentEvents)
        
        setLastUpdated(new Date().toLocaleTimeString('en-IN', { 
          hour: '2-digit', 
          minute: '2-digit', 
          second: '2-digit',
          hour12: true 
        }))
      } else {
        setConnected(false)
      }
    } catch (error) {
      console.error('Failed to fetch logs:', error)
      setConnected(false)
    }
  }

  // Helper to extract IP from request body
  const extractIP = (requestBody) => {
    if (!requestBody) return null
    const ipMatch = String(requestBody).match(/\b(?:\d{1,3}\.){3}\d{1,3}\b/)
    return ipMatch ? ipMatch[0] : null
  }

  // Fetch logs when limit changes
  useEffect(() => {
    fetchLogs()
  }, [logLimit])

  // Initial load and polling
  useEffect(() => {
    // Health check
    api.checkHealth()
      .then(() => setConnected(true))
      .catch(() => setConnected(false))

    // Initial fetch
    fetchLogs()

    // Poll every 3 seconds
    pollingIntervalRef.current = setInterval(() => {
      fetchLogs()
    }, 3000)

    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
      }
    }
  }, [])

  const setMode = async (newMode) => {
    try {
      await api.setWAFMode(newMode)
      setModeState(newMode)
    } catch (e) {
      console.error('Failed to set mode', e)
    }
  }

  const handleRefresh = () => {
    fetchLogs()
  }

  const handleLogLimitChange = (e) => {
    const newLimit = parseInt(e.target.value, 10)
    setLogLimit(newLimit)
    console.log('Log limit changed to:', newLimit)
  }

  return (
    <div className="dashboard-container">
      <header className="dashboard-header">
        <div className="header-left">
          <h1 className="dashboard-title">
            <i className="fas fa-shield-alt pulse" />
            WireFall
          </h1>
          <div className="system-status">
            <div className="status-indicator" id="mlStatus">
              <div className={`status-dot ml${connected ? '' : ' offline'}`} id="mlStatusDot" />
              <span>DL Model</span>
            </div>
          </div>
        </div>
        <div className="header-right">
          {/* Log Limit Selector */}
          <div className="log-limit-selector">
            <label htmlFor="logLimit" style={{ marginRight: '0.5rem', fontSize: '0.875rem', color: '#d1d5db' }}>
              Load:
            </label>
            <select 
              id="logLimit" 
              value={logLimit} 
              onChange={handleLogLimitChange}
              style={{
                background: 'rgba(255, 255, 255, 0.1)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '0.375rem',
                padding: '0.375rem 0.75rem',
                color: '#fff',
                fontSize: '0.875rem',
                cursor: 'pointer',
                marginRight: '1rem'
              }}
            >
              <option value={50}>50 logs</option>
              <option value={100}>100 logs</option>
              <option value={200}>200 logs</option>
              <option value={500}>500 logs</option>
              <option value={1000}>1000 logs</option>
            </select>
          </div>
          
          <div className="last-updated">
            <i className="fas fa-clock" />
            <span id="lastUpdated">Last Updated: {lastUpdated}</span>
          </div>
          <button className="refresh-btn" id="refreshBtn" onClick={handleRefresh}>
            <i className="fas fa-sync-alt" />
          </button>
        </div>
      </header>

      <div className="dashboard-body">
        <aside className="control-panel">
          <div className="panel-section">
            <h3>WAF Mode</h3>
            <div className="toggle-group" id="wafModeToggle">
              <div className={`toggle-option${mode === 'fast' ? ' active' : ''}`} data-mode="fast" onClick={() => setMode('fast')}>
                <i className="fas fa-bolt" />
                <span>Fast</span>
                <div className="toggle-ring" />
              </div>
              <div className={`toggle-option${mode === 'full' ? ' active' : ''}`} data-mode="full" onClick={() => setMode('full')}>
                <i className="fas fa-shield" />
                <span>Full</span>
                <div className="toggle-ring" />
              </div>
              <div className={`toggle-option${mode === 'off' ? ' active' : ''}`} data-mode="off" onClick={() => setMode('off')}>
                <i className="fas fa-power-off" />
                <span>Off</span>
                <div className="toggle-ring" />
              </div>
            </div>
          </div>

          <div className="panel-section">
            <h3>Live Metrics</h3>
            <div className="metric-card">
              <div className="metric-icon benign"><i className="fas fa-check" /></div>
              <div className="metric-content">
                <div className="metric-value" id="benignCount">{benignCount}</div>
                <div className="metric-label">Benign</div>
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-icon malicious"><i className="fas fa-ban" /></div>
              <div className="metric-content">
                <div className="metric-value" id="maliciousCount">{maliciousCount}</div>
                <div className="metric-label">Blocked</div>
              </div>
            </div>
            <div className="metric-card">
              <div className="metric-icon total"><i className="fas fa-chart-line" /></div>
              <div className="metric-content">
                <div className="metric-value" id="totalCount">{totalCount}</div>
                <div className="metric-label">Total</div>
              </div>
            </div>
          </div>
        </aside>

        <main className="main-content">
          <section className="graph-section">
            <div className="graph-header">
              <h2>Live Request Traffic</h2>
            </div>
            <div className="ecg-chart-container">
              <canvas id="ecgChart" ref={chartRef} />
            </div>
          </section>

          <section className="table-section">
            <div className="table-header">
              <h3>Recent Events (Showing last 20 of {logs.length})</h3>
            </div>
            <div className="table-container">
              <table className="events-table">
                <thead>
                  <tr>
                    <th>Time (IST)</th>
                    <th>IP</th>
                    <th>Path</th>
                    <th>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {events.length > 0 ? (
                    events.map((e) => (
                      <tr key={e.id} className={e.action === 'BLOCK' ? 'malicious' : ''}>
                        <td>{e.ts}</td>
                        <td>{e.ip}</td>
                        <td>{e.path}</td>
                        <td>{e.action}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={4} style={{ textAlign: 'center' }}>No events yet</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </main>
      </div>

      <div className={`log-viewer${logCollapsed ? ' collapsed' : ''}`} id="logViewer">
        <div className="log-header" onClick={() => setLogCollapsed((c) => !c)}>
          <h4>System Logs</h4>
          <button
            className="log-toggle"
            id="logToggle"
            aria-expanded={!logCollapsed}
            onClick={(e) => {
              e.stopPropagation()
              setLogCollapsed((c) => !c)
            }}
          >
            <i className="fas fa-chevron-up" />
          </button>
        </div>
        <div className="log-content" id="logContent">
          {logs.length > 0 ? (
            logs.slice(0, 10).map((log, idx) => (
              <div key={idx} className="log-entry">
                <span className="log-time">[{formatISTTime(log.timestamp)}]</span>
                <span className={`log-level ${log.analysis?.is_malicious ? 'warning' : 'info'}`}>
                  {log.analysis?.is_malicious ? 'ALERT' : 'INFO'}
                </span>
                <span className="log-message">
                  {log.request?.method} {log.request?.path} - {log.action_taken}
                </span>
              </div>
            ))
          ) : (
            <div className="log-entry">
              <span className="log-time">[{lastUpdated}]</span>
              <span className="log-level info">INFO</span>
              <span className="log-message">Waiting for logs...</span>
            </div>
          )}
        </div>
      </div>

      <div className="background-effects">
        <div className="particle" style={{ '--delay': '0s', '--duration': '10s' }} />
        <div className="particle" style={{ '--delay': '2s', '--duration': '12s' }} />
        <div className="particle" style={{ '--delay': '4s', '--duration': '8s' }} />
      </div>
    </div>
  )
}
