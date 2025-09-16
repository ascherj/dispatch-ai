"""
GitHub API integration for repository management
Handles authenticated requests to GitHub's REST API
"""

import re
from typing import Dict, Any, List, Optional
from datetime import datetime

import structlog
import httpx
from pydantic import BaseModel

logger = structlog.get_logger()

class GitHubIssue(BaseModel):
    """GitHub issue data model"""
    id: int
    number: int
    title: str
    body: Optional[str] = None
    state: str
    labels: List[Dict[str, Any]] = []
    assignees: List[Dict[str, Any]] = []
    user: Dict[str, Any]
    repository: Dict[str, Any]
    created_at: str
    updated_at: str
    closed_at: Optional[str] = None
    html_url: str

class SyncResult(BaseModel):
    """Result of a repository sync operation"""
    success: bool
    issues_fetched: int
    issues_stored: int
    error_message: Optional[str] = None
    last_issue_updated: Optional[str] = None

class GitHubOrganization(BaseModel):
    """GitHub organization data model"""
    id: int
    login: str
    name: Optional[str] = None
    description: Optional[str] = None
    avatar_url: str
    html_url: str
    type: str  # "Organization" or "User"
    public_repos: int
    total_private_repos: Optional[int] = None

class GitHubAPIClient:
    """GitHub API client for authenticated requests"""

    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.github.com"
        self.session = None

    async def __aenter__(self):
        """Async context manager entry"""
        self.session = httpx.AsyncClient(
            headers={
                "Authorization": f"token {self.access_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "DispatchAI/1.0"
            },
            timeout=30.0
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit"""
        if self.session:
            await self.session.aclose()

    async def get_repository_info(self, owner: str, repo: str) -> Dict[str, Any]:
        """Get repository information"""
        response = await self.session.get(f"{self.base_url}/repos/{owner}/{repo}")
        response.raise_for_status()
        return response.json()

    async def get_user_repositories(self, per_page: int = 100) -> List[Dict[str, Any]]:
        """Get repositories accessible by the authenticated user"""
        repositories = []
        page = 1

        while True:
            response = await self.session.get(
                f"{self.base_url}/user/repos",
                params={
                    "per_page": per_page,
                    "page": page,
                    "sort": "updated",
                    "direction": "desc"
                }
            )
            response.raise_for_status()

            page_repos = response.json()
            if not page_repos:
                break

            repositories.extend(page_repos)

            # Check rate limiting
            remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
            if remaining < 10:
                logger.warning("Approaching GitHub API rate limit", remaining=remaining)
                break

            page += 1

            # Safety limit
            if page > 10:  # Max 1000 repos
                break

        return repositories

    async def get_user_organizations(self) -> List[GitHubOrganization]:
        """Get organizations and user account that the authenticated user has repository access to"""
        organizations = []

        # First, get the authenticated user's own account
        try:
            user_response = await self.session.get(f"{self.base_url}/user")
            user_response.raise_for_status()
            user_data = user_response.json()

            # Add user's own account as an "organization"
            user_org = GitHubOrganization(
                id=user_data["id"],
                login=user_data["login"],
                name=user_data.get("name"),
                description=user_data.get("bio"),
                avatar_url=user_data["avatar_url"],
                html_url=user_data["html_url"],
                type="User",
                public_repos=user_data.get("public_repos", 0),
                total_private_repos=user_data.get("total_private_repos")
            )
            organizations.append(user_org)

        except Exception as e:
            logger.error("Error fetching user account", error=str(e))

        # Then get organizations the user belongs to
        try:
            orgs_response = await self.session.get(f"{self.base_url}/user/orgs")
            orgs_response.raise_for_status()
            orgs_data = orgs_response.json()

            for org_data in orgs_data:
                try:
                    org = GitHubOrganization(
                        id=org_data["id"],
                        login=org_data["login"],
                        name=org_data.get("name"),
                        description=org_data.get("description"),
                        avatar_url=org_data["avatar_url"],
                        html_url=org_data.get("html_url", f"https://github.com/{org_data['login']}"),
                        type="Organization",
                        public_repos=org_data.get("public_repos", 0)
                    )
                    organizations.append(org)

                except Exception as e:
                    logger.error("Error parsing organization", org_id=org_data.get("id"), error=str(e))

        except Exception as e:
            logger.error("Error fetching organizations", error=str(e))

        logger.info("Fetched user organizations", count=len(organizations))
        return organizations

    async def get_organization_repositories(self, org_login: str, per_page: int = 100) -> List[Dict[str, Any]]:
        """Get repositories for a specific organization or user"""
        repositories = []
        page = 1

        # Determine the endpoint based on whether this is a user or organization
        # Try user repos first, then org repos if that fails
        endpoints_to_try = [
            f"{self.base_url}/users/{org_login}/repos",  # User repositories
            f"{self.base_url}/orgs/{org_login}/repos"    # Organization repositories
        ]

        for endpoint in endpoints_to_try:
            try:
                page = 1
                repositories = []

                while True:
                    response = await self.session.get(
                        endpoint,
                        params={
                            "per_page": per_page,
                            "page": page,
                            "sort": "updated",
                            "direction": "desc"
                        }
                    )

                    if response.status_code == 404:
                        # Try next endpoint
                        break

                    response.raise_for_status()

                    page_repos = response.json()
                    if not page_repos:
                        break

                    # Filter repositories where user has access
                    accessible_repos = []
                    for repo in page_repos:
                        # Check if user has access to this repository
                        permissions = repo.get("permissions", {})
                        if permissions.get("pull", False) or permissions.get("push", False) or permissions.get("admin", False):
                            accessible_repos.append(repo)

                    repositories.extend(accessible_repos)

                    # Check rate limiting
                    remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
                    if remaining < 10:
                        logger.warning("Approaching GitHub API rate limit", remaining=remaining)
                        break

                    page += 1

                    # Safety limit
                    if page > 10:  # Max 1000 repos
                        break

                # If we got repositories, we found the right endpoint
                if repositories:
                    break

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    continue  # Try next endpoint
                else:
                    logger.error("Error fetching organization repositories",
                               org=org_login, endpoint=endpoint, status=e.response.status_code)
                    break
            except Exception as e:
                logger.error("Unexpected error fetching organization repositories",
                           org=org_login, endpoint=endpoint, error=str(e))
                break

        logger.info("Fetched organization repositories", org=org_login, count=len(repositories))
        return repositories

    async def get_repository_issues(
        self,
        owner: str,
        repo: str,
        state: str = "all",
        since: Optional[str] = None,
        per_page: int = 100,
        max_pages: int = 10
    ) -> List[GitHubIssue]:
        """
        Get issues from a repository

        Args:
            owner: Repository owner
            repo: Repository name
            state: Issue state ('open', 'closed', 'all')
            since: Only issues updated after this time (ISO 8601)
            per_page: Number of issues per page (max 100)
            max_pages: Maximum number of pages to fetch
        """
        issues = []
        page = 1

        params = {
            "state": state,
            "per_page": per_page,
            "sort": "updated",
            "direction": "desc"
        }

        if since:
            params["since"] = since

        while page <= max_pages:
            params["page"] = page

            try:
                response = await self.session.get(
                    f"{self.base_url}/repos/{owner}/{repo}/issues",
                    params=params
                )
                response.raise_for_status()

                page_issues = response.json()
                if not page_issues:
                    break

                # Filter out pull requests (GitHub API includes PRs in issues endpoint)
                actual_issues = [
                    issue for issue in page_issues
                    if "pull_request" not in issue
                ]

                # Convert to our model
                for issue_data in actual_issues:
                    try:
                        issue = GitHubIssue(
                            id=issue_data["id"],
                            number=issue_data["number"],
                            title=issue_data["title"],
                            body=issue_data.get("body"),
                            state=issue_data["state"],
                            labels=issue_data.get("labels", []),
                            assignees=issue_data.get("assignees", []),
                            user=issue_data["user"],
                            repository={
                                "owner": owner,
                                "name": repo,
                                "full_name": f"{owner}/{repo}"
                            },
                            created_at=issue_data["created_at"],
                            updated_at=issue_data["updated_at"],
                            closed_at=issue_data.get("closed_at"),
                            html_url=issue_data["html_url"]
                        )
                        issues.append(issue)
                    except Exception as e:
                        logger.error("Error parsing issue", issue_id=issue_data.get("id"), error=str(e))
                        continue

                # Check rate limiting
                remaining = int(response.headers.get("X-RateLimit-Remaining", 0))
                if remaining < 10:
                    logger.warning("Approaching GitHub API rate limit", remaining=remaining)
                    break

                page += 1

                # If we got fewer issues than requested, we're at the end
                if len(page_issues) < per_page:
                    break

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    # Rate limited or forbidden
                    logger.error("GitHub API forbidden", status=403, response=e.response.text)
                    break
                elif e.response.status_code == 404:
                    # Repository not found or no access
                    logger.error("Repository not found or no access", owner=owner, repo=repo)
                    break
                else:
                    logger.error("GitHub API error", status=e.response.status_code, error=str(e))
                    break
            except Exception as e:
                logger.error("Unexpected error fetching issues", error=str(e))
                break

        logger.info("Fetched issues from GitHub", owner=owner, repo=repo, count=len(issues))
        return issues

def parse_github_url(github_url: str) -> tuple[str, str]:
    """Parse GitHub URL and return owner, repo"""
    github_url_pattern = r"github\.com/([^/]+)/([^/]+)"
    match = re.search(github_url_pattern, github_url)
    if not match:
        raise ValueError("Invalid GitHub URL format")

    owner, repo = match.groups()
    repo = repo.rstrip('.git')  # Remove .git suffix if present
    return owner, repo

async def validate_public_repository(github_url: str) -> Dict[str, Any]:
    """Validate and get metadata for a public GitHub repository URL"""
    owner, repo = parse_github_url(github_url)

    # Use GitHub API without authentication for public repos
    async with httpx.AsyncClient() as client:
        response = await client.get(
            f"https://api.github.com/repos/{owner}/{repo}",
            headers={"Accept": "application/vnd.github.v3+json"},
            timeout=30.0
        )

        if response.status_code == 404:
            raise ValueError("Repository not found")
        elif response.status_code == 403:
            raise ValueError("Repository is private or rate limited")

        response.raise_for_status()
        repo_info = response.json()

        if repo_info["private"]:
            raise ValueError("Repository is private")

        return repo_info