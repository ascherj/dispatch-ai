import { useState, useEffect, useCallback } from 'react'
import './App.css'
import { AuthProvider } from './contexts/AuthContext'
import { useAuth } from './hooks/useAuth'
import LoginButton from './components/LoginButton'
import RepositoryManager from './components/RepositoryManager'
import AuthCallback from './components/AuthCallback'
import WelcomePage from './components/WelcomePage'

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

interface Repository {
  id: number
  owner: string
  name: string
  full_name: string
  is_public_dashboard: boolean
  last_synced_at?: string
  status?: string
}

interface EditingIssue {
  id: number
  category: string
  priority: string
  tags: string
}

// ClassificationUpdate interface removed - now handled by generic WebSocket messages

interface Stats {
  total_issues: number
  classified_issues: number
  pending_issues: number
  connected_clients: number
  categories: { name: string; count: number }[]
  priorities: { name: string; count: number }[]
}

function DashboardContent() {
  const { isAuthenticated, isLoading: authLoading, token } = useAuth();
  const [issues, setIssues] = useState<Issue[]>([])
  const [connectionStatus, setConnectionStatus] = useState<'connecting' | 'connected' | 'disconnected'>('disconnected')
  const [stats, setStats] = useState<Stats | null>(null)
  const [editingIssue, setEditingIssue] = useState<EditingIssue | null>(null)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [isDarkMode, setIsDarkMode] = useState(() => {
    const saved = localStorage.getItem('theme')
    return saved ? saved === 'dark' : true // Default to dark mode
  })
  const [activeTab, setActiveTab] = useState<'issues' | 'repositories'>('issues')
  const [repositories, setRepositories] = useState<Repository[]>([])
  const [selectedRepo, setSelectedRepo] = useState<string>('all')
  const [sortBy, setSortBy] = useState<'date' | 'priority' | 'status'>('date')
  const [filterCategory, setFilterCategory] = useState<string>('all')
  const [filterPriority, setFilterPriority] = useState<string>('all')

  // Utility function for authenticated API calls
  const authenticatedFetch = useCallback(async (url: string, options: RequestInit = {}) => {
    const headers = {
      'Content-Type': 'application/json',
      ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
      ...(options.headers || {}),
    }

    return fetch(url, {
      ...options,
      headers,
    })
  }, [token])

  useEffect(() => {
    let ws: WebSocket | null = null
    let reconnectTimeout: NodeJS.Timeout | null = null
    let reconnectAttempts = 0
    const maxReconnectAttempts = 5
    const reconnectInterval = 3000 // 3 seconds

    const connectWebSocket = () => {
      const baseWsUrl = import.meta.env.VITE_WS_URL || 'ws://localhost:8002/ws'
      const wsUrl = token ? `${baseWsUrl}?token=${token}` : baseWsUrl

      setConnectionStatus('connecting')
      ws = new WebSocket(wsUrl)

      ws.onopen = () => {
        setConnectionStatus('connected')
        reconnectAttempts = 0
        console.log('Connected to WebSocket')
      }

      ws.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data)
          console.log('Received WebSocket message:', message)

          if (message.type === 'issue_update') {
            console.log('Processing issue_update message')

            // Handle both raw issues and enriched issues
            if (message.topic === 'issues.enriched' && message.data.issue) {
              // Enriched issue with classification data
              const issueData = message.data.issue
              const classification = message.data.classification

              console.log('Updating issue with classification:', issueData.number, classification)

              setIssues(prev => {
                const existingIndex = prev.findIndex(issue => issue.number === issueData.number)
                if (existingIndex >= 0) {
                  // Update existing issue
                  const updated = [...prev]
                  updated[existingIndex] = {
                    ...updated[existingIndex],
                    category: classification?.category,
                    priority: classification?.priority,
                    confidence: classification?.confidence,
                    tags: classification?.tags || [],
                    status: 'classified'
                  }
                  console.log('Updated existing issue')
                  return updated
                } else {
                  // Add new issue
                  const newIssue: Issue = {
                    id: issueData.id,
                    number: issueData.number,
                    title: issueData.title,
                    repository: issueData.repository,
                    category: classification?.category,
                    priority: classification?.priority,
                    confidence: classification?.confidence,
                    tags: classification?.tags || [],
                    created_at: issueData.created_at,
                    updated_at: issueData.updated_at,
                    status: 'classified'
                  }
                  console.log('Added new issue:', newIssue)
                  return [newIssue, ...prev]
                }
              })
            } else if (message.topic === 'issues.raw') {
              console.log('Received raw issue, will wait for enriched version')
            }
          } else if (message.type === 'classification_update') {
            // Handle legacy classification_update messages
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
          console.error('Error parsing WebSocket message:', error, event.data)
        }
      }

      ws.onclose = (event) => {
        setConnectionStatus('disconnected')
        console.log('WebSocket disconnected:', event.code, event.reason)

        // Attempt to reconnect if it wasn't a manual close and we haven't exceeded max attempts
        if (event.code !== 1000 && reconnectAttempts < maxReconnectAttempts) {
          reconnectAttempts++
          console.log(`Attempting to reconnect... (${reconnectAttempts}/${maxReconnectAttempts})`)
          reconnectTimeout = setTimeout(connectWebSocket, reconnectInterval)
        } else if (reconnectAttempts >= maxReconnectAttempts) {
          console.log('Max reconnection attempts reached')
        }
      }

      ws.onerror = (error) => {
        console.error('WebSocket error:', error)
        setConnectionStatus('disconnected')
      }
    }

    // Initial connection
    connectWebSocket()

    // Cleanup on unmount or token change
    return () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
      }
      if (ws) {
        ws.close(1000, 'Component unmounting or token changed')
      }
    }
  }, [token])

  useEffect(() => {
    // Only fetch data if user is authenticated
    if (!isAuthenticated || !token) return

    // Fetch initial issues
    const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8002'
    authenticatedFetch(`${apiUrl}/api/issues`)
      .then(res => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`)
        }
        return res.json()
      })
      .then(data => setIssues(data))
      .catch(error => console.error('Error fetching issues:', error))

    // Fetch stats
    authenticatedFetch(`${apiUrl}/api/stats`)
      .then(res => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`)
        }
        return res.json()
      })
      .then(data => setStats(data))
      .catch(error => console.error('Error fetching stats:', error))

    // Fetch user repositories
    authenticatedFetch(`${apiUrl}/auth/user/repositories`)
      .then(res => {
        if (!res.ok) {
          throw new Error(`HTTP ${res.status}: ${res.statusText}`)
        }
        return res.json()
      })
      .then(data => setRepositories(data))
      .catch(error => console.error('Error fetching repositories:', error))
  }, [isAuthenticated, token, authenticatedFetch])

  // Theme persistence effect
  useEffect(() => {
    localStorage.setItem('theme', isDarkMode ? 'dark' : 'light')
    document.documentElement.setAttribute('data-theme', isDarkMode ? 'dark' : 'light')
  }, [isDarkMode])

  // Handle OAuth callback
  if (window.location.pathname === '/auth/callback') {
    return <AuthCallback />;
  }

  const toggleTheme = () => {
    setIsDarkMode(!isDarkMode)
  }

  const triggerClassification = async (issueId: number) => {
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8002'
      await authenticatedFetch(`${apiUrl}/api/issues/${issueId}/classify`, {
        method: 'POST'
      })
    } catch (error) {
      console.error('Error triggering classification:', error)
    }
  }

  const startEditing = (issue: Issue) => {
    setEditingIssue({
      id: issue.id,
      category: issue.category || '',
      priority: issue.priority || '',
      tags: issue.tags.join(', ')
    })
  }

  const cancelEditing = () => {
    setEditingIssue(null)
  }

  const saveCorrection = async () => {
    if (!editingIssue) return

    setIsSubmitting(true)
    try {
      const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8002'
      const response = await authenticatedFetch(`${apiUrl}/api/issues/${editingIssue.id}/correct`, {
        method: 'POST',
        body: JSON.stringify({
          issue_id: editingIssue.id,
          category: editingIssue.category,
          priority: editingIssue.priority,
          tags: editingIssue.tags.split(',').map(tag => tag.trim()).filter(tag => tag.length > 0)
        })
      })

      if (response.ok) {
        const updatedIssue = await response.json()
        setIssues(prev => prev.map(issue =>
          issue.id === editingIssue.id
            ? { ...issue, ...updatedIssue, status: 'classified' }
            : issue
        ))
        setEditingIssue(null)
      } else {
        console.error('Failed to save correction')
      }
    } catch (error) {
      console.error('Error saving correction:', error)
    } finally {
      setIsSubmitting(false)
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

  if (authLoading) {
    return (
      <div className="App">
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Loading...</p>
        </div>
      </div>
    );
  }

  // Show welcome page for unauthenticated users
  if (!isAuthenticated) {
    return <WelcomePage />;
  }

  return (
    <div className="App">
      <header className="header">
        <h1>
          <span className="logo-icon">⚡</span>
          DispatchAI
          <span className="dashboard-text">Dashboard</span>
        </h1>
        <div className="header-controls">
          {isAuthenticated && (
            <div className="tabs">
              <button
                onClick={() => setActiveTab('issues')}
                className={`tab ${activeTab === 'issues' ? 'active' : ''}`}
              >
                Issues
              </button>
              <button
                onClick={() => setActiveTab('repositories')}
                className={`tab ${activeTab === 'repositories' ? 'active' : ''}`}
              >
                Repositories
              </button>
            </div>
          )}
          <button
            onClick={toggleTheme}
            className="theme-toggle"
            aria-label={`Switch to ${isDarkMode ? 'light' : 'dark'} mode`}
          >
            {isDarkMode ? '☀️' : '🌙'}
          </button>
          <LoginButton />
          <div className="connection-status">
            <span className={`status-indicator ${connectionStatus}`}></span>
            <span>WebSocket: {connectionStatus}</span>
          </div>
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

      {stats && (stats.categories.length > 0 || stats.priorities.length > 0) && (
        <div className="analytics-container">
          <h2>Analytics</h2>
          <div className="charts-grid">
            {stats.categories.length > 0 && (
              <div className="chart-card">
                <h3>Categories</h3>
                <div className="chart">
                  {stats.categories.map((category) => {
                    const percentage = stats.total_issues > 0 ? (category.count / stats.total_issues) * 100 : 0
                    return (
                      <div key={category.name} className="chart-bar">
                        <div className="bar-label">
                          <span className="category-name">{category.name}</span>
                          <span className="category-count">{category.count}</span>
                        </div>
                        <div className="bar-container">
                          <div
                            className="bar-fill category-bar"
                            style={{ width: `${percentage}%` }}
                          ></div>
                        </div>
                        <span className="percentage">{Math.round(percentage)}%</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}

            {stats.priorities.length > 0 && (
              <div className="chart-card">
                <h3>Priorities</h3>
                <div className="chart">
                  {stats.priorities.map((priority) => {
                    const percentage = stats.total_issues > 0 ? (priority.count / stats.total_issues) * 100 : 0
                    const priorityColor = getPriorityColor(priority.name)
                    return (
                      <div key={priority.name} className="chart-bar">
                        <div className="bar-label">
                          <span className="priority-name">{priority.name}</span>
                          <span className="priority-count">{priority.count}</span>
                        </div>
                        <div className="bar-container">
                          <div
                            className="bar-fill priority-bar"
                            style={{
                              width: `${percentage}%`,
                              backgroundColor: priorityColor
                            }}
                          ></div>
                        </div>
                        <span className="percentage">{Math.round(percentage)}%</span>
                      </div>
                    )
                  })}
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {activeTab === 'repositories' ? (
        <RepositoryManager />
      ) : (
        <div className="issues-container">
          <div className="issues-header">
            <h2>Recent Issues</h2>
            <div className="filters-group">
              <div className="filter-item">
                <label htmlFor="repo-filter">Repository:</label>
                <select
                  id="repo-filter"
                  value={selectedRepo}
                  onChange={(e) => setSelectedRepo(e.target.value)}
                  className="filter-select"
                >
                  <option value="all">All Repositories</option>
                  {repositories.map(repo => (
                    <option key={repo.id} value={repo.full_name}>
                      {repo.full_name}
                      {repo.is_public_dashboard && ' 🌐'}
                    </option>
                  ))}
                </select>
              </div>
              
              <div className="filter-item">
                <label htmlFor="category-filter">Category:</label>
                <select
                  id="category-filter"
                  value={filterCategory}
                  onChange={(e) => setFilterCategory(e.target.value)}
                  className="filter-select"
                >
                  <option value="all">All Categories</option>
                  <option value="bug">Bug</option>
                  <option value="feature">Feature</option>
                  <option value="enhancement">Enhancement</option>
                  <option value="documentation">Documentation</option>
                  <option value="question">Question</option>
                </select>
              </div>
              
              <div className="filter-item">
                <label htmlFor="priority-filter">Priority:</label>
                <select
                  id="priority-filter"
                  value={filterPriority}
                  onChange={(e) => setFilterPriority(e.target.value)}
                  className="filter-select"
                >
                  <option value="all">All Priorities</option>
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>
              
              <div className="filter-item">
                <label htmlFor="sort-by">Sort By:</label>
                <select
                  id="sort-by"
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value as 'date' | 'priority' | 'status')}
                  className="filter-select"
                >
                  <option value="date">Date (Newest)</option>
                  <option value="priority">Priority</option>
                  <option value="status">Status</option>
                </select>
              </div>
            </div>
          </div>
          {(() => {
            let filteredIssues = issues.filter(issue => {
              const repoMatch = selectedRepo === 'all' || issue.repository === selectedRepo.split('/')[1]
              const categoryMatch = filterCategory === 'all' || issue.category === filterCategory
              const priorityMatch = filterPriority === 'all' || issue.priority === filterPriority
              return repoMatch && categoryMatch && priorityMatch
            })
            
            filteredIssues = [...filteredIssues].sort((a, b) => {
              if (sortBy === 'date') {
                return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
              } else if (sortBy === 'priority') {
                const priorityOrder = { critical: 0, high: 1, medium: 2, low: 3 }
                const aPriority = priorityOrder[a.priority as keyof typeof priorityOrder] ?? 999
                const bPriority = priorityOrder[b.priority as keyof typeof priorityOrder] ?? 999
                return aPriority - bPriority
              } else if (sortBy === 'status') {
                const statusOrder = { pending: 0, classified: 1 }
                const aStatus = statusOrder[a.status as keyof typeof statusOrder] ?? 999
                const bStatus = statusOrder[b.status as keyof typeof statusOrder] ?? 999
                return aStatus - bStatus
              }
              return 0
            })
            
            if (selectedRepo === 'all') {
              const groupedByRepo = filteredIssues.reduce((acc, issue) => {
                const repoName = issue.repository
                if (!acc[repoName]) acc[repoName] = []
                acc[repoName].push(issue)
                return acc
              }, {} as Record<string, Issue[]>)
              
              return Object.entries(groupedByRepo).map(([repoName, repoIssues]) => {
                const repo = repositories.find(r => r.name === repoName)
                return (
                  <div key={repoName} className="repository-section">
                    <h3 className="repository-section-header">
                      {repo?.full_name || repoName}
                      {repo?.is_public_dashboard && <span className="repo-badge-header">🌐 Public</span>}
                      <span className="issue-count-badge">{repoIssues.length}</span>
                    </h3>
                    <div className="issues-list">
                      {repoIssues.map(issue => (
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
                <span className="repository">
                  {issue.repository}
                  {repositories.find(r => r.name === issue.repository)?.is_public_dashboard && (
                    <span className="repo-badge" title="Public Dashboard">🌐</span>
                  )}
                </span>
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
                  disabled={issue.status === 'classified' || editingIssue?.id === issue.id}
                >
                  {issue.status === 'classified' ? 'Classified' : 'Classify'}
                </button>
                {editingIssue?.id === issue.id ? (
                  <div className="editing-controls">
                    <button
                      onClick={saveCorrection}
                      className="save-btn"
                      disabled={isSubmitting}
                    >
                      {isSubmitting ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      onClick={cancelEditing}
                      className="cancel-btn"
                      disabled={isSubmitting}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => startEditing(issue)}
                    className="edit-btn"
                  >
                    Edit
                  </button>
                )}
              </div>

              {editingIssue?.id === issue.id && (
                <div className="editing-form">
                  <div className="form-group">
                    <label>Category:</label>
                    <select
                      value={editingIssue.category}
                      onChange={(e) => setEditingIssue({ ...editingIssue, category: e.target.value })}
                    >
                      <option value="">Select category...</option>
                      <option value="bug">Bug</option>
                      <option value="feature">Feature</option>
                      <option value="enhancement">Enhancement</option>
                      <option value="documentation">Documentation</option>
                      <option value="question">Question</option>
                      <option value="duplicate">Duplicate</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Priority:</label>
                    <select
                      value={editingIssue.priority}
                      onChange={(e) => setEditingIssue({ ...editingIssue, priority: e.target.value })}
                    >
                      <option value="">Select priority...</option>
                      <option value="critical">Critical</option>
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Tags (comma-separated):</label>
                    <input
                      type="text"
                      value={editingIssue.tags}
                      onChange={(e) => setEditingIssue({ ...editingIssue, tags: e.target.value })}
                      placeholder="frontend, ui, urgent"
                    />
                  </div>
                </div>
              )}
            </div>
          ))}
                    </div>
                  </div>
                )
              })
            } else {
              return (
                <div className="issues-list">
                  {filteredIssues.map(issue => (
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
                <span className="repository">
                  {issue.repository}
                  {repositories.find(r => r.name === issue.repository)?.is_public_dashboard && (
                    <span className="repo-badge" title="Public Dashboard">🌐</span>
                  )}
                </span>
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
                  disabled={issue.status === 'classified' || editingIssue?.id === issue.id}
                >
                  {issue.status === 'classified' ? 'Classified' : 'Classify'}
                </button>
                {editingIssue?.id === issue.id ? (
                  <div className="editing-controls">
                    <button
                      onClick={saveCorrection}
                      className="save-btn"
                      disabled={isSubmitting}
                    >
                      {isSubmitting ? 'Saving...' : 'Save'}
                    </button>
                    <button
                      onClick={cancelEditing}
                      className="cancel-btn"
                      disabled={isSubmitting}
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    onClick={() => startEditing(issue)}
                    className="edit-btn"
                  >
                    Edit
                  </button>
                )}
              </div>

              {editingIssue?.id === issue.id && (
                <div className="editing-form">
                  <div className="form-group">
                    <label>Category:</label>
                    <select
                      value={editingIssue.category}
                      onChange={(e) => setEditingIssue({ ...editingIssue, category: e.target.value })}
                    >
                      <option value="">Select category...</option>
                      <option value="bug">Bug</option>
                      <option value="feature">Feature</option>
                      <option value="enhancement">Enhancement</option>
                      <option value="documentation">Documentation</option>
                      <option value="question">Question</option>
                      <option value="duplicate">Duplicate</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Priority:</label>
                    <select
                      value={editingIssue.priority}
                      onChange={(e) => setEditingIssue({ ...editingIssue, priority: e.target.value })}
                    >
                      <option value="">Select priority...</option>
                      <option value="critical">Critical</option>
                      <option value="high">High</option>
                      <option value="medium">Medium</option>
                      <option value="low">Low</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Tags (comma-separated):</label>
                    <input
                      type="text"
                      value={editingIssue.tags}
                      onChange={(e) => setEditingIssue({ ...editingIssue, tags: e.target.value })}
                      placeholder="frontend, ui, urgent"
                    />
                  </div>
                </div>
              )}
            </div>
          ))}
                </div>
              )
            }
          })()}
        </div>
      )}
    </div>
  )
}

function App() {
  return (
    <AuthProvider>
      <DashboardContent />
    </AuthProvider>
  );
}

export default App
