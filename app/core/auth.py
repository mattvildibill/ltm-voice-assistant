from fastapi import Header, HTTPException, status

from app.core.security import decode_access_token


def get_current_user_id(authorization: str | None = Header(default=None)) -> str:
    """
    Resolve the current user identifier from Authorization bearer tokens.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required.",
        )
    token = authorization.split(" ", 1)[1].strip()
    user_id = decode_access_token(token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
        )
    return user_id
