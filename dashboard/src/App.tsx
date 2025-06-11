import React, { useState, useEffect } from 'react'
import './App.css'

interface Issue {
  id: number
  number: number
  title: string
  repository: string
  category?: string
  priority?: string
  confidence?: number
  tags: string[]
  created_at: string
  updated_at: string
  status: string
}

interface ClassificationUpdate {
  type: string
  data: {
    issue_id: number
    category: string
    priority: string
    confidence: number
    tags: string[]
  }
}

interface Stats {
  total_issues: number
  classified_issues: number
  pending_issues: number
  connected_clients: number
  categories: { name: string; count: number }[]
  priorities: { name: string; count: number }[]
}

function App() {
  const [issues, setIssues] = useState<Issue[]>([])
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected')
  const [stats, setStats] = useState<Stats | null>(null)

  useEffect(() => {
    // Connect to WebSocket
    const ws = new WebSocket('ws://localhost:8002/ws')

    ws.onopen = () => {
      setConnectionStatus('connected')
      console.log('Connected to WebSocket')
    }

    ws.onmessage = (event) => {
      try {
        const message: ClassificationUpdate = JSON.parse(event.data)

        if (message.type === 'classification_update') {
          // Update the issue in the list
          setIssues(prev => prev.map(issue =>
            issue.id === message.data.issue_id
              ? {
                  ...issue,
                  category: message.data.category,
                  priority: message.data.priority,
                  confidence: message.data.confidence,
                  tags: message.data.tags,
                  status: 'classified'
                }
              : issue
          ))
        }
      } catch (error) {
        console.error('Error parsing WebSocket message:', error)
      }
    }

    ws.onclose = () => {
      setConnectionStatus('disconnected')
      console.log('Disconnected from WebSocket')
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
      setConnectionStatus('disconnected')
    }

    // Cleanup on unmount
    return () => {
      ws.close()
    }
  }, [])

  useEffect(() => {
    // Fetch initial issues
    fetch('http://localhost:8002/api/issues')
      .then(res => res.json())
      .then(data => setIssues(data))
      .catch(error => console.error('Error fetching issues:', error))

    // Fetch stats
    fetch('http://localhost:8002/api/stats')
      .then(res => res.json())
      .then(data => setStats(data))
      .catch(error => console.error('Error fetching stats:', error))
  }, [])

  const triggerClassification = async (issueId: number) => {
    try {
      await fetch(`http://localhost:8002/api/issues/${issueId}/classify`, {
        method: 'POST'
      })
    } catch (error) {
      console.error('Error triggering classification:', error)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'classified': return '#22c55e'
      case 'pending': return '#f59e0b'
      default: return '#6b7280'
    }
  }

  const getPriorityColor = (priority?: string) => {
    switch (priority) {
      case 'critical': return '#ef4444'
      case 'high': return '#f97316'
      case 'medium': return '#eab308'
      case 'low': return '#22c55e'
      default: return '#6b7280'
    }
  }

  return (
    <div className="App">
      <header className="header">
        <h1>🤖 Auto-Triager Dashboard</h1>
        <div className="connection-status">
          <span className={`status-indicator ${connectionStatus}`}></span>
          <span>WebSocket: {connectionStatus}</span>
        </div>
      </header>

      {stats && (
        <div className="stats-grid">
          <div className="stat-card">
            <h3>Total Issues</h3>
            <p className="stat-number">{stats.total_issues}</p>
          </div>
          <div className="stat-card">
            <h3>Classified</h3>
            <p className="stat-number">{stats.classified_issues}</p>
          </div>
          <div className="stat-card">
            <h3>Pending</h3>
            <p className="stat-number">{stats.pending_issues}</p>
          </div>
          <div className="stat-card">
            <h3>Connected Clients</h3>
            <p className="stat-number">{stats.connected_clients}</p>
          </div>
        </div>
      )}

      <div className="issues-container">
        <h2>Recent Issues</h2>
        <div className="issues-list">
          {issues.map(issue => (
            <div key={issue.id} className="issue-card">
              <div className="issue-header">
                <span className="issue-number">#{issue.number}</span>
                <span
                  className="status-badge"
                  style={{ backgroundColor: getStatusColor(issue.status) }}
                >
                  {issue.status}
                </span>
              </div>

              <h3 className="issue-title">{issue.title}</h3>

              <div className="issue-meta">
                <span className="repository">{issue.repository}</span>
                {issue.category && (
                  <span className="category-badge">{issue.category}</span>
                )}
                {issue.priority && (
                  <span
                    className="priority-badge"
                    style={{ backgroundColor: getPriorityColor(issue.priority) }}
                  >
                    {issue.priority}
                  </span>
                )}
              </div>

              {issue.tags.length > 0 && (
                <div className="tags">
                  {issue.tags.map(tag => (
                    <span key={tag} className="tag">{tag}</span>
                  ))}
                </div>
              )}

              {issue.confidence && (
                <div className="confidence">
                  Confidence: {Math.round(issue.confidence * 100)}%
                </div>
              )}

              <div className="issue-actions">
                <button
                  onClick={() => triggerClassification(issue.id)}
                  className="classify-btn"
                  disabled={issue.status === 'classified'}
                >
                  {issue.status === 'classified' ? 'Classified' : 'Classify'}
                </button>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

export default App
