"""
DispatchAI Auth Service (Refactored)
Clean, modular authentication service inspired by OpenAuth.js patterns
"""

import os
import logging
from typing import Dict, Any

import structlog
from fastapi import FastAPI, HTTPException, Depends, status, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

# Import our clean authentication architecture
from core.issuer import AuthIssuer
from core.storage import DatabaseStorage
from core.subjects import UserSubject
from providers.github import GitHubProvider, GitHubConfig
from github_api import GitHubAPIClient, GitHubIssueSyncer, SyncResult

# Configure structured logging
logging.basicConfig(level=logging.INFO)
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger()

# Environment configuration
DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/dispatchai"
)
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")
GITHUB_REDIRECT_URI = os.getenv("GITHUB_REDIRECT_URI", "http://localhost:3000/auth/callback")
JWT_SECRET = os.getenv("JWT_SECRET", "dev-jwt-secret-change-in-production")

# CORS allowed origins
CORS_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000,http://localhost:8002,http://127.0.0.1:3000",
).split(",")

# Initialize FastAPI app
app = FastAPI(
    title="DispatchAI Auth Service (Refactored)",
    description="Clean, modular authentication service with OAuth providers",
    version="0.2.0",
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security scheme
security = HTTPBearer(auto_error=False)

# Initialize authentication components
storage = DatabaseStorage(DATABASE_URL)

# Configure providers
providers = {}
if GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET:
    providers["github"] = GitHubProvider(GitHubConfig(
        client_id=GITHUB_CLIENT_ID,
        client_secret=GITHUB_CLIENT_SECRET,
        scopes=["user:email", "repo"],
        redirect_uri=GITHUB_REDIRECT_URI
    ))

# Initialize issuer
auth_issuer = AuthIssuer(
    providers=providers,
    storage=storage,
    secret_key=JWT_SECRET
)

# Pydantic models
class AuthorizeResponse(BaseModel):
    auth_url: str
    state: str

class CallbackRequest(BaseModel):
    code: str
    state: str

class AuthResponse(BaseModel):
    access_token: str
    refresh_token: str
    user: Dict[str, Any]

class UserResponse(BaseModel):
    id: int
    github_id: int
    username: str
    email: str = None
    created_at: str
    properties: Dict[str, Any] = {}

class RepositoryResponse(BaseModel):
    owner: str
    name: str
    full_name: str
    permissions: Dict[str, bool]
    last_sync_at: str = None
    issues_synced: int = 0
    sync_status: str = None

class HealthResponse(BaseModel):
    status: str
    service: str
    version: str

# Authentication helpers
async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> UserSubject:
    """Get current authenticated user"""
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required"
        )

    user = await auth_issuer.verify_token(credentials.credentials)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return user

# API Endpoints
@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    return HealthResponse(
        status="healthy",
        service="auth-refactored",
        version="0.2.0"
    )

@app.get("/auth/{provider}/authorize", response_model=AuthorizeResponse)
async def authorize(provider: str, request: Request):
    """Start OAuth authorization flow"""
    if provider not in auth_issuer.providers:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider}' not configured"
        )

    try:
        # Use the configured redirect URI
        result = auth_issuer.create_authorization_url(provider, GITHUB_REDIRECT_URI)

        logger.info("Authorization URL created", provider=provider, state=result["state"])

        return AuthorizeResponse(
            auth_url=result["url"],
            state=result["state"]
        )

    except Exception as e:
        logger.error("Authorization failed", provider=provider, error=str(e))
        raise HTTPException(status_code=500, detail="Authorization failed")

