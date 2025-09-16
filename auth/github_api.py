"""
GitHub API integration for manual issue retrieval
Handles authenticated requests to GitHub's REST API
"""

import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime
import asyncio

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

    async def get_user_info(self) -> Dict[str, Any]:
        """Get authenticated user information"""
        response = await self.session.get(f"{self.base_url}/user")
        response.raise_for_status()
        return response.json()

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

    async def check_rate_limit(self) -> Dict[str, Any]:
        """Check current rate limit status"""
        response = await self.session.get(f"{self.base_url}/rate_limit")
        response.raise_for_status()
        return response.json()

class GitHubIssueSyncer:
    """Handles syncing GitHub issues to the database"""

    def __init__(self, db_connection_factory):
        self.get_db_connection = db_connection_factory

    async def sync_repository_issues(
        self,
        github_client: GitHubAPIClient,
        user_id: int,
        owner: str,
        repo: str,
        since: Optional[str] = None
    ) -> SyncResult:
        """
        Sync issues from a GitHub repository to the database

        Args:
            github_client: Authenticated GitHub API client
            user_id: User ID performing the sync
            owner: Repository owner
            repo: Repository name
            since: Only sync issues updated after this time
        """
        try:
            # Update sync status to 'syncing'
            await self._update_sync_status(user_id, owner, repo, "syncing")

            # Fetch issues from GitHub
            issues = await github_client.get_repository_issues(
                owner=owner,
                repo=repo,
                since=since,
                max_pages=20  # Limit to prevent excessive API usage
            )

            if not issues:
                await self._update_sync_status(
                    user_id, owner, repo, "completed",
                    issues_synced=0
                )
                return SyncResult(
                    success=True,
                    issues_fetched=0,
                    issues_stored=0
                )

            # Store issues in database
            stored_count = await self._store_issues(issues, user_id)

            # Find the most recent issue update time
            last_updated = max(issues, key=lambda x: x.updated_at).updated_at

            # Update sync status to 'completed'
            await self._update_sync_status(
                user_id, owner, repo, "completed",
                issues_synced=stored_count,
                last_issue_updated=last_updated
            )

            logger.info(
                "Repository sync completed",
                user_id=user_id,
                owner=owner,
                repo=repo,
                issues_fetched=len(issues),
                issues_stored=stored_count
            )

            return SyncResult(
                success=True,
                issues_fetched=len(issues),
                issues_stored=stored_count,
                last_issue_updated=last_updated
            )

        except Exception as e:
            error_msg = f"Sync failed: {str(e)}"
            logger.error("Repository sync failed", user_id=user_id, owner=owner, repo=repo, error=error_msg)

            # Update sync status to 'failed'
            await self._update_sync_status(
                user_id, owner, repo, "failed",
                error_message=error_msg
            )

            return SyncResult(
                success=False,
                issues_fetched=0,
                issues_stored=0,
                error_message=error_msg
            )

    async def _update_sync_status(
        self,
        user_id: int,
        owner: str,
        repo: str,
        status: str,
        issues_synced: Optional[int] = None,
        last_issue_updated: Optional[str] = None,
        error_message: Optional[str] = None
    ):
        """Update repository sync status in database"""
        try:
            conn = self.get_db_connection()
            with conn.cursor() as cur:
                # Insert or update sync record
                cur.execute("""
                    INSERT INTO dispatchai.repository_syncs
                    (user_id, repository_owner, repository_name, sync_status, last_sync_at)
                    VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
                    ON CONFLICT (user_id, repository_owner, repository_name)
                    DO UPDATE SET
                        sync_status = EXCLUDED.sync_status,
                        last_sync_at = CURRENT_TIMESTAMP,
                        issues_synced = COALESCE(%s, repository_syncs.issues_synced),
                        last_issue_updated_at = COALESCE(%s::timestamp, repository_syncs.last_issue_updated_at),
                        error_message = %s,
                        updated_at = CURRENT_TIMESTAMP
                """, (
                    user_id, owner, repo, status,
                    issues_synced,
                    last_issue_updated,
                    error_message
                ))
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("Failed to update sync status", error=str(e))

    async def _store_issues(self, issues: List[GitHubIssue], user_id: int) -> int:
        """Store issues in the database"""
        stored_count = 0

        try:
            conn = self.get_db_connection()
            with conn.cursor() as cur:
                for issue in issues:
                    try:
                        # Convert labels to simple list of names
                        label_names = [label["name"] for label in issue.labels]

                        # Insert or update issue
                        cur.execute("""
                            INSERT INTO dispatchai.issues (
                                github_issue_id, repository_name, repository_owner, issue_number,
                                title, body, state, labels, assignees, author, author_association,
                                created_at, updated_at, closed_at, raw_data, sync_source, pulled_by_user_id
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (repository_owner, repository_name, issue_number)
                            DO UPDATE SET
                                title = EXCLUDED.title,
                                body = EXCLUDED.body,
                                state = EXCLUDED.state,
                                labels = EXCLUDED.labels,
                                assignees = EXCLUDED.assignees,
                                updated_at = EXCLUDED.updated_at,
                                closed_at = EXCLUDED.closed_at,
                                raw_data = EXCLUDED.raw_data
                        """, (
                            issue.id,
                            issue.repository["name"],
                            issue.repository["owner"],
                            issue.number,
                            issue.title,
                            issue.body,
                            issue.state,
                            label_names,  # JSON array of label names
                            [assignee["login"] for assignee in issue.assignees],  # JSON array of usernames
                            issue.user["login"],
                            issue.user.get("type", "User"),  # Use type instead of association for manual pulls
                            issue.created_at,
                            issue.updated_at,
                            issue.closed_at,
                            issue.dict(),  # Store full GitHub response as raw data
                            "manual_pull",
                            user_id
                        ))
                        stored_count += 1

                    except Exception as e:
                        logger.error("Error storing issue", issue_id=issue.id, error=str(e))
                        continue

            conn.commit()
            conn.close()

        except Exception as e:
            logger.error("Database error storing issues", error=str(e))
            raise

        return stored_count