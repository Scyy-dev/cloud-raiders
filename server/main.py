import importlib

from fastapi import FastAPI

from config import settings

game = FastAPI(title=settings.API_TITLE)

@game.get("/api/test")
async def hello_world():
    return {
        "message": "Hello world!"
    }

