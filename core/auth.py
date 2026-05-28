"""Shared Kaggle Bearer-auth helper."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Callable, Optional, Tuple


def _oauth_refresh(base_client, refresh_token: str) -> Optional[str]:
    """Exchange a refresh token for a fresh OAuth access token.

    Uses the OAuth2 refresh_token grant, which returns a proper OAuth-scoped
    token accepted by the Benchmark Tasks API. The alternative
    (KaggleCredentials.refresh_access_token → GenerateAccessTokenRequest) hits
    a different endpoint that returns a legacy API-key token rejected by Tasks API.
    """
    from kagglesdk.security.types.oauth_service import ExchangeOAuthTokenRequest
    req = ExchangeOAuthTokenRequest()
    req.grant_type = "refresh_token"
    req.refresh_token = refresh_token
    resp = base_client.security.oauth_client.exchange_oauth_token(req)
    return resp.accessToken if resp and resp.accessToken else None


def make_bearer_client(
    username: str,
    api_key: str,
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[object, bool]:
    """Return (KaggleClient, bearer_ok).

    Upgrades to Bearer auth in priority order:
      1. KAGGLE_REFRESH_TOKEN env var — set as a GitHub/CI secret or by wizard.
      2. ~/.kaggle/credentials.json  — written by `kaggle auth login`.
    Falls back to Basic auth (username + API key) if neither is available.
    Basic auth still works for Kernels API endpoints but is rejected by the
    Benchmark Tasks API (returns 404 for any request, including the owner's).
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
            token = _oauth_refresh(base_client, refresh_token)
            if token:
                _log(f"Authenticated as {username} (Bearer)")
                return KaggleClient(api_token=token), True

        creds = KaggleCredentials.load(base_client)
        if creds and creds._refresh_token:
            # Use the OAuth refresh endpoint — NOT KaggleCredentials.refresh_access_token()
            # which calls GenerateAccessTokenRequest and returns a legacy token that the
            # Tasks API rejects with 404.
            access_token = creds._access_token
            expired = (
                not access_token
                or not creds._access_token_expiration
                or creds._access_token_expiration < datetime.now(timezone.utc)
            )
            if expired:
                access_token = _oauth_refresh(base_client, creds._refresh_token)
            if access_token:
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
                    return KaggleClient(api_token=access_token), True
    except Exception:
        pass

    _log(
        "[!] OAuth not configured — only the latest run per task will be fetched.\n"
        "    Run the wizard or set KAGGLE_REFRESH_TOKEN to get all runs."
    )
    return base_client, False
