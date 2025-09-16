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

interface SyncResult {
  success: boolean;
  issues_fetched: number;
  issues_stored: number;
  error_message?: string;
}

const RepositoryManager: React.FC = () => {
  const { token, isAuthenticated } = useAuth();
  const [repositories, setRepositories] = useState<Repository[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncingRepos, setSyncingRepos] = useState<Set<string>>(new Set());

  const fetchRepositories = async () => {
    if (!isAuthenticated || !token) return;

    setIsLoading(true);
    setError(null);

    try {
      const authUrl = import.meta.env.VITE_AUTH_URL || 'http://localhost:8003';
      const response = await fetch(`${authUrl}/auth/user/repositories`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        throw new Error('Failed to fetch repositories');
      }

      const data = await response.json();
      setRepositories(data);
    } catch (err) {
      console.error('Error fetching repositories:', err);
      setError('Failed to load repositories');
    } finally {
      setIsLoading(false);
    }
  };

  const syncRepository = async (repo: Repository) => {
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
        // Refresh repositories to get updated sync status
        await fetchRepositories();
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
      fetchRepositories();
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
          onClick={fetchRepositories}
          disabled={isLoading}
          className="refresh-btn"
        >
          {isLoading ? 'Loading...' : 'Refresh'}
        </button>
      </div>

      {error && (
        <div className="error-message">
          {error}
        </div>
      )}

      {isLoading ? (
        <div className="loading-container">
          <div className="loading-spinner"></div>
          <p>Loading repositories...</p>
        </div>
      ) : (
        <div className="repositories-list">
          {repositories.length === 0 ? (
            <div className="no-repositories">
              <p>No repositories found. Make sure you have access to repositories on GitHub.</p>
            </div>
          ) : (
            repositories.map((repo) => {
              const repoKey = `${repo.owner}/${repo.name}`;
              const isSyncing = syncingRepos.has(repoKey);

              return (
                <div key={repo.full_name} className="repository-card">
                  <div className="repository-header">
                    <h3 className="repository-name">{repo.full_name}</h3>
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
                      onClick={() => syncRepository(repo)}
                      disabled={isSyncing || repo.sync_status === 'syncing'}
                      className="sync-btn"
                    >
                      {isSyncing ? 'Syncing...' : 'Sync Issues'}
                    </button>
                  </div>
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