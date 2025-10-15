# Repository Loading Performance Optimization Plan

## Overview
This document outlines the comprehensive optimization plan to improve repository loading performance in the DispatchAI dashboard, addressing slow UX when adding repositories.

## Current Performance Issues

### 1. Sequential API Calls (N+1 Problem)
- `get_user_organizations` fetches organizations first, then makes individual API calls to get accessible repository counts for each org
- Each organization expansion triggers a separate GitHub API call
- No caching means every page load hits GitHub APIs fresh

### 2. Inefficient Data Fetching
- `get_organization_repositories` fetches all repos then filters for accessible ones client-side
- Multiple database queries per repository for sync/connection status
- No pagination - loads all repositories at once

### 3. Poor State Management
- Multiple separate state variables (`organizations`, `organizationRepos`, `loadingRepos`, etc.)
- No optimistic updates for user actions
- State updates trigger unnecessary re-renders

### 4. No Caching Strategy
- Fresh API calls on every component mount/refetch
- No background refresh or stale-while-revalidate patterns

## Optimization Implementation Plan

### Phase 1: Foundation (High Priority)

#### 1.1 React Query Integration
- Install and configure TanStack Query
- Set up QueryClient with appropriate defaults
- Replace manual state management with React Query hooks
- Implement automatic caching, background refetching, and error handling

#### 1.2 Backend API Optimizations
- **Parallel Organization Repository Counts**: Modify `get_user_organizations` to fetch accessible repo counts in parallel using asyncio.gather()
- **Database Query Batching**: Batch sync status and connection status queries instead of per-repository queries
- **Response Caching**: Add Redis/memory cache for GitHub API responses

### Phase 2: State Management & UX (Medium Priority)

#### 2.1 State Consolidation
Replace multiple state variables with normalized structure:
```typescript
interface RepositoryState {
  organizations: Map<string, Organization>;
  repositories: Map<string, Repository[]>;
  loadingStates: Map<string, 'idle' | 'loading' | 'error'>;
  lastFetched: Map<string, Date>;
}
```

#### 2.2 Optimistic Updates
- Immediately update UI state for connect/disconnect/sync actions
- Rollback on failure with proper error handling
- Show loading states without blocking UI

### Phase 3: Scale & Performance (Medium Priority)

#### 3.1 Pagination & Virtual Scrolling
- Implement cursor-based pagination for large organizations
- Add virtual scrolling for repository lists
- Load repositories on-demand with intersection observer

#### 3.2 Smart Loading Strategies
- Pre-load user's most recently accessed organizations
- Cache organization metadata separately from repository lists
- Implement incremental loading for large repositories

## Expected Performance Improvements

- **Initial Load**: 60-80% faster through parallel API calls and caching
- **Organization Expansion**: Near-instantaneous for cached data, 50% faster for fresh loads
- **Memory Usage**: Reduced through pagination and selective loading
- **User Experience**: Immediate feedback with optimistic updates, no blocking operations

## Implementation Timeline

### Week 1: Foundation
- [ ] Install and configure TanStack Query
- [ ] Set up QueryClient provider
- [ ] Migrate RepositoryManager to use React Query hooks
- [ ] Implement basic caching

### Week 2: Backend Optimizations
- [ ] Parallelize organization repository count fetching
- [ ] Batch database queries for sync/connection status
- [ ] Add response caching layer

### Week 3: UX Improvements
- [ ] Implement optimistic updates
- [ ] Consolidate state management
- [ ] Add loading states and error boundaries

### Week 4: Scale Features
- [ ] Implement pagination for large organizations
- [ ] Add virtual scrolling
- [ ] Performance testing and optimization

## Success Metrics

- Initial page load time < 3 seconds
- Organization expansion < 1 second (cached), < 2 seconds (fresh)
- Memory usage reduced by 40%
- No blocking UI operations
- Improved error handling and recovery

## Risk Mitigation

- Gradual rollout with feature flags
- Comprehensive testing of caching behavior
- Fallback to original implementation if issues arise
- Performance monitoring and alerting

## Dependencies

- TanStack Query v5+
- Redis for caching (optional, can use in-memory)
- Updated backend APIs for batched operations</content>
</xai:function_call">## Repository Loading Performance Optimization Plan

