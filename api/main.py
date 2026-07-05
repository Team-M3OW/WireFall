import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from api.config import settings
from api.services.database import connect_mongo, close_mongo
from api.services.redis_client import connect_redis, close_redis
from inference.model import model_instance
from api.routes import analyze, health, logs, rules, modes, pass_request, ws

load_dotenv()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="[%(asctime)s] [%(levelname)s] %(message)s",
)

app = FastAPI(title="WireFall WAF", version="2.0.0", docs_url="/docs")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    logging.info("Starting WireFall WAF services...")
    connect_redis()
    connect_mongo()
    model_instance.load()
    logging.info("All services initialized.")


@app.on_event("shutdown")
async def shutdown():
    close_redis()
    close_mongo()
    logging.info("WireFall services shut down.")


app.include_router(analyze.router)
app.include_router(health.router)
app.include_router(logs.router)
app.include_router(rules.router)
app.include_router(modes.router)
app.include_router(pass_request.router)
app.include_router(ws.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host=settings.host, port=settings.port, reload=True)
