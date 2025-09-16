# DispatchAI – Complete MVP Implementation Roadmap

_Created: 2025-09-16_
_Status: Planning_

---

## 🎯 Executive Summary

This roadmap defines the complete path from current state (single-tenant webhook ingestion) to a fully multi-tenant GitHub issue triaging platform with authentication, repository management, and cross-repo analytics.

**Core Value Proposition:** Allow any GitHub user to sign in, connect repositories (their own or public ones), automatically classify issues using LLMs, and provide intelligent filtering/search across all their connected repositories.

---

## 🏗️ Current State Assessment

✅ **What we have:**
- Event-driven microservices (ingress → kafka → classifier → gateway → dashboard)
- LLM-powered issue classification with confidence scoring
- Embeddings for similarity search (pgvector)
- Real-time streaming to React dashboard
- Human-in-the-loop editing capability
- Basic auth service foundation already created

🔄 **What needs enhancement:**
- Multi-tenancy and user management
- Repository connection workflow
- Public/private dashboard visibility controls
- Cross-repository filtering and search
- Production-ready authentication flow

---

## 🗺️ Implementation Phases

### Phase 1: Authentication Foundation (Week 1)
**Goal:** Enable secure GitHub OAuth login with persistent sessions

#### 1.1 Environment Setup
- [ ] Configure GitHub OAuth App credentials
- [ ] Add environment variables: `GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`, `JWT_SECRET`, `ENCRYPTION_KEY`
- [ ] Update docker-compose with auth service secrets
- [ ] **CRITICAL:** Implement proper token encryption in storage.py (currently storing GitHub tokens in plain text)

#### 1.2 Auth Service Enhancement
- [ ] **CRITICAL:** Replace placeholder encryption methods with proper encryption using `cryptography` library
- [ ] Integrate GitHub OAuth flow in existing `auth` service
- [ ] Implement JWT token generation (15-min access + 7-day refresh)
- [ ] Create user registration/login endpoints
- [ ] Add token verification middleware for other services

#### 1.3 Database Schema
```sql
-- Core authentication tables
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    github_id INTEGER UNIQUE NOT NULL,
    github_login VARCHAR(255) NOT NULL,
    avatar_url TEXT,
    email VARCHAR(255),
    created_at TIMESTAMP DEFAULT NOW()
);

-- Repository registry (global, shared across users)
CREATE TABLE repositories (
    id SERIAL PRIMARY KEY,
    github_repo_id BIGINT UNIQUE NOT NULL, -- GitHub's immutable repo ID
    owner VARCHAR(255) NOT NULL,
    name VARCHAR(255) NOT NULL,
    private BOOLEAN DEFAULT FALSE,
    is_public_dashboard BOOLEAN DEFAULT FALSE, -- Allow unauthenticated access
    created_at TIMESTAMP DEFAULT NOW(),
    UNIQUE(owner, name)
);

-- Many-to-many: users can connect to multiple repos
CREATE TABLE user_repositories (
    user_id INTEGER REFERENCES users(id),
    repo_id INTEGER REFERENCES repositories(id),
    role VARCHAR(50) DEFAULT 'viewer', -- 'owner', 'viewer'
    can_write BOOLEAN DEFAULT FALSE,
    added_at TIMESTAMP DEFAULT NOW(),
    PRIMARY KEY (user_id, repo_id)
);
```

#### 1.4 Frontend Integration
- [ ] Update React dashboard with AuthContext
- [ ] Add login/logout UI components
- [ ] Implement token storage and automatic refresh
- [ ] Add protected route handling

**Success Criteria:** User can sign in with GitHub, receive a JWT, see their profile in the dashboard

---

### Phase 2: Repository Management (Week 2)
**Goal:** Allow users to connect and manage repositories

