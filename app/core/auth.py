from typing import Optional

from fastapi import Header

DEFAULT_USER_ID = "default-user"


def get_current_user_id(
    x_user_id: Optional[str] = Header(default=None, alias="X-User-Id")
) -> str:
    """
    Single-user mode: default to a shared user id unless a header overrides it.
    """
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    return DEFAULT_USER_ID
