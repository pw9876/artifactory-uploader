"""Core upload logic for artifactory-uploader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import requests


@dataclass
class UploadResult:
    local_path: Path
    remote_url: str
    dry_run: bool = False


class ArtifactoryClient:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        token: str | None = None,
        session: requests.Session | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.session.headers["User-Agent"] = "artifactory-uploader/0.1"
        if api_key:
            self.session.headers["X-JFrog-Art-Api"] = api_key
        elif token:
            self.session.headers["Authorization"] = f"Bearer {token}"

    def upload_file(self, local_path: Path, repo: str, remote_path: str) -> str:
        url = f"{self.base_url}/{repo}/{remote_path.lstrip('/')}"
        with local_path.open("rb") as fh:
            resp = self.session.put(url, data=fh, timeout=120)
            resp.raise_for_status()
        return url


def upload_directory(
    client: ArtifactoryClient,
    source_dir: Path,
    repo: str,
    target_prefix: str = "",
    dry_run: bool = False,
    exclude: list[str] | None = None,
    progress_cb=None,
) -> list[UploadResult]:
    source_dir = source_dir.resolve()
    exclude_patterns = exclude or []
    results: list[UploadResult] = []

    for local_path in sorted(source_dir.rglob("*")):
        if not local_path.is_file():
            continue
        rel = local_path.relative_to(source_dir)
        if any(rel.match(pat) for pat in exclude_patterns):
            continue

        rel_posix = rel.as_posix()
        remote_path = f"{target_prefix.rstrip('/')}/{rel_posix}" if target_prefix else rel_posix
        remote_url = f"{client.base_url}/{repo}/{remote_path}"

        if dry_run:
            result = UploadResult(local_path=local_path, remote_url=remote_url, dry_run=True)
        else:
            url = client.upload_file(local_path, repo, remote_path)
            result = UploadResult(local_path=local_path, remote_url=url)

        results.append(result)
        if progress_cb:
            progress_cb(result)

    return results
