import re
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
    import logging
    logging.info(f"ANALYZE PAYLOAD: '{payload}' (Redis client: {r})")
    matched_existing_rule = None

    if r and payload:
        try:
            is_exact = r.sismember("waf:rules:exact_payloads", payload)
            if is_exact:
                matched_existing_rule = "Exact Stage 1 Redis Fast-Path Rule"
        except Exception as e:
            import logging
            logging.error(f"Redis sismember error: {e}")

        if not matched_existing_rule:
            try:
                existing_rules = r.smembers("waf:rules:regex")
            except Exception:
                existing_rules = []

            if existing_rules:
                for rule in existing_rules:
                    rule_str = rule.decode("utf-8") if isinstance(rule, bytes) else rule
                    try:
                        pattern = rule_str
                        if pattern.startswith("(?i)"):
                            pattern = "(?i)" + pattern[4:]
                        else:
                            pattern = "(?i)" + pattern
                        if re.search(pattern, payload):
                            matched_existing_rule = rule_str
                            break
                    except Exception:
                        pass

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
        category, details = predict_anomaly(rec_error, cls_emb, perplexity, payload=payload)
        is_malicious = bool(category)

        response, new_rule = None, None
        if is_malicious:
            if r:
                try:
                    r.sadd("waf:rules:exact_payloads", payload)
                except Exception:
                    pass
            new_rule = generate_rule_from_payload(payload)
            if new_rule and r:
                try:
                    r.sadd("waf:rules:regex", new_rule)
                except Exception:
                    pass
            response = {
                "allow": False,
                "stage1_fast_path": False,
                "reason": f"Blocked by transformer model (loss: {rec_error:.4f})",
                "auto_learned_rule": new_rule,
            }
        else:
            response = {"allow": True, "stage1_fast_path": False, "reason": "Passed transformer model analysis."}

    action_taken = "BLOCK" if is_malicious else "ALLOW"
    timestamp = datetime.utcnow()
    doc_id = f"log_{int(timestamp.timestamp() * 1000)}"

    collection = get_collection()
    if collection is not None:
        doc = {
            "timestamp": timestamp,
            "request": request_data.model_dump(),
            "analysis": {
                "is_malicious": is_malicious,
                "reconstruction_loss": rec_error,
                "perplexity": perplexity if 'perplexity' in locals() else 0.0,
            },
            "action_taken": action_taken,
            "auto_learned_rule": new_rule,
        }
        result = collection.insert_one(doc)
        doc_id = str(result.inserted_id)

    await manager.broadcast(
        {
            "_id": doc_id,
            "timestamp": timestamp.isoformat(),
            "method": request_data.method,
            "path": request_data.path,
            "request_body": request_data.request_body,
            "action_taken": action_taken,
            "is_malicious": is_malicious,
            "reconstruction_loss": rec_error,
            "auto_learned_rule": new_rule,
        }
    )

    return response


@router.post("/set-ratelimit/{max_reqs}")
async def set_ratelimit(max_reqs: int):
    r = get_redis()
    if r:
        r.set("waf:config:ratelimit_max", str(max_reqs))
        return {"status": "success", "ratelimit_max": max_reqs}
    return {"status": "error", "message": "Redis unavailable"}

