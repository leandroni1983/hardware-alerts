import logging
from fastapi import FastAPI
from api.routes import scrape

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Hardware Alerts API")

app.include_router(scrape.router)
