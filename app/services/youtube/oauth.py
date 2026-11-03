"""Google OAuth 2.0 for the YouTube APIs: one-time consent, then unattended access with a refresh token.

The refresh token is obtained once with scripts/youtube_auth.py (desktop "installed app" flow: a
loopback redirect on 127.0.0.1 plus PKCE). Afterwards the pipeline exchanges it for short-lived
access tokens (~1 h) whenever it needs one, with no browser and no human.

A refresh token stops working when:
- the OAuth consent screen is in "Testing" (External): Google expires it after 7 days.
  Publish the app ("In production") to avoid this.
- you revoke access (myaccount.google.com/permissions) or change the Google account password
  (for tokens that include Gmail/YouTube-sensitive scopes Google may revoke them);
- it is not used for 6 months;
- more than 100 refresh tokens exist for the same account and client (the oldest dies).
"""

from __future__ import annotations

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass, field
from urllib.parse import urlencode

import httpx

from app.core.errors import IntegrationNotConfiguredError, ProviderError

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"

SCOPES = {
    # Upload videos and set thumbnails.
    "upload": "https://www.googleapis.com/auth/youtube.upload",
    # Read your channel and your videos' processing status (videos.list, channels.list).
    "readonly": "https://www.googleapis.com/auth/youtube.readonly",
    # Read YouTube Analytics reports (views, watch time, retention...).
    "analytics": "https://www.googleapis.com/auth/yt-analytics.readonly",
    # Optional: post comments (commentThreads.insert). Broad scope ("manage your YouTube account").
    "comments": "https://www.googleapis.com/auth/youtube.force-ssl",
}
DEFAULT_SCOPES = ("upload", "readonly", "analytics")


def scope_urls(names: tuple[str, ...] | list[str]) -> list[str]:
    unknown = [n for n in names if n not in SCOPES]
    if unknown:
        raise ValueError(f"Unknown scopes {unknown}; use {sorted(SCOPES)}.")
    return [SCOPES[n] for n in names]


def pkce_pair() -> tuple[str, str]:
    """(code_verifier, code_challenge) for PKCE with S256."""
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def build_auth_url(client_id: str, redirect_uri: str, scopes: list[str], state: str, code_challenge: str) -> str:
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        # offline + consent: Google returns a refresh token (and a new one on every consent).
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


def exchange_code(
    http: httpx.Client, client_id: str, client_secret: str, code: str, redirect_uri: str, code_verifier: str
) -> dict:
    response = http.post(
        TOKEN_URL,
        data={
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "code_verifier": code_verifier,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
    )
    if response.status_code != 200:
        raise ProviderError(f"Google refused the authorization code: {_google_error(response)}")
    data = response.json()
    if "refresh_token" not in data:
        raise ProviderError(
            "Google returned no refresh token. Remove the app's access at myaccount.google.com/permissions "
            "and authorize again (the flow already asks for offline access with prompt=consent)."
        )
    return data


def _google_error(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code}"
    error = body.get("error")
    if isinstance(error, dict):  # API style: {"error": {"code", "message", "errors": [{"reason"}]}}
        reasons = ",".join(e.get("reason", "") for e in error.get("errors", []))
        return f"HTTP {response.status_code} {reasons} {error.get('message', '')}".strip()
    return f"HTTP {response.status_code} {error} {body.get('error_description', '')}".strip()


@dataclass
class GoogleCredentials:
    """Refresh-token credentials. The access token is kept in memory only, never written anywhere."""

    client_id: str
    client_secret: str
    refresh_token: str
    _access_token: str | None = field(default=None, repr=False)
    _expires_at: float = field(default=0.0, repr=False)

    def __repr__(self) -> str:  # never leak secrets into logs
        return "GoogleCredentials(<redacted>)"

    def access_token(self, http: httpx.Client, *, force: bool = False) -> str:
        if not force and self._access_token and time.time() < self._expires_at - 60:
            return self._access_token
        response = http.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self.refresh_token,
                "grant_type": "refresh_token",
            },
        )
        if response.status_code in (400, 401):
            detail = _google_error(response)
            if "invalid_grant" in detail:
                raise IntegrationNotConfiguredError(
                    "The YouTube refresh token is expired or revoked. If the OAuth consent screen is in "
                    "'Testing', tokens expire after 7 days: publish the app to 'In production', then run "
                    "scripts/youtube_auth.py again and update YOUTUBE_REFRESH_TOKEN."
                )
            raise IntegrationNotConfiguredError(f"Google rejected the OAuth client: {detail}")
        if response.status_code != 200:
            raise ProviderError(f"Token refresh failed: {_google_error(response)}")
        data = response.json()
        self._access_token = data["access_token"]
        self._expires_at = time.time() + int(data.get("expires_in", 3600))
        return self._access_token


def credentials_from_settings(settings) -> GoogleCredentials:
    if not settings.youtube_configured:
        raise IntegrationNotConfiguredError(
            "YouTube is not configured. Set YOUTUBE_CLIENT_ID, YOUTUBE_CLIENT_SECRET and YOUTUBE_REFRESH_TOKEN "
            "(see docs/AUTOMATION.md, section YouTube)."
        )
    return GoogleCredentials(
        settings.youtube_client_id.get_secret_value(),
        settings.youtube_client_secret.get_secret_value(),
        settings.youtube_refresh_token.get_secret_value(),
    )


class GoogleAPI:
    """Small authorized HTTP helper: refreshes the token once on 401 and maps Google errors."""

    def __init__(self, credentials: GoogleCredentials, http: httpx.Client | None = None) -> None:
        self.credentials = credentials
        self.http = http or httpx.Client(timeout=httpx.Timeout(60.0, connect=20.0))

    def request(self, method: str, url: str, *, headers: dict | None = None, **kwargs) -> httpx.Response:
        """Bodies must be bytes/JSON (not streams) so a request can be re-sent after a token refresh."""
        base = dict(headers or {})
        response = None
        for attempt in range(2):
            token = self.credentials.access_token(self.http, force=attempt > 0)
            response = self.http.request(method, url, headers={**base, "Authorization": f"Bearer {token}"}, **kwargs)
            if response.status_code != 401:
                break
        return response

    def json(self, method: str, url: str, **kwargs) -> dict:
        response = self.request(method, url, **kwargs)
        if response.status_code >= 400:
            raise_for_google(response)
        return response.json() if response.content else {}


def raise_for_google(response: httpx.Response) -> None:
    detail = _google_error(response)
    if response.status_code == 403 and "quotaExceeded" in detail:
        raise ProviderError(f"YouTube API daily quota exhausted (resets at midnight Pacific time): {detail}")
    if response.status_code == 403 and "uploadLimitExceeded" in detail:
        raise ProviderError(f"YouTube's upload limit for this channel was reached; try again tomorrow: {detail}")
    if response.status_code == 403 and ("insufficientPermissions" in detail or "ACCESS_TOKEN_SCOPE" in detail):
        raise IntegrationNotConfiguredError(
            f"The refresh token lacks a required scope; run scripts/youtube_auth.py again: {detail}"
        )
    if response.status_code == 403 and "forbidden" in detail.lower() and "thumbnail" in str(response.url):
        raise ProviderError(
            "Custom thumbnails are not allowed yet: verify the channel by phone at youtube.com/verify. " + detail
        )
    raise ProviderError(f"YouTube API error: {detail}")
