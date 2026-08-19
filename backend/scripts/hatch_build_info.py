from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse, urlunparse

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

_SCP_LIKE_GIT_URL_PATTERN = re.compile(
    r"^(?:(?P<user>[^@/:]+)@)?(?P<host>[^:/]+):(?P<path>.+)$"
)


class BuildInfoHook(BuildHookInterface):
    """Add build information to wheel metadata."""

    PLUGIN_NAME = "build-info"

    _build_info_path: Path | None = None

    def initialize(self, version: str, build_data: dict) -> None:
        """Write build_info.json to a temp file and register it as extra metadata."""
        if self.target_name != "wheel":
            return  # sdists have no dist-info

        commit_sha = self._commit_sha()
        payload = {
            "version": self.metadata.version,
            "commit_sha": commit_sha,
            "short_sha": commit_sha[:7] if commit_sha else None,
            "branch": self._branch(),
            "dirty": self._is_dirty(),
            "repository_url": self._repository_url(),
            "build_timestamp": self._build_timestamp(),
        }

        fd, raw_path = tempfile.mkstemp(prefix="menagerist-build-info-", suffix=".json")
        os.close(fd)
        path = Path(raw_path)
        path.write_text(json.dumps(payload))
        self._build_info_path = path

        build_data.setdefault("extra_metadata", {})[str(path)] = "build_info.json"

    def finalize(self, version: str, build_data: dict, artifact_path: str) -> None:
        """Delete the temporary build_info.json file after the build completes."""
        if self._build_info_path and self._build_info_path.exists():
            self._build_info_path.unlink()

    def _commit_sha(self) -> str | None:
        """Return the commit SHA from the env override or `git rev-parse HEAD`."""
        if sha := os.environ.get("MENAGERIST_BUILD_COMMIT_SHA"):
            return sha
        try:
            result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            return result.stdout.strip()
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return None

    def _branch(self) -> str | None:
        """Return the current branch from the env override or `git branch`."""
        if branch := os.environ.get("MENAGERIST_BUILD_BRANCH"):
            return branch
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            return result.stdout.strip() or None
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return None

    def _is_dirty(self) -> bool | None:
        """Return whether the working tree has uncommitted changes."""
        if dirty := os.environ.get("MENAGERIST_BUILD_DIRTY"):
            return dirty.lower() in {"1", "true", "yes", "on"}
        try:
            result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            return bool(result.stdout.strip())
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return None

    def _repository_url(self) -> str | None:
        """Return the normalised repository URL from the env override or git remote."""
        if repository_url := os.environ.get("MENAGERIST_BUILD_REPOSITORY_URL"):
            return self._normalize_repository_url(repository_url)
        try:
            result = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=True,
                timeout=5,
            )
            return self._normalize_repository_url(result.stdout.strip())
        except (
            subprocess.CalledProcessError,
            FileNotFoundError,
            subprocess.TimeoutExpired,
        ):
            return None

    def _normalize_repository_url(self, repository_url: str) -> str:
        """Convert an SSH, git, or HTTP(S) remote URL to a canonical HTTPS URL."""
        repository_url = repository_url.strip()

        if "://" not in repository_url and (
            match := _SCP_LIKE_GIT_URL_PATTERN.match(repository_url)
        ):
            host = match.group("host")
            path = match.group("path")
            return f"https://{host}/{self._strip_git_suffix(path)}"

        parsed_url = urlparse(repository_url)
        path = self._strip_git_suffix(parsed_url.path).rstrip("/")

        if parsed_url.scheme in {"git", "ssh"}:
            return urlunparse(("https", parsed_url.hostname or "", path, "", "", ""))

        if parsed_url.scheme in {"http", "https"}:
            return urlunparse(("https", parsed_url.netloc, path, "", "", ""))

        return repository_url

    @staticmethod
    def _strip_git_suffix(path: str) -> str:
        """Remove a trailing `.git` suffix from a repository path."""
        return path.removesuffix(".git")

    @staticmethod
    def _build_timestamp() -> str | None:
        """Return the build timestamp from an env override or the current UTC time."""
        if timestamp := os.environ.get("MENAGERIST_BUILD_TIMESTAMP"):
            return timestamp
        if epoch := os.environ.get("MENAGERIST_BUILD_EPOCH"):
            return datetime.fromtimestamp(int(epoch), tz=UTC).isoformat()
        return datetime.now(UTC).isoformat()
