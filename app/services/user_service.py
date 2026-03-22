"""
User service — get or create a PredUser from an Auth0 token payload.
"""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.pred_user import PredUser


def get_or_create_pred_user(token_payload: dict[str, Any], session: Session) -> PredUser:
    """
    Upsert a PredUser based on the Auth0 token/userinfo payload.

    Works with both:
    - Access token payload (has 'sub')
    - Userinfo endpoint response (has 'sub', 'name', 'email', 'picture')

    Always updates last_login_at. Updates display_name/avatar if they changed in Auth0.
    """
    sub = token_payload.get("sub") or token_payload.get("auth0_sub")
    if not sub:
        raise ValueError("Token payload missing 'sub' claim")

    stmt = select(PredUser).where(PredUser.auth0_sub == sub)
    user = session.execute(stmt).scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if user is None:
        # First login — create new user
        display_name = (
            token_payload.get("name")
            or token_payload.get("nickname")
            or token_payload.get("email", "").split("@")[0]
            or "Player"
        )
        user = PredUser(
            auth0_sub=sub,
            display_name=display_name[:64],
            given_name=token_payload.get("given_name"),
            family_name=token_payload.get("family_name"),
            email=token_payload.get("email"),
            avatar_url=token_payload.get("picture"),
            created_at=now,
            last_login_at=now,
        )
        session.add(user)
    else:
        # Returning user — refresh timestamps and sync profile from Auth0
        user.last_login_at = now

        # Sync display_name if Auth0 has one and user hasn't customized it
        # (We don't track customization yet; future: add `display_name_customized` flag)
        if token_payload.get("name") and not user.display_name:
            user.display_name = token_payload["name"][:64]

        if token_payload.get("picture") and not user.avatar_url:
            user.avatar_url = token_payload["picture"]

        if token_payload.get("email") and not user.email:
            user.email = token_payload["email"]

        if token_payload.get("given_name") and not user.given_name:
            user.given_name = token_payload["given_name"]

        if token_payload.get("family_name") and not user.family_name:
            user.family_name = token_payload["family_name"]

    return user


def get_user_by_id(user_id: int, session: Session) -> PredUser | None:
    """Fetch a PredUser by primary key."""
    return session.get(PredUser, user_id)


def get_user_by_sub(auth0_sub: str, session: Session) -> PredUser | None:
    """Fetch a PredUser by Auth0 sub claim."""
    stmt = select(PredUser).where(PredUser.auth0_sub == auth0_sub)
    return session.execute(stmt).scalar_one_or_none()
