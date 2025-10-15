import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useAuth } from './useAuth'

// Types
export interface Organization {
  id: number
  login: string
  name?: string
  description?: string
  avatar_url: string
  html_url: string
  type: string
  public_repos: number
  total_private_repos?: number
  accessible_repos?: number
}

export interface Repository {
  owner: string
  name: string
  full_name: string
  permissions: {
    admin: boolean
    push: boolean
    pull: boolean
  }
  connected: boolean
  last_sync_at?: string
  issues_synced: number
  sync_status?: string
}

export interface OrganizationRepositories {
  organization: string
  repositories: Repository[]
}

export interface ConnectRepositoryRequest {
  owner: string
  name: string
  is_public: boolean
}

export interface ConnectRepositoryResponse {
  success: boolean
  message: string
  repository?: Repository
}

export interface DisconnectRepositoryResponse {
  success: boolean
  message: string
}

export interface SyncResult {
  success: boolean
  issues_fetched: number
  issues_stored: number
  error_message?: string
}

// API functions
const getApiUrl = () => import.meta.env.VITE_API_URL || 'http://localhost:8002'

const authenticatedFetch = async (url: string, options: RequestInit = {}, token?: string) => {
  const headers = {
    'Content-Type': 'application/json',
    ...(token ? { 'Authorization': `Bearer ${token}` } : {}),
    ...(options.headers || {}),
  }

  const response = await fetch(url, {
    ...options,
    headers,
  })

  if (!response.ok) {
    const errorText = await response.text()
    throw new Error(`${response.status}: ${errorText}`)
  }

  return response.json()
}

// Query keys
export const repositoryKeys = {
  all: ['repositories'] as const,
  organizations: () => [...repositoryKeys.all, 'organizations'] as const,
  organization: (orgLogin: string) => [...repositoryKeys.organizations(), orgLogin] as const,
  organizationRepos: (orgLogin: string) => [...repositoryKeys.organization(orgLogin), 'repos'] as const,
}

// Custom hooks
export const useOrganizations = () => {
  const { token } = useAuth()

  return useQuery({
    queryKey: repositoryKeys.organizations(),
    queryFn: async (): Promise<Organization[]> => {
      if (!token) throw new Error('No authentication token')
      return authenticatedFetch(`${getApiUrl()}/api/organizations`, {}, token)
    },
    enabled: !!token,
    staleTime: 2 * 60 * 1000, // 2 minutes - organizations change infrequently
  })
}

export const useOrganizationRepositories = (orgLogin: string, enabled: boolean = true) => {
  const { token } = useAuth()

  return useQuery({
    queryKey: repositoryKeys.organizationRepos(orgLogin),
    queryFn: async (): Promise<OrganizationRepositories> => {
      if (!token) throw new Error('No authentication token')
      return authenticatedFetch(`${getApiUrl()}/api/organizations/${orgLogin}/repositories`, {}, token)
    },
    enabled: !!token && enabled,
    staleTime: 1 * 60 * 1000, // 1 minute - repository lists change more frequently
  })
}

export const useConnectRepository = () => {
  const { token } = useAuth()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async (request: ConnectRepositoryRequest): Promise<ConnectRepositoryResponse> => {
      if (!token) throw new Error('No authentication token')
      return authenticatedFetch(`${getApiUrl()}/api/repos/connect`, {
        method: 'POST',
        body: JSON.stringify(request),
      }, token)
    },
    onMutate: async (variables) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({
        queryKey: repositoryKeys.organizationRepos(variables.owner)
      })

      // Snapshot the previous value
      const previousRepos = queryClient.getQueryData<OrganizationRepositories>(
        repositoryKeys.organizationRepos(variables.owner)
      )

      // Optimistically update to show repository as connected
      if (previousRepos) {
        queryClient.setQueryData<OrganizationRepositories>(
          repositoryKeys.organizationRepos(variables.owner),
          {
            ...previousRepos,
            repositories: previousRepos.repositories.map(repo =>
              repo.full_name === `${variables.owner}/${variables.name}`
                ? { ...repo, connected: true }
                : repo
            )
          }
        )
      }

      // Return a context object with the snapshotted value
      return { previousRepos }
    },
    onError: (_err, variables, context) => {
      // If the mutation fails, use the context returned from onMutate to roll back
      if (context?.previousRepos) {
        queryClient.setQueryData(
          repositoryKeys.organizationRepos(variables.owner),
          context.previousRepos
        )
      }
    },
    onSuccess: (data, variables) => {
      if (data.success) {
        // Invalidate and refetch to ensure we have the latest data
        queryClient.invalidateQueries({
          queryKey: repositoryKeys.organizationRepos(variables.owner)
        })
        // Also invalidate organizations to update counts
        queryClient.invalidateQueries({
          queryKey: repositoryKeys.organizations()
        })
      }
    },
  })
}

