from fastapi import FastAPI
from .routes import config, index, insights, metrics, plan, runs, suites, tests

app = FastAPI(title="Kaizen Portal API")
app.include_router(tests.router)
app.include_router(runs.router)
app.include_router(config.router)
app.include_router(plan.router)
app.include_router(suites.router)
app.include_router(metrics.router)
app.include_router(insights.router)
app.include_router(index.router)
