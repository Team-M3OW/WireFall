import asyncio
import json
import logging
from datetime import datetime

from api.services.database import get_collection
from api.services.redis_client import get_redis
from api.services.ws_manager import manager
from inference.ensemble import predict_anomaly
from inference.features import build_sequence, extract_features
from inference.rule_generator import generate_rule_from_payload

logging.basicConfig(level=logging.INFO, format="[%(asctime)s] [QUEUE-WORKER] %(message)s")

STREAM_KEY = "waf:async:analysis_queue"
GROUP_NAME = "waf_workers"
CONSUMER_NAME = "worker_node_1"


async def init_redis_stream(r):
    try:
        r.xgroup_create(STREAM_KEY, GROUP_NAME, id="0", mkstream=True)
        logging.info(f"Redis stream consumer group '{GROUP_NAME}' initialized.")
    except Exception:
        # Group already exists
        pass


async def process_event(event_data: dict):
    request_data = json.loads(event_data.get("request", "{}"))
    tenant_id = event_data.get("tenant_id", "default_tenant")

    formatted_log = build_sequence(request_data)
    rec_error, cls_emb, perplexity = extract_features(formatted_log)
    category, details = predict_anomaly(rec_error, cls_emb, perplexity)
    is_malicious = bool(category)

    new_rule = None
    if is_malicious:
        payload = request_data.get("request_body") or request_data.get("path") or ""
        new_rule = generate_rule_from_payload(payload)
        r = get_redis()
        if new_rule and r:
            # Add rule to tenant-isolated Redis fast-path rule set
            r.sadd(f"tenant:{tenant_id}:rules", new_rule)
            r.sadd("waf:rules:regex", new_rule)

    collection = get_collection()
    if collection is not None:
        timestamp = datetime.utcnow()
        doc = {
            "tenant_id": tenant_id,
            "timestamp": timestamp,
            "request": request_data,
            "analysis": {
                "is_malicious": is_malicious,
                "reconstruction_loss": float(rec_error),
                "perplexity": float(perplexity),
                "details": details,
            },
            "action_taken": "BLOCK" if is_malicious else "ALLOW",
            "auto_learned_rule": new_rule,
        }
        result = collection.insert_one(doc)
        doc["_id"] = str(result.inserted_id)

        # Broadcast via WebSocket gateway
        await manager.broadcast({
            "_id": doc["_id"],
            "tenant_id": tenant_id,
            "timestamp": timestamp.isoformat(),
            "method": request_data.get("method"),
            "path": request_data.get("path"),
            "request_body": request_data.get("request_body"),
            "action_taken": doc["action_taken"],
            "is_malicious": is_malicious,
            "reconstruction_loss": float(rec_error),
            "perplexity": float(perplexity),
            "auto_learned_rule": new_rule,
        })
        logging.info(f"Processed request for tenant={tenant_id} | action={doc['action_taken']}")


async def run_worker():
    logging.info("Starting WireFall Asynchronous Queue Worker...")
    while True:
        r = get_redis()
        if not r:
            await asyncio.sleep(2)
            continue

        await init_redis_stream(r)
        try:
            entries = r.xreadgroup(GROUP_NAME, CONSUMER_NAME, {STREAM_KEY: ">"}, count=10, block=1000)
            if entries:
                for stream_name, messages in entries:
                    for msg_id, message_data in messages:
                        await process_event(message_data)
                        r.xack(STREAM_KEY, GROUP_NAME, msg_id)
        except Exception as e:
            logging.error(f"Error in queue worker: {e}")
            await asyncio.sleep(1)


if __name__ == "__main__":
    from api.services.database import connect_mongo
    from api.services.redis_client import connect_redis
    from inference.model import model_instance

    connect_redis()
    connect_mongo()
    model_instance.load()
    asyncio.run(run_worker())