@app.post("/auth/{provider}/callback", response_model=AuthResponse)
async def callback(provider: str, callback_request: CallbackRequest):
    """Handle OAuth callback"""
    if provider not in auth_issuer.providers:
        raise HTTPException(
            status_code=404,
            detail=f"Provider '{provider}' not configured"
        )

    try:
        result = await auth_issuer.handle_callback(
            callback_request.code,
            callback_request.state
        )

        logger.info(
            "User authenticated successfully",
            provider=provider,
            user_id=result["user"]["id"]
        )

        return AuthResponse(**result)

    except ValueError as e:
        logger.error("Callback validation failed", provider=provider, error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Callback processing failed", provider=provider, error=str(e))
        raise HTTPException(status_code=500, detail="Authentication failed")

@app.get("/auth/user/profile", response_model=UserResponse)
async def get_user_profile(current_user: UserSubject = Depends(get_current_user)):
    """Get current user profile"""
    return UserResponse(
        id=current_user.id,
        github_id=current_user.github_id,
        username=current_user.username,
        email=current_user.email,
        created_at=current_user.created_at.isoformat(),
        properties=current_user.properties
    )

@app.get("/auth/user/repositories")
async def get_user_repositories(current_user: UserSubject = Depends(get_current_user)):
    """Get repositories accessible by the current user"""
    try:
        # Get user's GitHub access token
        github_token = await storage.get_user_access_token(current_user.id)
        if not github_token:
            raise HTTPException(status_code=401, detail="GitHub token not found")

        # Get GitHub provider to access repositories
        github_provider = auth_issuer.get_provider("github")
        repositories = await github_provider.get_user_repositories(github_token)

        # Get sync status from database
        conn = storage.get_connection()
        with conn.cursor() as cur:
            cur.execute("""
                SELECT repository_owner, repository_name, last_sync_at, issues_synced, sync_status
                FROM dispatchai.repository_syncs
                WHERE user_id = %s
            """, (current_user.id,))
            sync_data = {f"{row[0]}/{row[1]}": {
                "last_sync_at": row[2].isoformat() if row[2] else None,
                "issues_synced": row[3],
                "sync_status": row[4]
            } for row in cur.fetchall()}

        conn.close()

        # Build response
        result = []
        for repo in repositories:
            full_name = repo["full_name"]
            sync_info = sync_data.get(full_name, {})

            result.append(RepositoryResponse(
                owner=repo["owner"]["login"],
                name=repo["name"],
                full_name=full_name,
                permissions={
                    "admin": repo["permissions"]["admin"],
                    "push": repo["permissions"]["push"],
                    "pull": repo["permissions"]["pull"]
                },
                last_sync_at=sync_info.get("last_sync_at"),
                issues_synced=sync_info.get("issues_synced", 0),
                sync_status=sync_info.get("sync_status")
            ))

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Error fetching repositories", user_id=current_user.id, error=str(e))
        raise HTTPException(status_code=500, detail="Failed to fetch repositories")

@app.post("/repos/{owner}/{repo}/sync", response_model=SyncResult)
async def sync_repository_issues(
    owner: str,
    repo: str,
    current_user: UserSubject = Depends(get_current_user)
):
    """Manually sync issues from a GitHub repository"""
    try:
        # Get user's GitHub access token
        github_token = await storage.get_user_access_token(current_user.id)
        if not github_token:
            raise HTTPException(status_code=401, detail="GitHub token not found")

        # Initialize GitHub API client and syncer
        async with GitHubAPIClient(github_token) as github_client:
            # Verify repository access
            try:
                await github_client.get_repository_info(owner, repo)
            except Exception as e:
                if "404" in str(e):
                    raise HTTPException(status_code=404, detail="Repository not found or no access")
                elif "403" in str(e):
                    raise HTTPException(status_code=403, detail="Insufficient permissions")
                else:
                    raise HTTPException(status_code=500, detail="Failed to verify repository access")

            # Perform sync
            syncer = GitHubIssueSyncer(storage.get_connection)
            result = await syncer.sync_repository_issues(
                github_client=github_client,
                user_id=current_user.id,
                owner=owner,
                repo=repo
            )

            logger.info(
                "Repository sync completed",
                owner=owner,
                repo=repo,
                user_id=current_user.id,
                success=result.success,
                issues_fetched=result.issues_fetched,
                issues_stored=result.issues_stored
            )

            return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Repository sync failed", owner=owner, repo=repo, user_id=current_user.id, error=str(e))
        raise HTTPException(status_code=500, detail="Repository sync failed")

@app.post("/auth/refresh")
async def refresh_token(refresh_token: str):
    """Refresh access token"""
    result = await auth_issuer.refresh_user_token(refresh_token)
    if not result:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

    return result

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8003, reload=True, log_config=None)