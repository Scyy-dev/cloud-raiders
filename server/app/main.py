
from fastapi import FastAPI

from config import settings

app = FastAPI(title=settings.API_TITLE)

@app.get("/api/test")
async def hello_world():
    return {"message": "Hello world!"}

