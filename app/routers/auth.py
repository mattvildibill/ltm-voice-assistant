from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlmodel import Session, select

from app.core.auth import get_current_user_id
from app.core.security import create_access_token, get_password_hash, verify_password
from app.db.database import get_session
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=128)
    display_name: str | None = Field(default=None, max_length=120)


class LoginRequest(BaseModel):
    email: str
    password: str


class UserPublic(BaseModel):
    id: str
    email: str
    display_name: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserPublic


def get_db_session():
    with get_session() as session:
        yield session


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register_user(
    payload: RegisterRequest,
    session: Session = Depends(get_db_session),
):
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address.")
    existing = session.exec(select(User).where(User.email == email)).first()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered.")

    user = User(
        email=email,
        password_hash=get_password_hash(payload.password),
        display_name=payload.display_name,
    )
    session.add(user)
    session.commit()
    session.refresh(user)

    access_token = create_access_token(
        subject=user.id,
        expires_delta=timedelta(minutes=60 * 24 * 7),
    )
    return TokenResponse(
        access_token=access_token,
        user=UserPublic(id=user.id, email=user.email, display_name=user.display_name),
    )


@router.post("/login", response_model=TokenResponse)
def login_user(
    payload: LoginRequest,
    session: Session = Depends(get_db_session),
):
    email = payload.email.strip().lower()
    if "@" not in email:
        raise HTTPException(status_code=400, detail="Invalid email address.")
    user = session.exec(select(User).where(User.email == email)).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials.")

    access_token = create_access_token(subject=user.id)
    return TokenResponse(
        access_token=access_token,
        user=UserPublic(id=user.id, email=user.email, display_name=user.display_name),
    )


@router.get("/me", response_model=UserPublic)
def me(
    session: Session = Depends(get_db_session),
    user_id: str = Depends(get_current_user_id),
):
    user = session.exec(select(User).where(User.id == user_id)).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return UserPublic(id=user.id, email=user.email, display_name=user.display_name)
