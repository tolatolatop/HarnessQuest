import secrets
from typing import Any
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.dependencies import get_current_user, require_admin
from app.models import User, UserRole
from app.schemas import LoginRequest, TokenResponse, UserCreate, UserRead
from app.security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == payload.username))
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserRead)
def me(user: User = Depends(get_current_user)) -> User:
    return user


@router.get("/oidc/status")
def oidc_status() -> dict[str, bool]:
    settings = get_settings()
    return {"enabled": bool(settings.oidc_enabled and settings.oidc_issuer and settings.oidc_client_id)}


@router.get("/oidc/login")
async def oidc_login(request: Request) -> RedirectResponse:
    settings = get_settings()
    if not settings.oidc_enabled or not settings.oidc_issuer or not settings.oidc_client_id:
        raise HTTPException(status_code=404, detail="OIDC is not enabled")
    config = await _oidc_config(settings.oidc_issuer)
    redirect_uri = settings.oidc_redirect_uri or str(request.url_for("oidc_callback"))
    params = {
        "client_id": settings.oidc_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "state": secrets.token_urlsafe(16),
    }
    return RedirectResponse(f"{config['authorization_endpoint']}?{urlencode(params)}")


@router.get("/oidc/callback", name="oidc_callback")
async def oidc_callback(code: str, request: Request, db: Session = Depends(get_db)) -> HTMLResponse:
    settings = get_settings()
    if not settings.oidc_enabled or not settings.oidc_issuer or not settings.oidc_client_id:
        raise HTTPException(status_code=404, detail="OIDC is not enabled")
    config = await _oidc_config(settings.oidc_issuer)
    redirect_uri = settings.oidc_redirect_uri or str(request.url_for("oidc_callback"))
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": settings.oidc_client_id,
    }
    if settings.oidc_client_secret:
        data["client_secret"] = settings.oidc_client_secret
    async with httpx.AsyncClient(timeout=20) as client:
        token_response = await client.post(config["token_endpoint"], data=data)
        token_response.raise_for_status()
        token_body = token_response.json()
        if not isinstance(token_body, dict) or not isinstance(token_body.get("access_token"), str):
            raise HTTPException(status_code=502, detail="OIDC token response did not include access token")
        access_token = token_body["access_token"]
        userinfo_response = await client.get(
            config["userinfo_endpoint"],
            headers={"Authorization": f"Bearer {access_token}"},
        )
        userinfo_response.raise_for_status()
    info = userinfo_response.json()
    if not isinstance(info, dict):
        raise HTTPException(status_code=502, detail="OIDC userinfo response must be an object")
    email = info.get("email")
    if not email:
        raise HTTPException(status_code=400, detail="OIDC userinfo did not include email")
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(
            email=email,
            display_name=info.get("name") or info.get("preferred_username") or email,
            role=UserRole.member,
            password_hash=None,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    token = create_access_token(user.id)
    html = f"""
    <html>
      <body>
        <script>
          localStorage.setItem('hq_token', {token!r});
          window.location.href = '/';
        </script>
      </body>
    </html>
    """
    return HTMLResponse(html)


@router.get("/users", response_model=list[UserRead])
def list_users(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.display_name)))


@router.post("/users", response_model=UserRead)
def create_user(payload: UserCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> User:
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status_code=409, detail="Email already exists")
    user = User(
        email=payload.email,
        display_name=payload.display_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


async def _oidc_config(issuer: str) -> dict[str, Any]:
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
    return config