## Overview
This document outlines the comprehensive optimization plan to improve repository loading performance in the DispatchAI dashboard, addressing slow UX when adding repositories.

## Current Performance Issues

### 1. Sequential API Calls (N+1 Problem)
- `get_user_organizations` fetches organizations first, then makes individual API calls to get accessible repository counts for each org
- Each organization expansion triggers a separate GitHub API call
- No caching means every page load hits GitHub APIs fresh

### 2. Inefficient Data Fetching
- `get_organization_repositories` fetches all repos then filters for accessible ones client-side
- Multiple database queries per repository for sync/connection status
- No pagination - loads all repositories at once

### 3. Poor State Management
- Multiple separate state variables (`organizations`, `organizationRepos`, `loadingRepos`, etc.)
- No optimistic updates for user actions
- State updates trigger unnecessary re-renders

### 4. No Caching Strategy
- Fresh API calls on every component mount/refetch
- No background refresh or stale-while-revalidate patterns

## Optimization Implementation Plan

### Phase 1: Foundation (High Priority)

#### 1.1 React Query Integration
- Install and configure TanStack Query
- Set up QueryClient with appropriate defaults
- Replace manual state management with React Query hooks
- Implement automatic caching, background refetching, and error handling

#### 1.2 Backend API Optimizations
- **Parallel Organization Repository Counts**: Modify `get_user_organizations` to fetch accessible repo counts in parallel using asyncio.gather()
- **Database Query Batching**: Batch sync status and connection status queries instead of per-repository queries
- **Response Caching**: Add Redis/memory cache for GitHub API responses

### Phase 2: State Management & UX (Medium Priority)

#### 2.1 State Consolidation
Replace multiple state variables with normalized structure:
```typescript
interface RepositoryState {
  organizations: Map<string, Organization>;
  repositories: Map<string, Repository[]>;
  loadingStates: Map<string, 'idle' | 'loading' | 'error'>;
  lastFetched: Map<string, Date>;
}
```

#### 2.2 Optimistic Updates
- Immediately update UI state for connect/disconnect/sync actions
- Rollback on failure with proper error handling
- Show loading states without blocking UI

### Phase 3: Scale & Performance (Medium Priority)

#### 3.1 Pagination & Virtual Scrolling
- Implement cursor-based pagination for large organizations
- Add virtual scrolling for repository lists
- Load repositories on-demand with intersection observer

#### 3.2 Smart Loading Strategies
- Pre-load user's most recently accessed organizations
- Cache organization metadata separately from repository lists
- Implement incremental loading for large repositories

## Expected Performance Improvements

- **Initial Load**: 60-80% faster through parallel API calls and caching
- **Organization Expansion**: Near-instantaneous for cached data, 50% faster for fresh loads
- **Memory Usage**: Reduced through pagination and selective loading
- **User Experience**: Immediate feedback with optimistic updates, no blocking operations

## Implementation Timeline

### Week 1: Foundation
- [ ] Install and configure TanStack Query
- [ ] Set up QueryClient provider
- [ ] Migrate RepositoryManager to use React Query hooks
- [ ] Implement basic caching

### Week 2: Backend Optimizations
- [ ] Parallelize organization repository count fetching
- [ ] Batch database queries for sync/connection status
- [ ] Add response caching layer

### Week 3: UX Improvements
- [ ] Implement optimistic updates
- [ ] Consolidate state management
- [ ] Add loading states and error boundaries

### Week 4: Scale Features
- [ ] Implement pagination for large organizations
- [ ] Add virtual scrolling
- [ ] Performance testing and optimization

## Success Metrics

- Initial page load time < 3 seconds
- Organization expansion < 1 second (cached), < 2 seconds (fresh)
- Memory usage reduced by 40%
- No blocking UI operations
- Improved error handling and recovery

## Risk Mitigation

- Gradual rollout with feature flags
- Comprehensive testing of caching behavior
- Fallback to original implementation if issues arise
- Performance monitoring and alerting

## Dependencies

- TanStack Query v5+
- Redis for caching (optional, can use in-memory)
- Updated backend APIs for batched operations</content>
</xai:function_call">Now let's start implementing the optimizations. I'll begin with installing TanStack Query and setting up the foundation. 

<xai:function_call name="bash">
<parameter name="command">cd dashboard && npm install @tanstack/react-query @tanstack/react-query-devtools