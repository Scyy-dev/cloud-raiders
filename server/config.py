from pydantic import BaseSettings


class Settings(BaseSettings):
    API_TITLE="Cloud Raiders"

settings = Settings()
