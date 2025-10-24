from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from pymongo import MongoClient
from bson import ObjectId
from dotenv import load_dotenv
import os

# ===================================================================
# --- SETUP ---
# ===================================================================
load_dotenv()

app = FastAPI(
    title="WAF Logs Service",
    description="Standalone service for WAF log management",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
        "http://localhost:8001",  # Main WAF service
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===================================================================
# --- MONGODB CONNECTION ---
# ===================================================================
analysis_collection = None

try:
    mongo_uri = os.getenv("MONGO_URI")
    if not mongo_uri:
        raise ValueError("MONGO_URI environment variable not set!")
    
    mongo_client = MongoClient(mongo_uri)
    db = mongo_client.get_database("waf_db")
    analysis_collection = db.get_collection("analysis_logs")
    mongo_client.admin.command('ping')
    print(f"[{datetime.now()}] [SUCCESS] ✅ Connected to MongoDB")
except Exception as e:
    print(f"[{datetime.now()}] [ERROR] ❌ MongoDB connection failed: {e}")
    analysis_collection = None


# ===================================================================
# --- HEALTH CHECK ---
# ===================================================================
@app.get("/")
async def root():
    return {
        "service": "WAF Logs Service",
        "status": "running",
        "mongodb_connected": analysis_collection is not None
    }


@app.get("/health")
async def health_check():
    return {
        "status": "healthy" if analysis_collection is not None else "degraded",
        "mongodb_connected": analysis_collection is not None
    }


# ===================================================================
# --- LOGS ENDPOINTS ---
# ===================================================================
@app.get("/logs")
async def get_logs(limit: int = 50, skip: int = 0):
    """
    Get analysis logs from MongoDB with pagination.
    
    Parameters:
    - limit: Maximum number of logs to return (default: 50, max: 1000)
    - skip: Number of logs to skip for pagination (default: 0)
    """
    if analysis_collection is None:
        raise HTTPException(status_code=503, detail="MongoDB service unavailable")
    
    # Enforce reasonable limits
    limit = min(limit, 1000)
    limit = max(limit, 1)
    skip = max(skip, 0)
    
    try:
        # Fetch logs sorted by timestamp (newest first)
        logs = list(analysis_collection.find()
                   .sort("timestamp", -1)
                   .skip(skip)
                   .limit(limit))
        
        # Get total count
        total_count = analysis_collection.count_documents({})
        
        # Convert ObjectId to string and timestamp to ISO format
        for log in logs:
            log["_id"] = str(log["_id"])
            if "timestamp" in log:
                log["timestamp"] = log["timestamp"].isoformat()
        
        print(f"[{datetime.now()}] [INFO] 📚 Fetched {len(logs)} logs (skip: {skip}, limit: {limit})")
        
        return {
            "logs": logs,
            "count": len(logs),
            "total": total_count,
            "skip": skip,
            "limit": limit,
            "has_more": (skip + len(logs)) < total_count
        }
        
    except Exception as e:
        print(f"[{datetime.now()}] [ERROR] ❌ Error fetching logs: {e}")
        raise HTTPException(status_code=500, detail=f"Error fetching logs: {str(e)}")


@app.get("/logs/stats")
async def get_log_stats():
    """
    Get statistics about stored logs.
    """
    if analysis_collection is None:
        raise HTTPException(status_code=503, detail="MongoDB service unavailable")
    
    try:
        total_logs = analysis_collection.count_documents({})
        malicious_logs = analysis_collection.count_documents({"analysis.is_malicious": True})
        benign_logs = total_logs - malicious_logs
        
        # Get date range
        oldest = analysis_collection.find_one(sort=[("timestamp", 1)])
        newest = analysis_collection.find_one(sort=[("timestamp", -1)])
        
        return {
            "total_logs": total_logs,
            "malicious_logs": malicious_logs,
            "benign_logs": benign_logs,
            "oldest_log": oldest["timestamp"].isoformat() if oldest else None,
            "newest_log": newest["timestamp"].isoformat() if newest else None,
            "detection_rate": round((malicious_logs / total_logs * 100), 2) if total_logs > 0 else 0
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching stats: {str(e)}")


@app.get("/logs/recent")
async def get_recent_logs(count: int = 20):
    """
    Get the most recent logs (shortcut endpoint).
    """
    if analysis_collection is None:
        raise HTTPException(status_code=503, detail="MongoDB service unavailable")
    
    count = min(count, 100)  # Max 100
    
    try:
        logs = list(analysis_collection.find()
                   .sort("timestamp", -1)
                   .limit(count))
        
        for log in logs:
            log["_id"] = str(log["_id"])
            if "timestamp" in log:
                log["timestamp"] = log["timestamp"].isoformat()
        
        return {"logs": logs, "count": len(logs)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching recent logs: {str(e)}")


@app.get("/logs/{log_id}")
async def get_log_by_id(log_id: str):
    """
    Get a specific log by MongoDB _id.
    """
    if analysis_collection is None:
        raise HTTPException(status_code=503, detail="MongoDB service unavailable")
    
    try:
        log = analysis_collection.find_one({"_id": ObjectId(log_id)})
        
        if not log:
            raise HTTPException(status_code=404, detail="Log not found")
        
        log["_id"] = str(log["_id"])
        if "timestamp" in log:
            log["timestamp"] = log["timestamp"].isoformat()
        
        return log
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching log: {str(e)}")


@app.delete("/logs")
async def clear_all_logs():
    """
    Clear all logs from MongoDB (use with caution!).
    """
    if analysis_collection is None:
        raise HTTPException(status_code=503, detail="MongoDB service unavailable")
    
    try:
        result = analysis_collection.delete_many({})
        print(f"[{datetime.now()}] [WARNING] 🗑️ Cleared {result.deleted_count} logs")
        
        return {
            "status": "success",
            "message": f"Deleted {result.deleted_count} logs",
            "deleted_count": result.deleted_count
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error clearing logs: {str(e)}")


@app.delete("/logs/{log_id}")
async def delete_log_by_id(log_id: str):
    """
    Delete a specific log by MongoDB _id.
    """
    if analysis_collection is None:
        raise HTTPException(status_code=503, detail="MongoDB service unavailable")
    
    try:
        result = analysis_collection.delete_one({"_id": ObjectId(log_id)})
        
        if result.deleted_count == 0:
            raise HTTPException(status_code=404, detail="Log not found")
        
        print(f"[{datetime.now()}] [INFO] 🗑️ Deleted log: {log_id}")
        
        return {
            "status": "success",
            "message": "Log deleted",
            "log_id": log_id
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting log: {str(e)}")


# ===================================================================
# --- RUN SERVER ---
# ===================================================================
if __name__ == "__main__":
    import uvicorn
    print("\n" + "="*60)
    print("🚀 WAF Logs Service Starting...")
    print("="*60)
    print(f"📊 Service URL: http://localhost:8002")
    print(f"📚 API Docs: http://localhost:8002/docs")
    print("="*60 + "\n")
    
    uvicorn.run(app, host="0.0.0.0", port=8002)
