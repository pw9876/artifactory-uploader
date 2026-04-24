"""Tests for artifactory_uploader.cli."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from click.testing import CliRunner

from artifactory_uploader.cli import main
from artifactory_uploader.uploader import UploadResult


def _base_args(source: str) -> list[str]:
    return [
        "--url",
        "https://acme.jfrog.io/artifactory",
        "--repo",
        "my-repo",
        "--source",
        source,
        "--api-key",
        "key123",
    ]


class TestCLI:
    def test_upload_success(self, tmp_path):
        runner = CliRunner()
        result_obj = UploadResult(
            local_path=tmp_path / "file.txt",
            remote_url="https://acme.jfrog.io/artifactory/my-repo/file.txt",
        )
        with patch("artifactory_uploader.cli.upload_directory", return_value=[result_obj]):
            result = runner.invoke(main, _base_args(str(tmp_path)))
        assert result.exit_code == 0
        assert "Done" in result.output

    def test_missing_auth_rejected(self, tmp_path):
        runner = CliRunner()
        args = ["--url", "https://acme.jfrog.io", "--repo", "repo", "--source", str(tmp_path)]
        result = runner.invoke(main, args)
        assert result.exit_code != 0
        assert (
            "authentication" in result.output.lower()
            or "authentication" in (result.stderr or "").lower()
        )

    def test_token_auth_accepted(self, tmp_path):
        runner = CliRunner()
        args = [
            "--url",
            "https://acme.jfrog.io/artifactory",
            "--repo",
            "my-repo",
            "--source",
            str(tmp_path),
            "--token",
            "tok123",
        ]
        with patch("artifactory_uploader.cli.upload_directory", return_value=[]):
            result = runner.invoke(main, args)
        assert result.exit_code == 0

    def test_dry_run_shown_in_output(self, tmp_path):
        runner = CliRunner()
        result_obj = UploadResult(
            local_path=tmp_path / "file.txt",
            remote_url="https://acme.jfrog.io/artifactory/my-repo/file.txt",
            dry_run=True,
        )
        with patch("artifactory_uploader.cli.upload_directory", return_value=[result_obj]):
            result = runner.invoke(main, _base_args(str(tmp_path)) + ["--dry-run"])
        assert result.exit_code == 0
        assert "DRY RUN" in result.output
        assert "Would upload" in result.output

    def test_target_prefix_passed_to_uploader(self, tmp_path):
        runner = CliRunner()
        with patch("artifactory_uploader.cli.upload_directory", return_value=[]) as mock_ul:
            runner.invoke(main, _base_args(str(tmp_path)) + ["--target", "releases/1.0"])
            assert mock_ul.call_args.kwargs["target_prefix"] == "releases/1.0"

    def test_exclude_patterns_passed_to_uploader(self, tmp_path):
        runner = CliRunner()
        with patch("artifactory_uploader.cli.upload_directory", return_value=[]) as mock_ul:
            runner.invoke(main, _base_args(str(tmp_path)) + ["--exclude", "*.log"])
            assert "*.log" in mock_ul.call_args.kwargs["exclude"]

    def test_empty_source_warns(self, tmp_path):
        runner = CliRunner(mix_stderr=False)
        with patch("artifactory_uploader.cli.upload_directory", return_value=[]):
            result = runner.invoke(main, _base_args(str(tmp_path)))
        assert "Warning" in result.stderr

    def test_keyboard_interrupt_exits_cleanly(self, tmp_path):
        runner = CliRunner()
        with patch("artifactory_uploader.cli.upload_directory", side_effect=KeyboardInterrupt):
            result = runner.invoke(main, _base_args(str(tmp_path)))
        assert result.exit_code == 1

    def test_env_var_url(self, tmp_path):
        runner = CliRunner()
        args = ["--repo", "my-repo", "--source", str(tmp_path), "--api-key", "k"]
        with patch("artifactory_uploader.cli.upload_directory", return_value=[]):
            result = runner.invoke(main, args, env={"ARTIFACTORY_URL": "https://env.example.com"})
        assert result.exit_code == 0

    def test_progress_output_per_file(self, tmp_path):
        runner = CliRunner()
        result_obj = UploadResult(
            local_path=tmp_path / "report.pdf",
            remote_url="https://acme.jfrog.io/artifactory/my-repo/report.pdf",
        )

        def fake_upload(**kwargs):
            kwargs["progress_cb"](result_obj)
            return [result_obj]

        with patch("artifactory_uploader.cli.upload_directory", side_effect=fake_upload):
            result = runner.invoke(main, _base_args(str(tmp_path)))
        assert "report.pdf" in result.output
