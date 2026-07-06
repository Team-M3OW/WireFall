from datetime import datetime

from fastapi import APIRouter, HTTPException

from api.models.schemas import RequestData
from api.services.database import get_collection
from api.services.redis_client import get_redis
from api.services.ws_manager import manager
from inference.ensemble import predict_anomaly
from inference.features import build_sequence, extract_features
from inference.model import model_instance
from inference.rule_generator import generate_rule_from_payload

router = APIRouter()


@router.post("/analyze")
async def analyze(request_data: RequestData):
    if not model_instance.loaded:
        raise HTTPException(status_code=503, detail="Anomaly detection service unavailable")

    try:
        formatted_log = build_sequence(request_data.model_dump())
        rec_error, cls_emb, perplexity = extract_features(formatted_log)
        category, details = predict_anomaly(rec_error, cls_emb, perplexity)
        is_malicious = bool(category)

        response, new_rule = None, None
        if is_malicious:
            payload = request_data.request_body or request_data.path
            new_rule = generate_rule_from_payload(payload)
            r = get_redis()
            if new_rule and r:
                r.sadd("waf:rules:regex", new_rule)
            response = {
                "allow": False,
                "reason": f"Blocked by transformer model (loss: {rec_error:.4f})",
                "auto_learned_rule": new_rule,
            }
        else:
            response = {"allow": True, "reason": "Passed transformer model analysis."}

        collection = get_collection()
        if collection is not None:
            doc = {
                "timestamp": datetime.utcnow(),
                "request": request_data.model_dump(),
                "analysis": {
                    "is_malicious": is_malicious,
                    "reconstruction_loss": rec_error,
                    "perplexity": perplexity,
                    "details": details,
                },
                "action_taken": "BLOCK" if is_malicious else "ALLOW",
                "auto_learned_rule": new_rule,
            }
            result = collection.insert_one(doc)
            doc["_id"] = str(result.inserted_id)
            await manager.broadcast(
                {
                    "_id": doc["_id"],
                    "timestamp": doc["timestamp"].isoformat(),
                    "method": request_data.method,
                    "path": request_data.path,
                    "request_body": request_data.request_body,
                    "action_taken": doc["action_taken"],
                    "is_malicious": is_malicious,
                    "reconstruction_loss": rec_error,
                    "perplexity": perplexity,
                    "auto_learned_rule": new_rule,
                }
            )

        return response

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")
