from enum import Enum
from pydantic import BaseModel, BaseSettings


class Settings(BaseSettings):
    API_TITLE: str = "Cloud Raiders"
    JWT_ALGORITHM: str = "HS256"
    SECRET_KEY: str = "969281e9bb25af11c3f9c1d76575208d4a3753cad4ec6a207a29d5190cae495a"
    PASSWORD_SALT: str = "salt"
    DEFAULT_TOKEN_EXPIRY: int = 30


class AccessLevel(Enum, BaseModel):
    PLAYER: str = "player"
    ADMIN: str = "admin"


scope_descriptor = {AccessLevel.PLAYER: "Base Player permissions", AccessLevel.ADMIN: "API Administrator"}
access = AccessLevel()
settings = Settings()
