import React, { useState } from 'react';
import { useAuth } from '../hooks/useAuth';
import {
  useOrganizations,
  useOrganizationRepositories,
  useConnectRepository,
  useDisconnectRepository,
  useSyncRepository,
  type Organization,
  type Repository,
} from '../hooks/useRepositories';

// OrganizationCard component
interface OrganizationCardProps {
  organization: Organization;
  isExpanded: boolean;
  onToggle: () => void;
  searchTerm: string;
  connectionFilter: 'all' | 'connected' | 'not-connected';
  permissionFilter: 'all' | 'admin' | 'push' | 'pull';
  onConnectRepository: (repo: Repository) => void;
  onDisconnectRepository: (repo: Repository) => void;
  onSyncRepository: (repo: Repository) => void;
  connectingRepos: Set<string>;
  disconnectingRepos: Set<string>;
  syncingRepos: Set<string>;
  getSyncStatusColor: (status?: string) => string;
  formatLastSync: (dateString?: string) => string;
}

const OrganizationCard: React.FC<OrganizationCardProps> = ({
  organization,
  isExpanded,
  onToggle,
  searchTerm,
  connectionFilter,
  permissionFilter,
  onConnectRepository,
  onDisconnectRepository,
  onSyncRepository,
  connectingRepos,
  disconnectingRepos,
  syncingRepos,
  getSyncStatusColor,
  formatLastSync,
}) => {
  const { data: orgReposData, isLoading: isLoadingRepos, error: reposError } = useOrganizationRepositories(
    organization.login,
    isExpanded
  );

  const repos = orgReposData?.repositories || [];

  // Filter repositories based on current filter state
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

  // Don't render if no filtered repos and there's a search term
  if (searchTerm && filteredRepos.length === 0) {
    return null;
  }

  return (
    <div
      className="organization-card"
      data-expanded={isExpanded}
    >
      <div
        className="organization-header"
        onClick={onToggle}
        style={{ cursor: 'pointer' }}
      >
        <div className="organization-info">
          <img
            src={organization.avatar_url}
            alt={`${organization.login} avatar`}
            className="organization-avatar"
            width="32"
            height="32"
          />
          <div className="organization-details">
            <h3 className="organization-name">
              {organization.name || organization.login}
              <span className="organization-type">({organization.type})</span>
            </h3>
            <p className="organization-description">
              {organization.description || `${organization.accessible_repos ?? organization.public_repos} accessible repositories`}
            </p>
          </div>
        </div>
        <div className="organization-expand">
          <span className={`expand-arrow ${isExpanded ? 'expanded' : ''}`}>
            ▶
          </span>
          <span className="repo-count">{organization.accessible_repos ?? organization.public_repos} repos</span>
        </div>
      </div>

      {isExpanded && (
        <div className="organization-repositories">
          {isLoadingRepos ? (
            <div className="loading-container">
              <div className="loading-spinner"></div>
              <p>Loading repositories...</p>
            </div>
          ) : reposError ? (
            <div className="error-message">
              Failed to load repositories: {reposError.message}
            </div>
          ) : filteredRepos.length === 0 ? (
            <div className="no-repositories">
              <p>No accessible repositories found in this organization.</p>
            </div>
          ) : (
            <div className="repositories-list">
              {filteredRepos.map((repo) => {
                const repoKey = `${repo.owner}/${repo.name}`;
                const isSyncing = syncingRepos.has(repoKey);
                const isConnecting = connectingRepos.has(repoKey);
                const isDisconnecting = disconnectingRepos.has(repoKey);
                const isConnected = repo.connected;

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
                           onClick={() => onConnectRepository(repo)}
                           disabled={isConnecting}
                           className="connect-btn"
                         >
                           {isConnecting ? 'Connecting...' : 'Connect Repository'}
                         </button>
                       ) : (
                         <>
                           <button
                             onClick={() => onSyncRepository(repo)}
                             disabled={isSyncing || repo.sync_status === 'syncing'}
                             className="sync-btn"
                           >
                             {isSyncing ? 'Syncing...' : 'Sync Issues'}
                           </button>
                           <button
                             onClick={() => onDisconnectRepository(repo)}
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
};

const RepositoryManager: React.FC = () => {
  const { isAuthenticated } = useAuth();

  // React Query hooks
  const {
    data: organizations = [],
    isLoading: isLoadingOrgs,
    error: orgsError,
    refetch: refetchOrganizations
  } = useOrganizations();

  const connectRepoMutation = useConnectRepository();
  const disconnectRepoMutation = useDisconnectRepository();
  const syncRepoMutation = useSyncRepository();

  // Local UI state
  const [expandedOrgs, setExpandedOrgs] = useState<Set<string>>(new Set());

  // Filtering state
  const [searchTerm, setSearchTerm] = useState('');
  const [connectionFilter, setConnectionFilter] = useState<'all' | 'connected' | 'not-connected'>('all');
  const [permissionFilter, setPermissionFilter] = useState<'all' | 'admin' | 'push' | 'pull'>('all');

  const toggleOrganization = (orgLogin: string) => {
    const isExpanded = expandedOrgs.has(orgLogin);

    if (isExpanded) {
      // Collapse organization
      setExpandedOrgs(prev => {
        const newSet = new Set(prev);
        newSet.delete(orgLogin);
        return newSet;
      });
    } else {
      // Expand organization
      setExpandedOrgs(prev => new Set(prev).add(orgLogin));
    }
  };

  const syncRepository = (repo: Repository) => {
    syncRepoMutation.mutate({ owner: repo.owner, repo: repo.name });
  };

  const connectRepository = (repo: Repository) => {
    connectRepoMutation.mutate({
      owner: repo.owner,
      name: repo.name,
      is_public: !repo.permissions.admin // If user doesn't have admin, assume public dashboard
    });
  };

  const disconnectRepository = (repo: Repository) => {
    disconnectRepoMutation.mutate({ owner: repo.owner, repo: repo.name });
  };

  // Error handling - combine all possible errors
  const error = orgsError?.message ||
    connectRepoMutation.error?.message ||
    disconnectRepoMutation.error?.message ||
    syncRepoMutation.error?.message;

  // Track loading states for mutations
  const connectingRepos = new Set<string>();
  const disconnectingRepos = new Set<string>();
  const syncingRepos = new Set<string>();

  // Add current mutations to loading sets
  if (connectRepoMutation.isPending && connectRepoMutation.variables) {
    connectingRepos.add(`${connectRepoMutation.variables.owner}/${connectRepoMutation.variables.name}`);
  }
  if (disconnectRepoMutation.isPending && disconnectRepoMutation.variables) {
    disconnectingRepos.add(`${disconnectRepoMutation.variables.owner}/${disconnectRepoMutation.variables.repo}`);
  }
  if (syncRepoMutation.isPending && syncRepoMutation.variables) {
    syncingRepos.add(`${syncRepoMutation.variables.owner}/${syncRepoMutation.variables.repo}`);
  }

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

  // Filter organizations based on search term (repositories are filtered per organization)
  const getFilteredOrganizations = () => {
    if (!searchTerm) return organizations;

    // If there's a search term, only show organizations that are expanded
    // The actual repository filtering will happen in the OrganizationCard component
    return organizations.filter(org => expandedOrgs.has(org.login));
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
             onClick={() => refetchOrganizations()}
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
                <p>No organizations found. Try refreshing or check your permissions.</p>
              </div>
            ) : (
              filteredOrgs.map((org) => (
                <OrganizationCard
                  key={org.login}
                  organization={org}
                  isExpanded={expandedOrgs.has(org.login)}
                  onToggle={() => toggleOrganization(org.login)}
                  searchTerm={searchTerm}
                  connectionFilter={connectionFilter}
                  permissionFilter={permissionFilter}
                  onConnectRepository={(repo) => connectRepository(repo)}
                  onDisconnectRepository={(repo) => disconnectRepository(repo)}
                  onSyncRepository={(repo) => syncRepository(repo)}
                  connectingRepos={connectingRepos}
                  disconnectingRepos={disconnectingRepos}
                  syncingRepos={syncingRepos}
                  getSyncStatusColor={getSyncStatusColor}
                  formatLastSync={formatLastSync}
                />
              ))
            );
          })()}
        </div>
      )}
      </div>
    </div>
  );
};

export default RepositoryManager;
