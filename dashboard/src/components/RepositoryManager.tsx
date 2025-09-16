import React, { useState, useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';

interface Repository {
  owner: string;
  name: string;
  full_name: string;
  permissions: {
    admin: boolean;
    push: boolean;
    pull: boolean;
  };
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

const RepositoryManager: React.FC = () => {
  const { token, isAuthenticated } = useAuth();
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [organizationRepos, setOrganizationRepos] = useState<Map<string, Repository[]>>(new Map());
  const [expandedOrgs, setExpandedOrgs] = useState<Set<string>>(new Set());
  const [isLoadingOrgs, setIsLoadingOrgs] = useState(false);
  const [loadingRepos, setLoadingRepos] = useState<Set<string>>(new Set());
  const [error, setError] = useState<string | null>(null);
  const [syncingRepos, setSyncingRepos] = useState<Set<string>>(new Set());

  const fetchOrganizations = async () => {
    if (!isAuthenticated || !token) return;

    setIsLoadingOrgs(true);
    setError(null);

    try {
      const gatewayUrl = import.meta.env.VITE_GATEWAY_URL || 'http://localhost:8002';
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
  };

  const fetchOrganizationRepositories = async (orgLogin: string) => {
    if (!isAuthenticated || !token) return;

    setLoadingRepos(prev => new Set(prev).add(orgLogin));
    setError(null);

    try {
      const gatewayUrl = import.meta.env.VITE_GATEWAY_URL || 'http://localhost:8002';
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

  useEffect(() => {
    if (isAuthenticated) {
      fetchOrganizations();
    }
  }, [isAuthenticated]);

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
          {organizations.length === 0 ? (
            <div className="no-organizations">
              <p>No organizations found. Make sure you have access to repositories on GitHub.</p>
            </div>
          ) : (
            organizations.map((org) => {
              const isExpanded = expandedOrgs.has(org.login);
              const isLoadingRepos = loadingRepos.has(org.login);
              const repos = organizationRepos.get(org.login) || [];

              return (
                <div key={org.login} className="organization-card">
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
                          {org.description || `${org.public_repos} public repositories`}
                        </p>
                      </div>
                    </div>
                    <div className="organization-expand">
                      <span className={`expand-arrow ${isExpanded ? 'expanded' : ''}`}>
                        ▶
                      </span>
                      <span className="repo-count">{org.public_repos} repos</span>
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
                                    <span className="stat-label">Last Sync:</span>
                                    <span className="stat-value">{formatLastSync(repo.last_sync_at)}</span>
                                  </div>
                                  <div className="stat">
                                    <span className="stat-label">Issues Synced:</span>
                                    <span className="stat-value">{repo.issues_synced}</span>
                                  </div>
                                  {repo.sync_status && (
                                    <div className="stat">
                                      <span className="stat-label">Status:</span>
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
                                  <button
                                    onClick={() => syncRepository(repo, org.login)}
                                    disabled={isSyncing || repo.sync_status === 'syncing'}
                                    className="sync-btn"
                                  >
                                    {isSyncing ? 'Syncing...' : 'Sync Issues'}
                                  </button>
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
          )}
        </div>
      )}
    </div>
  );
};

export default RepositoryManager;