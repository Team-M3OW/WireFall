from fastapi import APIRouter, HTTPException
from bson import ObjectId
from api.models.schemas import PassRequestBody
from api.services.database import get_collection
from api.services.redis_client import get_redis

router = APIRouter()


@router.post("/pass-request")
async def pass_request(body: PassRequestBody):
    r = get_redis()
    if not r:
        raise HTTPException(status_code=503, detail="Redis service unavailable")
    collection = get_collection()
    if collection is None:
        raise HTTPException(status_code=503, detail="MongoDB service unavailable")

    try:
        document = collection.find_one({"_id": ObjectId(body.mongo_id)})
        if not document:
            raise HTTPException(status_code=404, detail="Request not found in database")

        request_body = document.get("request", {}).get("request_body", "")
        if not request_body:
            raise HTTPException(status_code=400, detail="Request body is empty, cannot whitelist")

        r.sadd("waf:whitelist", request_body)
        return {
            "status": "success",
            "message": "Request added to whitelist",
            "mongo_id": body.mongo_id,
            "whitelisted_data": request_body[:100],
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error whitelisting request: {str(e)}")
