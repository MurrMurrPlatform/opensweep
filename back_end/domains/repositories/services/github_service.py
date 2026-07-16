"""GitHub service — thin wrapper over GitHubClient for the surfaces OpenSweep
actually uses: file contents (repo file viewer, platform read-code tools)
and PR URL construction. Inactive client (no credential) = graceful None."""

from typing import Optional

from infrastructure.git_providers import GitProviderClient
from infrastructure.github_client import GitHubClient
from logging_config import logger


class GitHubService:
    def __init__(self, client: GitProviderClient | None = None) -> None:
        self._client = client or GitHubClient()
        if not self._client.is_active:
            logger.info(
                "GitHub client inactive (GITHUB_TOKEN empty)", extra={"tag": "github"}
            )

    async def get_file_contents(self, owner: str, repo: str, path: str, ref: str | None = None) -> Optional[tuple[str, int]]:
        """Fetch file contents from GitHub. Returns (utf8_text, bytes_total) or None."""
        if not self._client.is_active:
            return None
        try:
            raw = await self._client.get_file_contents(owner, repo, path, ref=ref)
        except Exception as exc:
            logger.warning(f"GitHub get_file_contents failed: {exc}", extra={"tag": "github"})
            return None
        if isinstance(raw, list) or raw.get("type") != "file":
            return None
        import base64
        b64 = raw.get("content") or ""
        try:
            data = base64.b64decode(b64.replace("\n", ""))
        except Exception:
            return None
        if b"\x00" in data[:4096]:
            return None
        return data.decode("utf-8", errors="replace"), int(raw.get("size") or len(data))

    def build_pr_url(self, owner: Optional[str], repo: Optional[str], number: int) -> str:
        if owner and repo:
            return f"https://github.com/{owner}/{repo}/pull/{number}"
        return f"https://github.com/example/repo/pull/{number}"
