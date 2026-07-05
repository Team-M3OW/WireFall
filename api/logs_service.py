import logging
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient, DESCENDING
from bson import ObjectId
from dotenv import load_dotenv
from pydantic import BaseModel

load_dotenv()

app = FastAPI(title="WireFall Logs Service", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mongo_client = None
collection = None


@app.on_event("startup")
async def startup():
    global mongo_client, collection
    import os

    mongo_uri = os.getenv("MONGO_URI", "")
    if mongo_uri:
        mongo_client = MongoClient(mongo_uri)
        db = mongo_client.get_database("waf_db")
        collection = db.get_collection("analysis_logs")
        logging.info("Logs service connected to MongoDB.")


@app.on_event("shutdown")
async def shutdown():
    if mongo_client:
        mongo_client.close()


@app.get("/")
@app.get("/health")
async def health():
    return {"status": "healthy" if collection is not None else "degraded"}


@app.get("/logs")
async def get_logs(limit: int = 50, skip: int = 0):
    if collection is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    total = collection.count_documents({})
    cursor = collection.find().sort("timestamp", DESCENDING).skip(skip).limit(limit)
    logs = []
    for log in cursor:
        log["_id"] = str(log["_id"])
        if "timestamp" in log:
            log["timestamp"] = log["timestamp"].isoformat()
        logs.append(log)
    return {"logs": logs, "total": total, "limit": limit, "skip": skip, "has_more": (skip + limit < total)}


@app.get("/logs/stats")
async def get_logs_stats():
    if collection is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    total = collection.count_documents({})
    malicious = collection.count_documents({"analysis.is_malicious": True})
    benign = collection.count_documents({"analysis.is_malicious": False})
    return {
        "total": total,
        "malicious": malicious,
        "benign": benign,
        "detection_rate": (malicious / total * 100) if total > 0 else 0,
    }


@app.get("/logs/recent")
async def get_recent_logs(limit: int = 10):
    if collection is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    cursor = collection.find().sort("timestamp", DESCENDING).limit(limit)
    logs = []
    for log in cursor:
        log["_id"] = str(log["_id"])
        if "timestamp" in log:
            log["timestamp"] = log["timestamp"].isoformat()
        logs.append(log)
    return {"logs": logs}


@app.get("/logs/{log_id}")
async def get_log(log_id: str):
    if collection is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    try:
        log = collection.find_one({"_id": ObjectId(log_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid log ID format")
    if not log:
        raise HTTPException(status_code=404, detail="Log not found")
    log["_id"] = str(log["_id"])
    if "timestamp" in log:
        log["timestamp"] = log["timestamp"].isoformat()
    return log


@app.delete("/logs")
async def clear_logs():
    if collection is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    result = collection.delete_many({})
    return {"status": "success", "deleted_count": result.deleted_count}


@app.delete("/logs/{log_id}")
async def delete_log(log_id: str):
    if collection is None:
        raise HTTPException(status_code=503, detail="MongoDB unavailable")
    try:
        result = collection.delete_one({"_id": ObjectId(log_id)})
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid log ID format")
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Log not found")
    return {"status": "success", "deleted": True}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.logs_service:app", host="0.0.0.0", port=8002, reload=True)
