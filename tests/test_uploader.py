"""Tests for artifactory_uploader.uploader."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

from artifactory_uploader.uploader import ArtifactoryClient, UploadResult, upload_directory


def _make_client(base_url: str = "https://example.jfrog.io/artifactory") -> ArtifactoryClient:
    session = MagicMock()
    session.put.return_value.raise_for_status = MagicMock()
    return ArtifactoryClient(base_url=base_url, session=session)


class TestArtifactoryClient:
    def test_api_key_set_in_header(self):
        client = ArtifactoryClient("https://example.com", api_key="mykey")
        assert client.session.headers["X-JFrog-Art-Api"] == "mykey"

    def test_token_set_in_header(self):
        client = ArtifactoryClient("https://example.com", token="mytoken")
        assert client.session.headers["Authorization"] == "Bearer mytoken"

    def test_trailing_slash_stripped_from_base_url(self):
        client = ArtifactoryClient("https://example.com/artifactory/")
        assert client.base_url == "https://example.com/artifactory"

    def test_upload_file_puts_to_correct_url(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes(b"content")
        client = _make_client("https://example.jfrog.io/artifactory")
        url = client.upload_file(f, "my-repo", "path/to/file.txt")
        assert url == "https://example.jfrog.io/artifactory/my-repo/path/to/file.txt"
        client.session.put.assert_called_once()
        assert client.session.put.call_args[0][0] == url

    def test_upload_file_strips_leading_slash_from_remote_path(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes(b"content")
        client = _make_client()
        url = client.upload_file(f, "repo", "/leading/slash/file.txt")
        assert "/repo//leading" not in url
        assert url.endswith("/leading/slash/file.txt")

    def test_upload_file_raises_on_http_error(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes(b"content")
        session = MagicMock()
        session.put.return_value.raise_for_status.side_effect = requests.HTTPError("403")
        client = ArtifactoryClient("https://example.com", session=session)
        with pytest.raises(requests.HTTPError):
            client.upload_file(f, "repo", "file.txt")


class TestUploadDirectory:
    def test_uploads_all_files(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "a.txt").write_bytes(b"a")
        (tmp_path / "subdir" / "b.txt").write_bytes(b"b")
        client = _make_client()
        results = upload_directory(client, tmp_path, "repo")
        assert len(results) == 2
        assert client.session.put.call_count == 2

    def test_preserves_directory_structure(self, tmp_path):
        (tmp_path / "x" / "y").mkdir(parents=True)
        (tmp_path / "x" / "y" / "file.txt").write_bytes(b"data")
        client = _make_client()
        results = upload_directory(client, tmp_path, "repo")
        remote_path = client.session.put.call_args[0][0]
        assert "x/y/file.txt" in remote_path

    def test_target_prefix_prepended(self, tmp_path):
        (tmp_path / "file.txt").write_bytes(b"data")
        client = _make_client()
        upload_directory(client, tmp_path, "repo", target_prefix="releases/1.0")
        remote_path = client.session.put.call_args[0][0]
        assert "releases/1.0/file.txt" in remote_path

    def test_target_prefix_trailing_slash_normalised(self, tmp_path):
        (tmp_path / "file.txt").write_bytes(b"data")
        client = _make_client()
        upload_directory(client, tmp_path, "repo", target_prefix="prefix/")
        remote_path = client.session.put.call_args[0][0]
        assert "prefix//file.txt" not in remote_path
        assert "prefix/file.txt" in remote_path

    def test_dry_run_does_not_call_upload(self, tmp_path):
        (tmp_path / "file.txt").write_bytes(b"data")
        client = _make_client()
        results = upload_directory(client, tmp_path, "repo", dry_run=True)
        client.session.put.assert_not_called()
        assert len(results) == 1
        assert results[0].dry_run is True

    def test_dry_run_result_contains_expected_url(self, tmp_path):
        (tmp_path / "file.txt").write_bytes(b"data")
        client = _make_client("https://acme.jfrog.io/artifactory")
        results = upload_directory(client, tmp_path, "my-repo", dry_run=True)
        assert results[0].remote_url == "https://acme.jfrog.io/artifactory/my-repo/file.txt"

    def test_exclude_pattern_filters_files(self, tmp_path):
        (tmp_path / "file.txt").write_bytes(b"a")
        (tmp_path / "debug.log").write_bytes(b"b")
        (tmp_path / "trace.log").write_bytes(b"c")
        client = _make_client()
        results = upload_directory(client, tmp_path, "repo", exclude=["*.log"])
        assert len(results) == 1
        assert results[0].local_path.name == "file.txt"

    def test_multiple_exclude_patterns(self, tmp_path):
        (tmp_path / "file.txt").write_bytes(b"a")
        (tmp_path / "file.log").write_bytes(b"b")
        (tmp_path / "file.tmp").write_bytes(b"c")
        client = _make_client()
        results = upload_directory(client, tmp_path, "repo", exclude=["*.log", "*.tmp"])
        assert len(results) == 1

    def test_subdirectories_not_included_as_results(self, tmp_path):
        (tmp_path / "subdir").mkdir()
        (tmp_path / "subdir" / "file.txt").write_bytes(b"data")
        client = _make_client()
        results = upload_directory(client, tmp_path, "repo")
        assert all(r.local_path.is_file() for r in results)

    def test_empty_directory_returns_empty_list(self, tmp_path):
        client = _make_client()
        results = upload_directory(client, tmp_path, "repo")
        assert results == []

    def test_progress_callback_called_per_file(self, tmp_path):
        (tmp_path / "a.txt").write_bytes(b"a")
        (tmp_path / "b.txt").write_bytes(b"b")
        client = _make_client()
        calls: list[UploadResult] = []
        upload_directory(client, tmp_path, "repo", progress_cb=calls.append)
        assert len(calls) == 2
        assert all(isinstance(r, UploadResult) for r in calls)

    def test_result_local_path_is_absolute(self, tmp_path):
        (tmp_path / "file.txt").write_bytes(b"data")
        client = _make_client()
        results = upload_directory(client, tmp_path, "repo")
        assert results[0].local_path.is_absolute()