export const useDisconnectRepository = () => {
  const { token } = useAuth()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ owner, repo }: { owner: string; repo: string }): Promise<DisconnectRepositoryResponse> => {
      if (!token) throw new Error('No authentication token')
      return authenticatedFetch(`${getApiUrl()}/api/repos/${owner}/${repo}`, {
        method: 'DELETE',
      }, token)
    },
    onMutate: async (variables) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({
        queryKey: repositoryKeys.organizationRepos(variables.owner)
      })

      // Snapshot the previous value
      const previousRepos = queryClient.getQueryData<OrganizationRepositories>(
        repositoryKeys.organizationRepos(variables.owner)
      )

      // Optimistically update to show repository as disconnected
      if (previousRepos) {
        queryClient.setQueryData<OrganizationRepositories>(
          repositoryKeys.organizationRepos(variables.owner),
          {
            ...previousRepos,
            repositories: previousRepos.repositories.map(repo =>
              repo.full_name === `${variables.owner}/${variables.repo}`
                ? { ...repo, connected: false, sync_status: undefined, last_sync_at: undefined, issues_synced: 0 }
                : repo
            )
          }
        )
      }

      // Return a context object with the snapshotted value
      return { previousRepos }
    },
    onError: (_err, variables, context) => {
      // If the mutation fails, use the context returned from onMutate to roll back
      if (context?.previousRepos) {
        queryClient.setQueryData(
          repositoryKeys.organizationRepos(variables.owner),
          context.previousRepos
        )
      }
    },
    onSuccess: (data, variables) => {
      if (data.success) {
        // Invalidate and refetch to ensure we have the latest data
        queryClient.invalidateQueries({
          queryKey: repositoryKeys.organizationRepos(variables.owner)
        })
        // Also invalidate organizations to update counts
        queryClient.invalidateQueries({
          queryKey: repositoryKeys.organizations()
        })
      }
    },
  })
}

export const useSyncRepository = () => {
  const { token } = useAuth()
  const queryClient = useQueryClient()

  return useMutation({
    mutationFn: async ({ owner, repo }: { owner: string; repo: string }): Promise<SyncResult> => {
      if (!token) throw new Error('No authentication token')
      return authenticatedFetch(`${getApiUrl()}/repos/${owner}/${repo}/sync`, {
        method: 'POST',
      }, token)
    },
    onMutate: async (variables) => {
      // Cancel any outgoing refetches
      await queryClient.cancelQueries({
        queryKey: repositoryKeys.organizationRepos(variables.owner)
      })

      // Snapshot the previous value
      const previousRepos = queryClient.getQueryData<OrganizationRepositories>(
        repositoryKeys.organizationRepos(variables.owner)
      )

      // Optimistically update to show repository as syncing
      if (previousRepos) {
        queryClient.setQueryData<OrganizationRepositories>(
          repositoryKeys.organizationRepos(variables.owner),
          {
            ...previousRepos,
            repositories: previousRepos.repositories.map(repo =>
              repo.full_name === `${variables.owner}/${variables.repo}`
                ? { ...repo, sync_status: 'syncing' }
                : repo
            )
          }
        )
      }

      // Return a context object with the snapshotted value
      return { previousRepos }
    },
    onError: (_err, variables, context) => {
      // If the mutation fails, use the context returned from onMutate to roll back
      if (context?.previousRepos) {
        queryClient.setQueryData(
          repositoryKeys.organizationRepos(variables.owner),
          context.previousRepos
        )
      }
    },
    onSuccess: (data, variables) => {
      if (data.success) {
        // Invalidate and refetch to ensure we have the latest data
        queryClient.invalidateQueries({
          queryKey: repositoryKeys.organizationRepos(variables.owner)
        })
      }
    },
  })
}