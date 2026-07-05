from fastapi import APIRouter
from api.services.redis_client import get_redis
from api.services.database import mongo_client
from inference.model import model_instance

router = APIRouter()


@router.get("/health")
async def health_check():
    return {
        "status": "healthy" if get_redis() and model_instance.loaded and (mongo_client is not None) else "degraded",
        "redis_connected": bool(get_redis()),
        "mongodb_connected": (mongo_client is not None),
        "anomaly_model_loaded": model_instance.loaded,
    }
