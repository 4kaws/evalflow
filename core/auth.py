"""Shared Kaggle Bearer-auth helper."""
from __future__ import annotations

import os
from typing import Callable, Optional, Tuple


def make_bearer_client(
    username: str,
    api_key: str,
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[object, bool]:
    """Return (KaggleClient, bearer_ok).

    Upgrades to Bearer auth in priority order:
      1. KAGGLE_REFRESH_TOKEN env var — set as a GitHub/CI secret.
      2. ~/.kaggle/credentials.json  — written by `kaggle auth login`.
    Falls back to Basic auth (username + API key) if neither is available.
    Basic auth still works for Kernels API endpoints but is rejected by the
    Benchmark Tasks API for non-owned tasks.
    """
    from kagglesdk import KaggleClient

    def _log(msg: str) -> None:
        if log:
            log(msg)

    base_client = KaggleClient(username=username, password=api_key)

    try:
        from kagglesdk.kaggle_creds import KaggleCredentials

        refresh_token = os.environ.get("KAGGLE_REFRESH_TOKEN")
        if refresh_token:
            creds = KaggleCredentials(client=base_client, refresh_token=refresh_token)
            token = creds.get_access_token()
            if token:
                _log(f"Authenticated as {username}")
                return KaggleClient(api_token=token), True

        creds = KaggleCredentials.load(base_client)
        if creds:
            token = creds.get_access_token()
            if token:
                oauth_user = creds.get_username() or ""
                if oauth_user and oauth_user.lower() != username.lower():
                    _log(
                        f"[!] OAuth account mismatch: credentials.json is for '{oauth_user}' "
                        f"but KAGGLE_USERNAME is '{username}'.\n"
                        "    Re-run the wizard to fix — OAuth will not be used."
                    )
                    # fall through to basic auth
                else:
                    _log(f"Authenticated as {username} (Bearer)")
                    return KaggleClient(api_token=token), True
    except Exception:
        pass

    _log(
        "[!] OAuth not configured — only the latest run per task will be fetched.\n"
        "    Run the wizard or set KAGGLE_REFRESH_TOKEN to get all runs."
    )
    return base_client, False
