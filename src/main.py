from fastapi import FastAPI

from src.urls.v1 import default_route

app = FastAPI()
app.include_router(default_route.router, tags = ['API'])
