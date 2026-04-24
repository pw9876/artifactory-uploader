"""CLI entry point for artifactory-uploader."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from artifactory_uploader.uploader import ArtifactoryClient, upload_directory


@click.command()
@click.option(
    "--url",
    envvar="ARTIFACTORY_URL",
    required=True,
    help="Artifactory base URL (e.g. https://company.jfrog.io/artifactory). "
    "Can also be set via ARTIFACTORY_URL.",
)
@click.option(
    "--repo",
    envvar="ARTIFACTORY_REPO",
    required=True,
    help="Repository key to upload into. Can also be set via ARTIFACTORY_REPO.",
)
@click.option(
    "--source",
    "-s",
    required=True,
    type=click.Path(exists=True, file_okay=False, readable=True),
    help="Local directory to upload.",
)
@click.option(
    "--target",
    "-t",
    default="",
    help="Remote path prefix within the repository (default: repo root).",
)
@click.option(
    "--api-key",
    envvar="ARTIFACTORY_API_KEY",
    default=None,
    help="Artifactory API key. Can also be set via ARTIFACTORY_API_KEY.",
)
@click.option(
    "--token",
    envvar="ARTIFACTORY_TOKEN",
    default=None,
    help="Artifactory access token. Can also be set via ARTIFACTORY_TOKEN.",
)
@click.option(
    "--exclude",
    "-e",
    multiple=True,
    help="Glob pattern to exclude (e.g. '*.log'). Can be specified multiple times.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Show what would be uploaded without uploading.",
)
def main(
    url: str,
    repo: str,
    source: str,
    target: str,
    api_key: str | None,
    token: str | None,
    exclude: tuple[str, ...],
    dry_run: bool,
) -> None:
    """Upload a local directory tree to Artifactory, preserving structure.

    \b
    Examples:
      artifactory-uploader --url https://acme.jfrog.io/artifactory --repo libs-release -s ./dist
      artifactory-uploader --url $URL --repo my-repo --source ./build --target releases/1.0
      artifactory-uploader --url $URL --repo my-repo --source ./artifacts --dry-run
    """
    if not api_key and not token:
        raise click.UsageError(
            "Provide authentication via --api-key / ARTIFACTORY_API_KEY "
            "or --token / ARTIFACTORY_TOKEN."
        )

    source_path = Path(source)
    client = ArtifactoryClient(base_url=url, api_key=api_key, token=token)

    mode = "[DRY RUN] " if dry_run else ""
    click.echo(f"{mode}URL    : {url}")
    click.echo(f"{mode}Repo   : {repo}")
    click.echo(f"{mode}Source : {source_path.resolve()}")
    if target:
        click.echo(f"{mode}Target : {target}")
    if exclude:
        click.echo(f"{mode}Exclude: {', '.join(exclude)}")
    click.echo()

    uploaded = 0

    def on_result(result):
        nonlocal uploaded
        uploaded += 1
        prefix = "[DRY RUN] " if result.dry_run else ""
        click.echo(f"{prefix}[{uploaded}] {result.local_path.name} -> {result.remote_url}")

    try:
        results = upload_directory(
            client=client,
            source_dir=source_path,
            repo=repo,
            target_prefix=target,
            dry_run=dry_run,
            exclude=list(exclude),
            progress_cb=on_result,
        )
    except KeyboardInterrupt:
        click.echo("\nInterrupted.", err=True)
        sys.exit(1)

    click.echo()
    action = "Would upload" if dry_run else "Uploaded"
    click.echo(f"Done. {action} {len(results)} file(s).")

    if not results:
        click.echo(
            f"Warning: no files found in {source_path.resolve()}",
            err=True,
        )
