# TODO: DispatchAI Development Priorities

## ✅ COMPLETED: GitHub Authentication Bug Fix

### Problem Summary
GitHub authentication button was missing from frontend and login attempts were failing with various errors. **Final Issue**: GitHub OAuth redirect URI mismatch error.

### Root Cause Analysis
1. ✅ **Missing Auth Service**: Auth service (port 8003) was not configured in production docker-compose
2. ✅ **Mixed Content Errors**: Frontend trying to access HTTP auth service via HTTPS
3. ✅ **URL Path Duplication**: AUTH_URL contained `/auth` but frontend code appended `/auth/github/authorize`, creating duplicate path `/auth/auth/github/authorize`
4. ✅ **Missing OAuth Configuration**: Auth service missing GitHub OAuth credentials
5. ✅ **GitHub OAuth Redirect URI Mismatch**: Updated GitHub OAuth app settings to use correct redirect URI

### Fixes Applied
1. ✅ **Added auth service to docker-compose.prod.yml**:
   - Complete auth service configuration with proper environment variables
   - Health checks and dependencies configured
   - Port 8003 exposed

2. ✅ **Fixed SSL/HTTPS issues**:
   - Updated AUTH_URL to use HTTPS: `https://dispatchai.ascher.dev`
   - User configured nginx to proxy `/auth` requests to `localhost:8003`

3. ✅ **Fixed duplicate /auth path**:
   - Changed AUTH_URL from `https://dispatchai.ascher.dev/auth` to `https://dispatchai.ascher.dev`
   - Rebuilt dashboard container with corrected environment variable
   - Frontend now constructs correct URL: `https://dispatchai.ascher.dev/auth/github/authorize`

4. ✅ **Fixed missing OAuth configuration**:
   - Added all required environment variables to .env.prod:
     - JWT_SECRET (existing key reused)
     - ENCRYPTION_KEY (generated Fernet key)
     - GITHUB_REDIRECT_URI=https://dispatchai.ascher.dev/auth/callback
     - GITHUB_CLIENT_ID (with real OAuth app credentials)
     - GITHUB_CLIENT_SECRET (with real OAuth app credentials)
   - Restarted auth service with proper configuration
   - Auth endpoint now returns OAuth URL instead of 404

### ✅ RESOLUTION: GitHub OAuth Redirect URI Fixed

**Final Fix Applied**:
- Updated GitHub OAuth app settings to use correct redirect URI: `https://dispatchai.ascher.dev/auth/callback`
- Login flow now working successfully
- Users can authenticate with GitHub and access protected features

### Files Modified
- `docker-compose.prod.yml` - Added complete auth service configuration
- `auth/Dockerfile` - Added curl for health checks
- `dashboard/Dockerfile` - Added VITE_AUTH_URL build argument support
- `.env.prod` - Updated AUTH_URL to `https://dispatchai.ascher.dev`
- `/etc/nginx/sites-available/dispatchai` - User added auth proxy configuration

### Current Environment State
- All production containers rebuilt with latest code
- Auth service running on port 8003
- Nginx configured to proxy `/auth` to auth service
- Dashboard built with correct AUTH_URL environment variable

**✅ RESOLUTION**: GitHub OAuth app redirect URI updated to `https://dispatchai.ascher.dev/auth/callback` - login flow now working correctly!

---

## 🎯 NEXT PRIORITIES

### Priority 1: Dashboard Repository Management UI
**Goal**: Complete the repository management interface
- [ ] Repository list view with filtering and search
- [ ] Organization/user grouping with expand/collapse
- [ ] Repository stats (issue counts, sync status)
- [ ] Enable/disable repository sync controls
- [ ] Manual repository refresh actions

### Priority 2: Issue Management Dashboard
**Goal**: Build interface for viewing and managing classified issues
- [ ] Issue list view with AI classification results
- [ ] Issue detail view with full context
- [ ] Manual correction UI for human-in-the-loop feedback
- [ ] Similar issues display using vector similarity
- [ ] Batch operations for corrections

### Priority 3: Analytics & Insights
**Goal**: Provide system performance and pattern insights
- [ ] Classification accuracy metrics over time
- [ ] Processing latency and throughput dashboards
- [ ] Repository-level issue patterns and trends
- [ ] User activity and correction history

### Priority 4: Advanced Features
**Goal**: Enhance system capabilities
- [ ] Similar issues detection optimization
- [ ] Repository-specific learning
- [ ] Suggested assignee recommendations
- [ ] Pattern recognition displays

---

## 📊 System Status

**All Core Services**: ✅ Operational
- Ingress, Classifier, Gateway, Dashboard, Auth services running
- GitHub OAuth authentication working
- WebSocket real-time updates functional
- AI classification pipeline operational

**Latest Update**: January 2025 - GitHub OAuth authentication fully resolved