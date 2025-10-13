import React, { useState, useEffect, useCallback } from 'react';
import { useAuth } from '../hooks/useAuth';

interface Repository {
  owner: string;
  name: string;
  full_name: string;
  permissions: {
    admin: boolean;
    push: boolean;
    pull: boolean;
  };
  connected: boolean;
  last_sync_at?: string;
  issues_synced: number;
  sync_status?: string;
}

interface Organization {
  id: number;
  login: string;
  name?: string;
  description?: string;
  avatar_url: string;
  html_url: string;
  type: string; // "Organization" or "User"
  public_repos: number;
  total_private_repos?: number;
  accessible_repos?: number;
}

interface OrganizationRepositories {
  organization: string;
  repositories: Repository[];
}

interface SyncResult {
  success: boolean;
  issues_fetched: number;
  issues_stored: number;
  error_message?: string;
}

interface ConnectResult {
  success: boolean;
  message: string;
  repository?: Repository;
}

interface DisconnectResult {
  success: boolean;
  message: string;
}

const RepositoryManager: React.FC = () => {
  const { token, isAuthenticated } = useAuth();
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationRepos, setOrganizationRepos] = useState<Map<string, Repository[]>>(new Map());
  const [expandedOrgs, setExpandedOrgs] = useState<Set<string>>(new Set());
  const [isLoadingOrgs, setIsLoadingOrgs] = useState(false);
  const [loadingRepos, setLoadingRepos] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [syncingRepos, setSyncingRepos] = useState<Set<string>>(new Set());
  const [connectingRepos, setConnectingRepos] = useState<Set<string>>(new Set());
  const [disconnectingRepos, setDisconnectingRepos] = useState<Set<string>>(new Set());

  // Filtering state
  const [searchTerm, setSearchTerm] = useState('');
  const [connectionFilter, setConnectionFilter] = useState<'all' | 'connected' | 'not-connected'>('all');
  const [permissionFilter, setPermissionFilter] = useState<'all' | 'admin' | 'push' | 'pull'>('all');

  const fetchOrganizations = useCallback(async () => {
    if (!isAuthenticated || !token) return;

    setIsLoadingOrgs(true);
    setError(null);

    try {
      const gatewayUrl = import.meta.env.VITE_API_URL || 'http://localhost:8002';
      const response = await fetch(`${gatewayUrl}/api/organizations`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch organizations');
      }

      const data = await response.json();
      setOrganizations(data);
    } catch (err) {
      console.error('Error fetching organizations:', err);
      setError('Failed to load organizations');
    } finally {
      setIsLoadingOrgs(false);
    }
  }, [isAuthenticated, token]);

  const fetchOrganizationRepositories = async (orgLogin: string) => {
    if (!isAuthenticated || !token) return;

    setLoadingRepos(prev => new Set(prev).add(orgLogin));
    setError(null);

    try {
      const gatewayUrl = import.meta.env.VITE_API_URL || 'http://localhost:8002';
      const response = await fetch(`${gatewayUrl}/api/organizations/${orgLogin}/repositories`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error(`Failed to fetch repositories for ${orgLogin}`);
      }

      const data: OrganizationRepositories = await response.json();

      setOrganizationRepos(prev => {
        const newMap = new Map(prev);
        newMap.set(orgLogin, data.repositories);
        return newMap;
      });

    } catch (err) {
      console.error(`Error fetching repositories for ${orgLogin}:`, err);
      setError(`Failed to load repositories for ${orgLogin}`);
    } finally {
      setLoadingRepos(prev => {
        const newSet = new Set(prev);
        newSet.delete(orgLogin);
        return newSet;
      });
    }
  };

  const toggleOrganization = async (orgLogin: string) => {
    const isExpanded = expandedOrgs.has(orgLogin);

    if (isExpanded) {
      // Collapse organization
      setExpandedOrgs(prev => {
        const newSet = new Set(prev);
        newSet.delete(orgLogin);
        return newSet;
      });
    } else {
      // Expand organization - fetch repositories if not already loaded
      setExpandedOrgs(prev => new Set(prev).add(orgLogin));

      if (!organizationRepos.has(orgLogin)) {
        await fetchOrganizationRepositories(orgLogin);
      }
    }
  };

  const syncRepository = async (repo: Repository, orgLogin: string) => {
    if (!token) return;

    const repoKey = `${repo.owner}/${repo.name}`;
    setSyncingRepos(prev => new Set(prev).add(repoKey));
    setError(null);

    try {
      const authUrl = import.meta.env.VITE_AUTH_URL || 'http://localhost:8003';
      const response = await fetch(`${authUrl}/repos/${repo.owner}/${repo.name}/sync`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Sync failed');
      }

      const result: SyncResult = await response.json();

      if (result.success) {
        // Refresh repositories for this organization to get updated sync status
        await fetchOrganizationRepositories(orgLogin);
      } else {
        setError(`Sync failed: ${result.error_message}`);
      }

    } catch (err) {
      console.error('Error syncing repository:', err);
      setError(err instanceof Error ? err.message : 'Sync failed');
    } finally {
      setSyncingRepos(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoKey);
        return newSet;
      });
    }
  };

  const connectRepository = async (repo: Repository, orgLogin: string) => {
    if (!token) return;

    const repoKey = `${repo.owner}/${repo.name}`;
    setConnectingRepos(prev => new Set(prev).add(repoKey));
    setError(null);

    try {
      const gatewayUrl = import.meta.env.VITE_API_URL || 'http://localhost:8002';
      const response = await fetch(`${gatewayUrl}/api/repos/connect`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          owner: repo.owner,
          name: repo.name,
          is_public: !repo.permissions.admin // If user doesn't have admin, assume public dashboard
        }),
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Connect failed');
      }

      const result: ConnectResult = await response.json();

      if (result.success) {
        // Refresh repositories for this organization to get updated connection status
        await fetchOrganizationRepositories(orgLogin);
      } else {
        setError(`Connect failed: ${result.message}`);
      }

    } catch (err) {
      console.error('Error connecting repository:', err);
      setError(err instanceof Error ? err.message : 'Connect failed');
    } finally {
      setConnectingRepos(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoKey);
        return newSet;
      });
    }
  };

  const disconnectRepository = async (repo: Repository, orgLogin: string) => {
    if (!token) return;

    const repoKey = `${repo.owner}/${repo.name}`;
    setDisconnectingRepos(prev => new Set(prev).add(repoKey));
    setError(null);

    try {
      const gatewayUrl = import.meta.env.VITE_API_URL || 'http://localhost:8002';
      const response = await fetch(`${gatewayUrl}/api/repos/${repo.owner}/${repo.name}`, {
        method: 'DELETE',
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const errorData = await response.json();
        throw new Error(errorData.detail || 'Disconnect failed');
      }

      const result: DisconnectResult = await response.json();

      if (result.success) {
        // Refresh repositories for this organization to get updated connection status
        await fetchOrganizationRepositories(orgLogin);
      } else {
        setError(`Disconnect failed: ${result.message}`);
      }

    } catch (err) {
      console.error('Error disconnecting repository:', err);
      setError(err instanceof Error ? err.message : 'Disconnect failed');
    } finally {
      setDisconnectingRepos(prev => {
        const newSet = new Set(prev);
        newSet.delete(repoKey);
        return newSet;
      });
    }
  };

  useEffect(() => {
    if (isAuthenticated) {
      fetchOrganizations();
    }
  }, [isAuthenticated, fetchOrganizations]);

  const getSyncStatusColor = (status?: string) => {
    switch (status) {
      case 'completed': return '#22c55e';
      case 'syncing': return '#f59e0b';
      case 'failed': return '#ef4444';
      default: return '#6b7280';
    }
  };

  const formatLastSync = (dateString?: string) => {
    if (!dateString) return 'Never';
    return new Date(dateString).toLocaleDateString();
  };

  // Filter repositories based on current filter state
  const getFilteredOrganizations = () => {
    return organizations.map(org => {
      const repos = organizationRepos.get(org.login) || [];
      const filteredRepos = repos.filter(repo => {
        // Search filter
        const searchMatch = searchTerm === '' ||
          repo.full_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          repo.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
          repo.owner.toLowerCase().includes(searchTerm.toLowerCase());

        // Connection filter
        const connectionMatch = connectionFilter === 'all' ||
          (connectionFilter === 'connected' && repo.connected) ||
          (connectionFilter === 'not-connected' && !repo.connected);

        // Permission filter
        const permissionMatch = permissionFilter === 'all' ||
          (permissionFilter === 'admin' && repo.permissions.admin) ||
          (permissionFilter === 'push' && repo.permissions.push) ||
          (permissionFilter === 'pull' && repo.permissions.pull);

        return searchMatch && connectionMatch && permissionMatch;
      });

      return { ...org, filteredRepos };
    }).filter(org => org.filteredRepos.length > 0 || searchTerm === ''); // Show org if it has filtered repos or no search term
  };

  if (!isAuthenticated) {
    return (
      <div className="repository-manager">
        <div className="auth-required">
          <h2>Authentication Required</h2>
          <p>Please log in with GitHub to manage your repositories.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="repository-manager">
      <div className="repository-manager-container">
        <div className="repository-manager-header">
          <h2>Repository Management</h2>
          <button
            onClick={fetchOrganizations}
            disabled={isLoadingOrgs}
            className="refresh-btn"
          >
            {isLoadingOrgs ? 'Loading...' : 'Refresh'}
          </button>
        </div>

        <div className="filters-group">
          <div className="filter-item">
            <label htmlFor="repo-search">Search:</label>
            <input
              id="repo-search"
              type="text"
              placeholder="Search repositories..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="filter-input"
            />
          </div>

          <div className="filter-item">
            <label htmlFor="connection-filter">Connection:</label>
            <select
              id="connection-filter"
              value={connectionFilter}
              onChange={(e) => setConnectionFilter(e.target.value as 'all' | 'connected' | 'not-connected')}
              className="filter-select"
            >
              <option value="all">All</option>
              <option value="connected">Connected</option>
              <option value="not-connected">Not Connected</option>
            </select>
          </div>

          <div className="filter-item">
            <label htmlFor="permission-filter">Permission:</label>
            <select
              id="permission-filter"
              value={permissionFilter}
              onChange={(e) => setPermissionFilter(e.target.value as 'all' | 'admin' | 'push' | 'pull')}
              className="filter-select"
            >
              <option value="all">All</option>
              <option value="admin">Admin</option>
              <option value="push">Push</option>
              <option value="pull">Pull</option>
            </select>
          </div>
        </div>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {isLoadingOrgs ? (
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Loading organizations...</p>
        </div>
      ) : (
        <div className="organizations-list">
          {(() => {
            const filteredOrgs = getFilteredOrganizations();
            return filteredOrgs.length === 0 ? (
              <div className="no-organizations">
                <p>No repositories match your filters. Try adjusting your search criteria.</p>
              </div>
            ) : (
              filteredOrgs.map((org) => {
                const isExpanded = expandedOrgs.has(org.login);
                const isLoadingRepos = loadingRepos.has(org.login);
                const repos = org.filteredRepos;

              return (
                <div
                  key={org.login}
                  className="organization-card"
                  data-expanded={isExpanded}
                >
                  <div
                    className="organization-header"
                    onClick={() => toggleOrganization(org.login)}
                    style={{ cursor: 'pointer' }}
                  >
                    <div className="organization-info">
                      <img
                        src={org.avatar_url}
                        alt={`${org.login} avatar`}
                        className="organization-avatar"
                        width="32"
                        height="32"
                      />
                      <div className="organization-details">
                        <h3 className="organization-name">
                          {org.name || org.login}
                          <span className="organization-type">({org.type})</span>
                        </h3>
                        <p className="organization-description">
                          {org.description || `${org.accessible_repos ?? org.public_repos} accessible repositories`}
                        </p>
                      </div>
                    </div>
                    <div className="organization-expand">
                      <span className={`expand-arrow ${isExpanded ? 'expanded' : ''}`}>
                        ▶
                      </span>
                      <span className="repo-count">{org.accessible_repos ?? org.public_repos} repos</span>
                    </div>
                  </div>

                  {isExpanded && (
                    <div className="organization-repositories">
                      {isLoadingRepos ? (
                        <div className="loading-container">
                          <div className="loading-spinner"></div>
                          <p>Loading repositories...</p>
                        </div>
                      ) : repos.length === 0 ? (
                        <div className="no-repositories">
                          <p>No accessible repositories found in this organization.</p>
                        </div>
                      ) : (
                        <div className="repositories-list">
                          {repos.map((repo) => {
                            const repoKey = `${repo.owner}/${repo.name}`;
                            const isSyncing = syncingRepos.has(repoKey);
                            const isConnecting = connectingRepos.has(repoKey);
                            const isDisconnecting = disconnectingRepos.has(repoKey);
                            const isConnected = repo.connected; // Use proper connection status from backend

                            return (
                              <div key={repo.full_name} className="repository-card">
                                <div className="repository-header">
                                  <h4 className="repository-name">{repo.full_name}</h4>
                                  <div className="repository-permissions">
                                    {repo.permissions.admin && <span className="permission-badge admin">Admin</span>}
                                    {repo.permissions.push && <span className="permission-badge push">Push</span>}
                                    {repo.permissions.pull && <span className="permission-badge pull">Pull</span>}
                                  </div>
                                </div>

                                <div className="repository-stats">
                                  <div className="stat">
                                    <span className="stat-label">Connection:</span>
                                    <span className={`stat-value connection-status ${isConnected ? 'connected' : 'not-connected'}`}>
                                      {isConnected ? 'Connected' : 'Not Connected'}
                                    </span>
                                  </div>
                                  <div className="stat">
                                    <span className="stat-label">Last Sync:</span>
                                    <span className="stat-value">{formatLastSync(repo.last_sync_at)}</span>
                                  </div>
                                  <div className="stat">
                                    <span className="stat-label">Issues Synced:</span>
                                    <span className="stat-value">{repo.issues_synced}</span>
                                  </div>
                                  {repo.sync_status && (
                                    <div className="stat">
                                      <span className="stat-label">Sync Status:</span>
                                      <span
                                        className="sync-status"
                                        style={{ color: getSyncStatusColor(repo.sync_status) }}
                                      >
                                        {repo.sync_status}
                                      </span>
                                    </div>
                                  )}
                                </div>

                                <div className="repository-actions">
                                  {!isConnected ? (
                                    <button
                                      onClick={() => connectRepository(repo, org.login)}
                                      disabled={isConnecting}
                                      className="connect-btn"
                                    >
                                      {isConnecting ? 'Connecting...' : 'Connect Repository'}
                                    </button>
                                  ) : (
                                    <>
                                      <button
                                        onClick={() => syncRepository(repo, org.login)}
                                        disabled={isSyncing || repo.sync_status === 'syncing'}
                                        className="sync-btn"
                                      >
                                        {isSyncing ? 'Syncing...' : 'Sync Issues'}
                                      </button>
                                      <button
                                        onClick={() => disconnectRepository(repo, org.login)}
                                        disabled={isDisconnecting}
                                        className="disconnect-btn"
                                      >
                                        {isDisconnecting ? 'Disconnecting...' : 'Disconnect'}
                                      </button>
                                    </>
                                  )}
                                </div>
                              </div>
                            );
                          })}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })
            );
          })()}
        </div>
      )}
      </div>
    </div>
  );
};

export default RepositoryManager;
