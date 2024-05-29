from sqlmodel import Field
from app.base import BaseDB


class Player(BaseDB):
    id: int | None = Field(description="Player ID", primary_key=True, nullable=False)
    username: str = Field(description="Unique player name", nullable=False)
