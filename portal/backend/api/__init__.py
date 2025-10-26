from fastapi import FastAPI
from .routes import tests, runs, config, index

app = FastAPI(title="Kaizen Portal API")
app.include_router(tests.router)
app.include_router(runs.router)
app.include_router(config.router)
app.include_router(index.router)
