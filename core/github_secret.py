"""
GitHub Actions secret utilities — encrypt and upsert secrets via the GitHub REST API.

This module is the single place that knows how to talk to GitHub secrets. Both
setup_wizard.py (bootstrap on first run) and monitor.py (sync after every check)
import from here so the encryption and auth logic never diverges.
"""
from __future__ import annotations


def put_secret(token: str, repo: str, name: str, plaintext: bytes) -> str:
    """
    Encrypt *plaintext* with the repo's Actions public key and upsert the secret.

    GitHub's PUT /actions/secrets/{name} is an upsert: it creates the secret if it
    does not exist, or silently overwrites it if it does. Call ensure_secret_seeded()
    instead when you want to leave an existing secret untouched.

    Returns a one-line human-readable status string (never raises).
    """
    import requests
    from base64 import b64decode, b64encode

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        pk_r = requests.get(
            f"https://api.github.com/repos/{repo}/actions/secrets/public-key",
            headers=headers,
            timeout=10,
        )
        pk_r.raise_for_status()
        pk_data = pk_r.json()
    except Exception as exc:
        return f"[!]   Could not fetch repo public key: {exc}"

    try:
        from nacl import encoding, public as nacl_public
        pk = nacl_public.PublicKey(b64decode(pk_data["key"]), encoding.RawEncoder)
        box = nacl_public.SealedBox(pk)
        encrypted = b64encode(box.encrypt(plaintext)).decode()
    except Exception as exc:
        return f"[!]   Encryption failed: {exc}"

    try:
        put_r = requests.put(
            f"https://api.github.com/repos/{repo}/actions/secrets/{name}",
            headers=headers,
            json={"encrypted_value": encrypted, "key_id": pk_data["key_id"]},
            timeout=10,
        )
        put_r.raise_for_status()
        return f"[+]   {name} secret saved to GitHub."
    except Exception as exc:
        try:
            code = put_r.status_code
        except Exception:
            code = "?"
        if str(code) in ("401", "403"):
            return (
                f"[!]   {name}: HTTP {code} — your PAT needs "
                "'Secrets: read & write' permission on this repo."
            )
        return f"[!]   {name}: {exc}"


def ensure_secret_seeded(token: str, repo: str, name: str, default: bytes) -> str:
    """
    Create a GitHub Actions secret with *default* value only if it does not already exist.

    Used by the setup wizard to seed EVALFLOW_MANIFEST with '{}' on first run so the
    daily CI schedule can start immediately — without the user manually creating the
    secret in GitHub Settings.

    If the secret already exists (from a previous wizard run or a monitor sync), it is
    left completely unchanged. Returns a one-line human-readable status string (never raises).
    """
    import requests

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    try:
        r = requests.get(
            f"https://api.github.com/repos/{repo}/actions/secrets/{name}",
            headers=headers,
            timeout=10,
        )
        if r.status_code == 200:
            return f"[ok]  {name} already exists on GitHub — left unchanged."
        if r.status_code in (401, 403):
            return (
                f"[!]   {name}: HTTP {r.status_code} — your PAT needs "
                "'Secrets: read & write' permission on this repo."
            )
        if r.status_code != 404:
            return f"[!]   {name} check failed: HTTP {r.status_code}"
    except Exception as exc:
        return f"[!]   {name} check failed: {exc}"

    # Secret does not exist — create it with the default value.
    return put_secret(token, repo, name, default)
