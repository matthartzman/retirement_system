#!/usr/bin/env python3
"""List GitHub Actions artifacts with age, size, expiry, and run links.

Examples:
    GH_TOKEN=... python scripts/list_github_artifacts.py --repo OWNER/REPO
    python scripts/list_github_artifacts.py --repo OWNER/REPO --format json

The token needs Actions read permission. If GH_TOKEN/GITHUB_TOKEN is not set,
the script tries to use `gh auth token` from an authenticated GitHub CLI session.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

API_ROOT = "https://api.github.com"
API_VERSION = "2022-11-28"


def get_token() -> str | None:
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        return token
    if shutil.which("gh"):
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=False
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    return None


def api_get(token: str, url: str) -> dict[str, object]:
    request = Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": API_VERSION,
            "User-Agent": "github-artifact-list-script",
        },
    )
    try:
        with urlopen(request, timeout=30) as response:
            data = json.load(response)
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Could not reach GitHub API: {exc.reason}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected response from GitHub API")
    return data


def list_artifacts(token: str, repo: str) -> list[dict[str, object]]:
    artifacts: list[dict[str, object]] = []
    page = 1
    while True:
        url = f"{API_ROOT}/repos/{repo}/actions/artifacts?per_page=100&page={page}"
        response = api_get(token, url)
        batch = response.get("artifacts")
        if not isinstance(batch, list):
            raise RuntimeError("GitHub API response did not contain an artifacts list")
        artifacts.extend(item for item in batch if isinstance(item, dict))
        if len(batch) < 100:
            return artifacts
        page += 1


def parse_date(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    except ValueError:
        return None


def human_size(value: object) -> str:
    try:
        size = float(value)
    except (TypeError, ValueError):
        return "?"
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{size:.0f} B"
        size /= 1024
    return "?"


def artifact_row(artifact: dict[str, object], repo: str, now: datetime) -> dict[str, object]:
    created = parse_date(artifact.get("created_at"))
    expires = parse_date(artifact.get("expires_at"))
    age_days = (now - created).total_seconds() / 86400 if created else None
    run = artifact.get("workflow_run")
    run_id = run.get("id") if isinstance(run, dict) else None
    return {
        "name": artifact.get("name") or "(unnamed)",
        "id": artifact.get("id"),
        "size_bytes": artifact.get("size_in_bytes", 0),
        "size": human_size(artifact.get("size_in_bytes", 0)),
        "created_at": created.isoformat(timespec="seconds") if created else "unknown",
        "age_days": round(age_days, 1) if age_days is not None else None,
        "expires_at": expires.isoformat(timespec="seconds") if expires else "unknown",
        "expired": bool(artifact.get("expired", False)),
        "run_id": run_id,
        "run_url": f"https://github.com/{repo}/actions/runs/{run_id}" if run_id else "",
        "branch": run.get("head_branch", "") if isinstance(run, dict) else "",
    }


def print_table(rows: list[dict[str, object]], repo: str) -> None:
    if not rows:
        print(f"No artifacts found for {repo}.")
        return

    headers = ("NAME", "AGE", "SIZE", "CREATED (UTC)", "EXPIRES (UTC)", "STATUS", "RUN", "BRANCH")
    values = []
    for row in rows:
        age = f"{row['age_days']} days" if row["age_days"] is not None else "unknown"
        status = "expired" if row["expired"] else "available"
        values.append((
            str(row["name"]), age, str(row["size"]), str(row["created_at"]),
            str(row["expires_at"]), status,
            str(row["run_url"] or "-"), str(row["branch"] or "-"),
        ))

    widths = [max(len(headers[i]), *(len(value[i]) for value in values)) for i in range(len(headers))]
    print("  ".join(headers[i].ljust(widths[i]) for i in range(len(headers))))
    print("  ".join("-" * width for width in widths))
    for value in values:
        print("  ".join(value[i].ljust(widths[i]) for i in range(len(headers))))

    total_bytes = sum(int(row["size_bytes"] or 0) for row in rows)
    expired_count = sum(bool(row["expired"]) for row in rows)
    print(f"\n{len(rows)} artifact(s); combined size {human_size(total_bytes)}; {expired_count} expired.")
    print("Run URLs link to the workflow run that produced each artifact.")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo", default=os.environ.get("GITHUB_REPOSITORY"),
        help="Repository in OWNER/REPO format (default: GITHUB_REPOSITORY)",
    )
    parser.add_argument(
        "--format", choices=("table", "json"), default="table",
        help="Output format (default: table)",
    )
    args = parser.parse_args()
    if not args.repo or args.repo.count("/") != 1:
        parser.error("--repo OWNER/REPO is required (or set GITHUB_REPOSITORY)")

    token = get_token()
    if not token:
        parser.error("Set GH_TOKEN/GITHUB_TOKEN or authenticate with `gh auth login`")

    try:
        now = datetime.now(timezone.utc)
        artifacts = list_artifacts(token, args.repo)
        artifacts.sort(key=lambda item: parse_date(item.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
        rows = [artifact_row(item, args.repo, now) for item in artifacts]
        if args.format == "json":
            print(json.dumps({"repository": args.repo, "count": len(rows), "artifacts": rows}, indent=2))
        else:
            print_table(rows, args.repo)
        return 0
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
