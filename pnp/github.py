"""Communicate with GitHub using GITHUB API, and create release and upload assets."""
# ======================== STANDARDS =========================
from typing import NoReturn
import os

# ====================== THIRD PARTIES =======================
import requests

# ========================== LOCALS ==========================
from ._constants import GITHUB as API


def create_release(token: str, repo: str, tag: str,
                   name: str | None = None,
                   body: str | None = None,
                   draft: bool = False,
                   prerelease: bool = False
                   ) -> dict | NoReturn:
    """
    Create a GitHub release.

    Args
        token: Personal Access Token with repo scope
        repo: full_name e.g., "username/repo"
        tag: tag to release
        name: Release title
        body: release notes
    """
    url     = f"{API}/repos/{repo}/releases"
    headers = {"Authorization": f"token {token}"}
    data    = {
        "tag_name": tag,
        "name": name or tag,
        "body": body or "",
        "draft": draft,
        "prerelease": prerelease
    }
    r = requests.post(url, headers=headers, json=data,
        timeout=10)
    if r.status_code not in (200, 201):
        raise RuntimeError("GitHub release creation failed:"
            + f" {r.status_code} {r.text}")
    return r.json()


def upload_asset(token: str, repo: str, release_id: int,
                 filepath: str, label: str | None = None
                 ) -> dict | NoReturn:
    """Upload asset to existing release."""
    url = f"https://uploads.github.com/repos/{repo}/" \
        + f"releases/{release_id}/assets"
    params = {"name": os.path.basename(filepath)}
    if label: params["label"] = label
    headers = {
        "Authorization": f"token {token}",
        "Content-Type": "application/octet-stream"
    }
    with open(filepath, "rb") as f:
        r = requests.post(url, headers=headers,
            params=params, data=f, timeout=10)
    if r.status_code not in (200, 201):
        raise RuntimeError("Asset upload failed: "
            + f"{r.status_code} {r.text}")
    return r.json()
