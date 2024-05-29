import datetime
from datetime import timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm, SecurityScopes
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlmodel import Field, SQLModel

from app.config import settings, scope_descriptor, access

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", scopes=scope_descriptor)

inactive_user_exception = HTTPException(
    status_code=status.HTTP_400_BAD_REQUEST,
    detail="The current user has been disabled.",
)

FAKE_DB = {
    "admin": {
        "id": 1,
        "username": "admin",
        "email": "admin@host.com",
        "disabled": False,
        "access": "admin"
    },
    "user": {"id": 2, "username": "user", "email": "user@host.com", "disabled": False, "access": "player"},
    "disabled": {
        "id": 3,
        "username": "disabled",
        "email": "disabled@host.com",
        "disabled": True,
        "access": "player"
    },
}


class Token(BaseModel):
    access_token: str
    token_type: str


class TokenData(BaseModel):
    username: str | None = None
    scopes: list[str] = []


class User(SQLModel):
    id: int | None = Field(description="User ID", primary_key=True, nullable=False)
    username: str = Field(description="Username", nullable=False)
    email: str = Field(description="User email", nullable=False)
    disabled: bool = Field(description="Account status")
    access: list[str] = Field(description="Account API access")


class UserDB(User, table=True):
    hashed_password: str


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def hash_password(password: str):
    password = password + settings.PASSWORD_SALT
    return pwd_context.hash(password)


def get_user(db, username: str):
    if username in db:
        return UserDB(**db[username])


def auth_user(db, username: str, password: str):
    user = get_user(db, username)
    if not user:
        return False
    if not verify_password(password, user.hashed_password):
        return False
    return user


def create_access_token(data: dict, expires_delta: timedelta | None = None):
    to_encode = data.copy()
    expires_delta = expires_delta or timedelta(minutes=15)
    expire_time = datetime.now(timezone.utc) + expires_delta
    to_encode.update({"exp": expire_time})
    encoded_jwt = jwt.encode(
        to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )
    return encoded_jwt

async def get_current_user(scopes: SecurityScopes,  token: Annotated[str, Depends(oauth2_scheme)]):

    # Compose auth format
    if scopes.scopes:
        authenticate_value = f'Bearer scope="{scopes.scope_str}"'
    else:
        authenticate_value = "Bearer"

    # Exceptions
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": authenticate_value},
    )
    access_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not enough permissions",
        headers={"WWW-Authenticate": authenticate_value},
    )

    # Decode the payload
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        requested_scopes = payload.get("scopes", [])
    except JWTError as e:
        raise credentials_exception from e

    # Validate user data
    user = get_user(FAKE_DB, username=username)
    if user is None:
        raise credentials_exception

    # Only allow access if the user requested scopes they have access to
    permitted_scopes = user.access
    for scope in requested_scopes:
        if scope not in permitted_scopes:
            raise access_exception

    return user

async def get_current_active_user(current_user: Annotated[User, Security(get_current_user, scopes=[access.PLAYER])]):
    if current_user.disabled:
        raise inactive_user_exception
    return current_user


async def login_for_access_token(form_data: Annotated[OAuth2PasswordRequestForm, Depends()]) -> Token:
    user = auth_user(FAKE_DB, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail="Invalid username or password"
        )
    access_token_expires = timedelta(minutes=settings.DEFAULT_TOKEN_EXPIRY)
    access_token = create_access_token(
        data={"sub": user.username}, expires_delta=access_token_expires
    )
    return Token(access_token=access_token, token_type="bearer")


async def read_user(current_user: Annotated[User, Depends(get_current_active_user)]):
    return current_user

async def read_other_user(current_user: Annotated[User, Depends]):
    pass


def register_security_routes(router: APIRouter):
    router.add_api_route(
        "/token",
        login_for_access_token,
        methods=["POST"],
        description="Submit OAuth2 form to login",
    )
    router.add_api_route(
        "/user",
        read_user,
        methods=["GET"],
        description=""
    )
