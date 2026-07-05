from fastapi import APIRouter, HTTPException
from api.services.database import get_collection

router = APIRouter()


@router.get("/logs")
async def get_logs(limit: int = 20):
    collection = get_collection()
    if collection is None:
        raise HTTPException(status_code=503, detail="MongoDB service unavailable")

    try:
        logs_cursor = collection.find().sort("timestamp", -1).limit(limit)
        logs = []
        for log in logs_cursor:
            log["_id"] = str(log["_id"])
            if "timestamp" in log:
                log["timestamp"] = log["timestamp"].isoformat()
            logs.append(log)
        return {"logs": logs, "count": len(logs)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching logs: {str(e)}")