#### 2.1 GitHub Integration Service
- [ ] Create GitHub API client with user token support
- [ ] Implement repository listing (user's repos + organizations)
- [ ] Add public repository URL validation and metadata fetching
- [ ] Handle GitHub API rate limiting

#### 2.2 Repository Connection Workflow
- [ ] Build repository selection UI component
- [ ] Add "Connect Repository" flow for user's repos
- [ ] Add "Add Public Repository" flow for any GitHub URL
- [ ] Implement repository deduplication logic

#### 2.3 Backend Repository Management
- [ ] Create repository CRUD endpoints in gateway service
- [ ] Add repository validation and GitHub metadata sync
- [ ] Implement bulk issue import for newly connected repos
- [ ] Add repository removal/disconnect functionality

#### 2.4 Issue Import System
- [ ] Create async job system for bulk GitHub issue import
- [ ] Modify existing classifier to handle both webhook and batch imports
- [ ] Add import status tracking and user notifications
- [ ] Ensure no duplicate processing for existing issues

**Success Criteria:** User can connect multiple repositories, trigger bulk import, and see all issues being classified

---

### Phase 3: Multi-Tenant Dashboard (Week 3)
**Goal:** Secure, user-specific dashboards with proper visibility controls

#### 3.1 Access Control Implementation
- [ ] Add JWT verification to gateway websocket connections
- [ ] Filter issue streams based on user's connected repositories
- [ ] Implement repository-level access checks for private repos
- [ ] Create public dashboard endpoints (no auth required)

#### 3.2 Dashboard Repository Management
- [ ] Add repository switcher/navigation in UI
- [ ] Show repository connection status and metadata
- [ ] Implement repository disconnect functionality
- [ ] Add repository sharing controls (public/private toggle)

#### 3.3 Enhanced Issue Display
- [ ] Group issues by repository in the dashboard
- [ ] Add repository-specific filtering and sorting
- [ ] Show repository metadata (private/public status, last sync)
- [ ] Implement repository-specific issue counts and stats

#### 3.4 Public Dashboard Sharing
- [ ] Create shareable public URLs for public repositories
- [ ] Add social sharing metadata (OpenGraph, Twitter cards)
- [ ] Implement view-only mode for unauthenticated users
- [ ] Add "Connect this repository" CTA for logged-out users

**Success Criteria:** Users see only their connected repositories, public dashboards are accessible without auth, private ones require proper permissions

---

### Phase 4: Cross-Repository Analytics (Week 4)
**Goal:** Powerful filtering and search across all connected repositories

#### 4.1 Enhanced Filtering System
- [ ] Add cross-repository tag filtering
- [ ] Implement severity-based filtering (low/medium/high/critical)
- [ ] Create date range and status filters
- [ ] Add repository-specific filters (show/hide specific repos)

#### 4.2 Semantic Search & Similarity
- [ ] Implement cross-repository similarity search using embeddings
- [ ] Add "find similar issues" functionality
- [ ] Create semantic search interface with natural language queries
- [ ] Show related issues across different repositories

#### 4.3 Analytics Dashboard
- [ ] Add issue classification statistics across repositories
- [ ] Create repository comparison views
- [ ] Implement trend analysis (issues over time, tag distributions)
- [ ] Add exportable reports and insights

#### 4.4 Advanced Repository Features
- [ ] Implement repository grouping/tagging by users
- [ ] Add repository health scoring based on issue patterns
- [ ] Create repository recommendation system
- [ ] Add bulk operations across multiple repositories

**Success Criteria:** Users can efficiently filter, search, and analyze issues across all their connected repositories

---

### Phase 5: Production Hardening (Week 5)
**Goal:** Production-ready deployment and monitoring

#### 5.1 Security Enhancements
- [ ] Implement proper secret management (move from .env files)
- [ ] Add rate limiting and abuse protection
- [ ] Implement audit logging for sensitive operations
- [ ] Add CSRF protection and security headers

#### 5.2 Performance Optimization
- [ ] Add Redis caching for GitHub API responses
- [ ] Implement database query optimization
- [ ] Add CDN for static assets
- [ ] Optimize embeddings storage and retrieval

#### 5.3 Monitoring & Observability
- [ ] Add health check endpoints for all services
- [ ] Implement structured logging across services
- [ ] Add metrics collection (Prometheus/Grafana)
- [ ] Create alerting for critical failures

#### 5.4 Deployment & CI/CD
- [ ] Set up automated testing pipeline
- [ ] Implement blue-green deployment strategy
- [ ] Add database migration automation
- [ ] Create backup and disaster recovery procedures

**Success Criteria:** System runs reliably in production with proper monitoring and security

---

## 🔧 Technical Architecture Decisions

### Authentication Strategy
- **Keep dedicated auth microservice** - maintains clean boundaries, easy to swap providers later
- **GitHub OAuth as sole IdP** - zero cost, users already have accounts
- **JWT with refresh tokens** - stateless verification, secure session management
- **No external auth services** - maintains cost control and simplicity

### Multi-Tenancy Model
- **Shared repository table** - prevents duplication across users
- **User-repository join table** - flexible many-to-many relationships
- **Role-based access** - extensible for future features
- **Repository-level visibility controls** - supports both public and private dashboards

### Data Architecture
- **Preserve existing event-driven flow** - minimal changes to working system
- **Extend with user context** - add user_id to relevant events
- **Maintain embedding-based search** - leverage existing pgvector investment
- **Cross-repository indexing** - enable global search and analytics

---

## 🚨 Risk Mitigation

| Risk | Impact | Probability | Mitigation |
|------|--------|-------------|------------|
| **GitHub access tokens stored in plain text** | **Critical** | **High** | **IMMEDIATE: Implement proper encryption with cryptography library** |
| GitHub API rate limits | High | Medium | Implement intelligent caching, stagger bulk imports |
| Database migration issues | High | Low | Thorough testing in dev, backup procedures |
| JWT secret compromise | High | Low | Key rotation procedures, short token lifetimes |
| User data privacy concerns | Medium | Medium | Clear privacy policy, minimal data collection |
| Scale beyond single VPS | Medium | High | Design for horizontal scaling from start |

---

## 📊 Success Metrics

### Phase 1 Success
- [ ] 100% of GitHub OAuth flows complete successfully
- [ ] JWT tokens verify correctly across all services
- [ ] No authentication-related errors in logs

### Phase 2 Success
- [ ] Users can connect repositories in <30 seconds
- [ ] Bulk import completes for repos with <1000 issues in <5 minutes
- [ ] Zero duplicate issues created during import

### Phase 3 Success
- [ ] Private repositories are inaccessible without proper auth
- [ ] Public dashboards load in <2 seconds without authentication
- [ ] Repository switching is instant (cached data)

### Phase 4 Success
- [ ] Cross-repository search returns results in <1 second
- [ ] Filtering across 10+ repositories remains performant
- [ ] Similarity search finds relevant issues with >80% accuracy

### Phase 5 Success
- [ ] 99.9% uptime over 30-day period
- [ ] All services restart automatically on failure
- [ ] Zero security vulnerabilities in dependency scan

---

## 🚀 Beyond MVP (Future Phases)

### Enhanced GitHub Integration
- Bi-directional sync (create/update issues from DispatchAI)
- GitHub App instead of OAuth App for fine-grained permissions
- Support for GitHub Enterprise instances

### Advanced Features
- AI-powered issue assignment recommendations
- Automated triage rule creation
- Integration with project management tools
- Team collaboration features

### Platform Expansion
- Support for GitLab, Bitbucket
- Integration with other issue trackers (Jira, Linear)
- API for third-party integrations
- Enterprise SSO (SAML, OIDC)

---

## 🎯 Definition of Done (Complete MVP)

A user can:
1. ✅ Sign in with their GitHub account
2. ✅ Connect any of their repositories or add public repositories by URL
3. ✅ View automatically classified issues from all connected repositories
4. ✅ Filter and search issues across multiple repositories
5. ✅ Share public repository dashboards with others
6. ✅ Access private repository dashboards only with proper authentication
7. ✅ Find similar issues using semantic search
8. ✅ Edit classifications with human-in-the-loop feedback

The system:
1. ✅ Handles multiple users without conflicts
2. ✅ Prevents duplicate repositories and issues
3. ✅ Runs reliably in production
4. ✅ Maintains security best practices
5. ✅ Scales to support 100+ concurrent users
6. ✅ Processes both webhook and batch imports efficiently

---

_This roadmap represents approximately 5 weeks of focused development work to transform DispatchAI from a single-tenant proof-of-concept to a production-ready multi-tenant platform._
