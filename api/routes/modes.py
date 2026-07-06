from fastapi import APIRouter, HTTPException

from api.services.redis_client import get_redis

router = APIRouter()
VALID_MODES = ["off", "fast", "full"]


@router.post("/set-mode/{mode_name}")
async def set_waf_mode(mode_name: str):
    if mode_name not in VALID_MODES:
        raise HTTPException(status_code=400, detail=f"Invalid mode. Must be one of: {VALID_MODES}")
    r = get_redis()
    if not r:
        raise HTTPException(status_code=503, detail="Redis service unavailable")
    try:
        r.set("waf:mode", mode_name)
        return {"status": "success", "mode": mode_name, "message": f"WAF mode set to {mode_name}"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error setting WAF mode: {str(e)}")
