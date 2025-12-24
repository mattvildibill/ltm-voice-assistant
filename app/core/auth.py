from fastapi import Header


def get_current_user_id(x_user_id: str | None = Header(default=None)) -> str:
    """
    Resolve the current user identifier from headers.
    Defaults to "default-user" for backward compatibility if header is missing.
    """
    if x_user_id and x_user_id.strip():
        return x_user_id.strip()
    return "default-user"
