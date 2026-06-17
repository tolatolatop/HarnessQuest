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
from app.services.oauth import authorization_url, exchange_code, fetch_external_user, new_state, oauth_enabled, provider_config

router = APIRouter(prefix="/auth", tags=["auth"])
OAUTH_STATE_COOKIE = "hq_oauth_state"


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
    return {"enabled": oauth_enabled(settings)}


@router.get("/oidc/login")
async def oidc_login(request: Request) -> RedirectResponse:
    return await _start_oauth(request, "oidc_callback")


@router.get("/oauth/status")
def oauth_status() -> dict[str, bool]:
    settings = get_settings()
    return {"enabled": oauth_enabled(settings)}


@router.get("/oauth/login")
async def oauth_login(request: Request) -> RedirectResponse:
    return await _start_oauth(request, "oauth_callback")


@router.get("/oidc/callback", name="oidc_callback")
async def oidc_callback(code: str, request: Request, state: str | None = None, db: Session = Depends(get_db)) -> HTMLResponse:
    return await _finish_oauth(code, request, state, "oidc_callback", db)


@router.get("/oauth/callback", name="oauth_callback")
async def oauth_callback(
    code: str,
    request: Request,
    state: str | None = None,
    db: Session = Depends(get_db),
) -> HTMLResponse:
    return await _finish_oauth(code, request, state, "oauth_callback", db)


async def _start_oauth(request: Request, callback_route_name: str) -> RedirectResponse:
    config = await provider_config(get_settings(), str(request.url_for(callback_route_name)))
    state = new_state()
    response = RedirectResponse(authorization_url(config, state))
    response.set_cookie(
        OAUTH_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
    )
    return response


async def _finish_oauth(
    code: str,
    request: Request,
    state: str | None,
    callback_route_name: str,
    db: Session,
) -> HTMLResponse:
    cookie_state = request.cookies.get(OAUTH_STATE_COOKIE)
    if not state or not cookie_state or state != cookie_state:
        raise HTTPException(status_code=400, detail="Invalid OAuth state")
    config = await provider_config(get_settings(), str(request.url_for(callback_route_name)))
    access_token = await exchange_code(config, code)
    external_user = await fetch_external_user(config, access_token)
    user = db.scalar(select(User).where(User.email == external_user.email))
    if not user:
        user = User(
            email=external_user.email,
            display_name=external_user.display_name,
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
    response = HTMLResponse(html)
    response.delete_cookie(OAUTH_STATE_COOKIE)
    return response


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
