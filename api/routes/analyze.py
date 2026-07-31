import hashlib
import asyncio
import logging
from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, BackgroundTasks

from api.models.schemas import RequestData
from api.services.database import get_collection
from api.services.redis_client import get_redis
from api.services.mq import publish_rule_generation_task
from api.services.rate_limiter import SlidingWindowRateLimiter
from inference.ensemble import predict_anomaly
from inference.features import build_sequence, extract_features

# LLD Fundamental: The Singleton Pattern
# We import 'model_instance' which was instantiated exactly once globally.
from inference.model import model_instance

router = APIRouter()

MAX_CONCURRENT_INFERENCES = 50
inference_semaphore = asyncio.Semaphore(MAX_CONCURRENT_INFERENCES)

rate_limiter = SlidingWindowRateLimiter(limit=1000, window_in_seconds=60)

# OS Fundamental: Thread Pools for I/O Bound Tasks
def async_db_log(doc: dict):
    """ Runs in a background thread pool to avoid blocking the API response """
    try:
        collection = get_collection()
        if collection is not None:
            collection.insert_one(doc)
    except Exception as e:
        logging.warning(f"Background DB logging failed: {e}")

@router.post("/analyze")
async def analyze(request_data: RequestData, request: Request, background_tasks: BackgroundTasks):
    tenant_id = request_data.tenant_id
    rate_limiter.check_limit(tenant_id=tenant_id, identifier=request.client.host)

    r = get_redis()
    
    req_str = f"{request_data.method}{request_data.path}{request_data.request_body}"
    req_hash = hashlib.sha256(req_str.encode()).hexdigest()
    cache_key = f"waf:{tenant_id}:cache:{req_hash}"
    
    if r and r.get(cache_key):
        return {"allow": True, "reason": "Passed transformer model analysis (cached)."}

    # Ensure the Singleton is loaded before proceeding
    if not model_instance.loaded:
        raise HTTPException(status_code=503, detail="ML Model not loaded yet")

    async with inference_semaphore:
        try:
            formatted_log = build_sequence(request_data.model_dump())
            rec_error, cls_emb, perplexity = extract_features(formatted_log)
            category, details = predict_anomaly(rec_error, cls_emb, perplexity)
        except Exception as e:
            logging.error(f"ML Inference Failed: {str(e)}")
            return {"allow": True, "reason": "WAF Inference Error: Passed by default fallback."}

    is_malicious = bool(category)
    response = None
    
    if is_malicious:
        payload = request_data.request_body or request_data.path
        publish_rule_generation_task(payload, tenant_id)
        
        response = {
            "allow": False,
            "reason": f"Blocked by transformer model (loss: {rec_error:.4f})",
            "auto_learned_rule": "Pending background generation",
        }
    else:
        if r:
            r.setex(cache_key, 300, "1")
        response = {"allow": True, "reason": "Passed transformer model analysis."}

    # Offload MongoDB network I/O to a background thread
    doc = {
        "tenant_id": tenant_id,
        "timestamp": datetime.utcnow(),
        "request": request_data.model_dump(),
        "analysis": {
            "is_malicious": is_malicious,
            "reconstruction_loss": float(rec_error),
            "perplexity": float(perplexity),
            "details": details,
        },
        "action_taken": "BLOCK" if is_malicious else "ALLOW",
        "auto_learned_rule": "Pending" if is_malicious else None,
    }
    background_tasks.add_task(async_db_log, doc)

    return response
