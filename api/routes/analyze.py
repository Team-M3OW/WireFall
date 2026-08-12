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


@router.get("/analyze")
async def analyze_info():
    return {
        "endpoint": "/analyze",
        "method": "POST",
        "status": "active" if model_instance.loaded else "unavailable",
        "usage": "Send POST request with JSON payload containing method, path, protocol, request_body.",
    }


@router.post("/analyze")
async def analyze(request_data: RequestData):
    if not model_instance.loaded:
        raise HTTPException(status_code=503, detail="Anomaly detection service unavailable")

    r = get_redis()
    if r is None:
        from api.services.redis_client import connect_redis
        r = connect_redis()
    payload = request_data.request_body or request_data.path

    matched_existing_rule = None
    if r:
        try:
            existing_rules = r.smembers("waf:rules:regex")
        except Exception:
            existing_rules = []
        if existing_rules:
            import re
            for rule in existing_rules:
                rule_str = rule.decode("utf-8") if isinstance(rule, bytes) else rule
                rule_clean = rule_str.replace("(?i)", "").replace("\\", "")
                if rule_clean and (payload.lower() in rule_clean.lower() or rule_clean.lower() in payload.lower()):
                    matched_existing_rule = rule_str
                    break
                clean_p = re.sub(r'[\`\(\)\?\:\-\\\|\^\$\.\*]+', ' ', rule_str.replace("(?i)", "")).strip()
                tokens = [t.lower() for t in clean_p.split() if len(t) >= 4 and t.lower() not in ["http", "query"]]
                if tokens and any(t in payload.lower() for t in tokens):
                    matched_existing_rule = rule_str
                    break

    if matched_existing_rule:
        response = {
            "allow": False,
            "stage1_fast_path": True,
            "reason": f"Blocked instantly by Stage 1 Static WAF Rule ({matched_existing_rule})",
            "auto_learned_rule": matched_existing_rule,
        }
        is_malicious = True
        rec_error, perplexity = 0.0, 0.0
        new_rule = matched_existing_rule
    else:
        formatted_log = build_sequence(request_data.model_dump())
        rec_error, cls_emb, perplexity = extract_features(formatted_log)
        category, details = predict_anomaly(rec_error, cls_emb, perplexity)
        is_malicious = bool(category)

        response, new_rule = None, None
        if is_malicious:
            new_rule = generate_rule_from_payload(payload)
            if new_rule and r:
                r.sadd("waf:rules:regex", new_rule)
            response = {
                "allow": False,
                "stage1_fast_path": False,
                "reason": f"Blocked by transformer model (loss: {rec_error:.4f})",
                "auto_learned_rule": new_rule,
            }
        else:
            response = {"allow": True, "stage1_fast_path": False, "reason": "Passed transformer model analysis."}

        collection = get_collection()
        if collection is not None:
            timestamp = datetime.utcnow()
            doc = {
                "timestamp": timestamp,
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
                    "timestamp": timestamp.isoformat(),
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
