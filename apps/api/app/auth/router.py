from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import service
from app.auth.deps import current_user
from app.auth.schemas import LoginRequest, RefreshRequest, RegisterRequest, TokenPair, UserOut
from app.db.models import User
from app.db.session import get_db
from app.security.ratelimit import rate_limit

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=TokenPair, status_code=201, dependencies=[Depends(rate_limit("register", 10))])
async def register(body: RegisterRequest, session: AsyncSession = Depends(get_db)) -> TokenPair:
    user = await service.register(session, email=body.email, password=body.password, display_name=body.display_name)
    return await service.issue_tokens(session, user)


@router.post("/login", response_model=TokenPair, dependencies=[Depends(rate_limit("login", 20))])
async def login(body: LoginRequest, session: AsyncSession = Depends(get_db)) -> TokenPair:
    user = await service.authenticate(session, email=body.email, password=body.password)
    return await service.issue_tokens(session, user)


@router.post("/refresh", response_model=TokenPair, dependencies=[Depends(rate_limit("refresh", 60))])
async def refresh(body: RefreshRequest, session: AsyncSession = Depends(get_db)) -> TokenPair:
    user = await service.rotate_refresh_token(session, body.refresh_token)
    return await service.issue_tokens(session, user)


@router.post("/logout", status_code=204)
async def logout(body: RefreshRequest, session: AsyncSession = Depends(get_db)):  # noqa: ANN201 - 204, no body
    await service.revoke_refresh_token(session, body.refresh_token)


@router.post("/logout-all", status_code=204)
async def logout_all(user: User = Depends(current_user), session: AsyncSession = Depends(get_db)):  # noqa: ANN201
    await service.revoke_all_sessions(session, user.id)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(current_user)) -> User:
    return user
