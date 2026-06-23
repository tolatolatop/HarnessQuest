import secrets
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import HTTPException

from app.config import Settings
import re


@dataclass(frozen=True)
class OAuthEndpoints:
    authorization_url: str
    token_url: str
    userinfo_url: str
    email_url: str | None = None


@dataclass(frozen=True)
class OAuthProviderConfig:
    provider: str
    client_id: str
    client_secret: str | None
    redirect_uri: str
    scope: str
    endpoints: OAuthEndpoints


@dataclass(frozen=True)
class ExternalUser:
    email: str
    display_name: str
    provider: str
    provider_user_id: str | None = None


def oauth_enabled(settings: Settings) -> bool:
    if settings.oauth_enabled and settings.oauth_client_id:
        return True
    return bool(settings.oidc_enabled and settings.oidc_issuer and settings.oidc_client_id)


async def provider_config(settings: Settings, callback_url: str) -> OAuthProviderConfig:
    provider = (settings.oauth_provider or "oidc").lower()
    client_id = settings.oauth_client_id or settings.oidc_client_id
    client_secret = settings.oauth_client_secret or settings.oidc_client_secret
    redirect_uri = settings.oauth_redirect_uri or settings.oidc_redirect_uri or callback_url
    scope = settings.oauth_scope or "openid email profile"
    if not oauth_enabled(settings) or not client_id:
        raise HTTPException(status_code=404, detail="OAuth is not enabled")

    if provider == "github":
        endpoints = OAuthEndpoints(
            authorization_url=settings.oauth_authorization_url or "https://github.com/login/oauth/authorize",
            token_url=settings.oauth_token_url or "https://github.com/login/oauth/access_token",
            userinfo_url=settings.oauth_userinfo_url or "https://api.github.com/user",
            email_url=settings.oauth_email_url or "https://api.github.com/user/emails",
        )
        scope = settings.oauth_scope or "read:user user:email"
    elif settings.oauth_authorization_url and settings.oauth_token_url and settings.oauth_userinfo_url:
        endpoints = OAuthEndpoints(
            authorization_url=settings.oauth_authorization_url,
            token_url=settings.oauth_token_url,
            userinfo_url=settings.oauth_userinfo_url,
            email_url=settings.oauth_email_url,
        )
    else:
        issuer = settings.oidc_issuer
        if not issuer:
            raise HTTPException(status_code=404, detail="OIDC issuer is not configured")
        endpoints = await oidc_endpoints(issuer)

    return OAuthProviderConfig(
        provider=provider,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scope=scope,
        endpoints=endpoints,
    )


async def oidc_endpoints(issuer: str) -> OAuthEndpoints:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(f"{issuer.rstrip('/')}/.well-known/openid-configuration")
        response.raise_for_status()
    config = response.json()
    if not isinstance(config, dict):
        raise HTTPException(status_code=500, detail="OIDC discovery response must be an object")
    required = ["authorization_endpoint", "token_endpoint", "userinfo_endpoint"]
    missing = [key for key in required if key not in config]
    if missing:
        raise HTTPException(status_code=500, detail=f"OIDC discovery missing: {', '.join(missing)}")
    return OAuthEndpoints(
        authorization_url=str(config["authorization_endpoint"]),
        token_url=str(config["token_endpoint"]),
        userinfo_url=str(config["userinfo_endpoint"]),
    )


def new_state() -> str:
    return secrets.token_urlsafe(24)


def authorization_url(config: OAuthProviderConfig, state: str) -> str:
    params = {
        "client_id": config.client_id,
        "redirect_uri": config.redirect_uri,
        "response_type": "code",
        "scope": config.scope,
        "state": state,
    }
    return f"{config.endpoints.authorization_url}?{urlencode(params)}"


async def exchange_code(config: OAuthProviderConfig, code: str) -> str:
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.redirect_uri,
        "client_id": config.client_id,
    }
    if config.client_secret:
        data["client_secret"] = config.client_secret
    headers = {"Accept": "application/json"}
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post(config.endpoints.token_url, data=data, headers=headers)
        response.raise_for_status()
    token_body = response.json()
    if not isinstance(token_body, dict) or not isinstance(token_body.get("access_token"), str):
        raise HTTPException(status_code=502, detail="OAuth token response did not include access token")
    return token_body["access_token"]


async def fetch_external_user(config: OAuthProviderConfig, access_token: str, settings: Settings | None = None) -> ExternalUser:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(
            config.endpoints.userinfo_url,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
        )
        response.raise_for_status()
        info = response.json()
        if not isinstance(info, dict):
            raise HTTPException(status_code=502, detail="OAuth userinfo response must be an object")
        email = _resolve_with_fallback(info, settings.oauth_map_email if settings else None, lambda: _str_or_none(info.get("email")))
        if not email and config.endpoints.email_url:
            email = await _fetch_primary_email(client, config.endpoints.email_url, access_token)
    if not email:
        raise HTTPException(status_code=400, detail="OAuth userinfo did not include email")
    display_name = _resolve_with_fallback(
        info,
        settings.oauth_map_display_name if settings else None,
        lambda: _str_or_none(info.get("name")) or _str_or_none(info.get("preferred_username")) or _str_or_none(info.get("login")) or email,
    )
    provider_user_id = _str_or_none(info.get("sub")) or _str_or_none(info.get("id"))
    return ExternalUser(email=email, display_name=display_name, provider=config.provider, provider_user_id=provider_user_id)


async def _fetch_primary_email(client: httpx.AsyncClient, email_url: str, access_token: str) -> str | None:
    response = await client.get(
        email_url,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    response.raise_for_status()
    emails = response.json()
    if not isinstance(emails, list):
        return None
    for item in emails:
        if isinstance(item, dict) and item.get("primary") and item.get("verified") and isinstance(item.get("email"), str):
            return item["email"]
    for item in emails:
        if isinstance(item, dict) and item.get("verified") and isinstance(item.get("email"), str):
            return item["email"]
    return None


def _str_or_none(value: Any) -> str | None:
    if isinstance(value, str) and value:
        return value
    if isinstance(value, int):
        return str(value)
    return None


def _resolve_with_fallback(info: dict, mapping: str | None, default_fn) -> str | None:
    """Resolve a field from userinfo using mapping spec, or fall back to default."""
    if not mapping:
        return default_fn()
    value = resolve_field(info, mapping)
    return value if value is not None else default_fn()


def resolve_field(userinfo: dict, spec: str) -> str | None:
    """Resolve a field from userinfo dict using dot-path | fallback spec."""
    if spec.startswith("="):
        return spec[1:]
    for path in spec.split("|"):
        value = _resolve_path(userinfo, path.strip())
        if value is not None:
            return _str_or_none(value)
    return None


def _resolve_path(data: dict, path: str) -> Any:
    """Traverse a dot-path into a dict, supporting array index [N]."""
    parts = [p for p in re.split(r'[.\[\]]+', path) if p]
    current = data
    for part in parts:
        if isinstance(current, dict):
            current = current.get(part)
        elif isinstance(current, (list, tuple)):
            try:
                current = current[int(part)]
            except (IndexError, ValueError):
                return None
        else:
            return None
    return current
