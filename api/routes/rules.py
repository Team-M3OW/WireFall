import re

from fastapi import APIRouter, HTTPException

from api.models.schemas import RuleBody
from api.services.redis_client import get_redis

router = APIRouter()


@router.get("/rules")
async def get_rules():
    r = get_redis()
    if not r:
        raise HTTPException(status_code=503, detail="Redis service unavailable")
    try:
        rules = list(r.smembers("waf:rules:regex"))
        return {"rules": rules, "count": len(rules)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching rules: {str(e)}")


@router.post("/rules")
async def add_rule(body: RuleBody):
    r = get_redis()
    if not r:
        raise HTTPException(status_code=503, detail="Redis service unavailable")
    try:
        re.compile(body.rule)
        r.sadd("waf:rules:regex", body.rule)
        return {"status": "success", "message": "Rule added", "rule": body.rule}
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error adding rule: {str(e)}")


@router.delete("/rules")
async def delete_rule(body: RuleBody):
    r = get_redis()
    if not r:
        raise HTTPException(status_code=503, detail="Redis service unavailable")
    try:
        removed = r.srem("waf:rules:regex", body.rule)
        if removed:
            return {"status": "success", "message": "Rule deleted", "rule": body.rule}
        raise HTTPException(status_code=404, detail="Rule not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error deleting rule: {str(e)}")
