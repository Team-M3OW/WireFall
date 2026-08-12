from fastapi import APIRouter

import api.services.database as db_service
from api.services.redis_client import get_redis
from inference.model import model_instance

router = APIRouter()


@router.get("/health")
async def health_check():
    is_mongo = db_service.get_mongo() is not None
    is_redis = get_redis() is not None
    is_model = model_instance.loaded
    return {
        "status": "healthy" if (is_redis and is_model and is_mongo) else "degraded",
        "redis_connected": is_redis,
        "mongodb_connected": is_mongo,
        "anomaly_model_loaded": is_model,
    }
