import time
from fastapi import HTTPException
from api.services.redis_client import get_redis

class SlidingWindowRateLimiter:
    """
    Implements a Sliding Window Log rate limiting algorithm using Redis Sorted Sets.
    Unlike a Fixed Window (which suffers from burst issues at the edges of windows),
    the Sliding Window perfectly tracks requests down to the millisecond.
    """
    def __init__(self, limit: int, window_in_seconds: int):
        self.limit = limit
        self.window = window_in_seconds

    def check_limit(self, tenant_id: str, identifier: str):
        r = get_redis()
        if not r:
            # Fallback/Graceful Degradation: If Redis is completely down, fail-open 
            # to keep the WAF routing traffic rather than taking down the customer's site.
            return True
            
        key = f"waf:ratelimit:{tenant_id}:{identifier}"
        now = time.time()
        
        # Use a Redis transaction (pipeline) to ensure atomicity and reduce network RTT
        pipeline = r.pipeline()
        
        # 1. Remove all timestamps strictly older than the current window
        pipeline.zremrangebyscore(key, 0, now - self.window)
        # 2. Add the current timestamp
        pipeline.zadd(key, {str(now): now})
        # 3. Count elements remaining in the sorted set
        pipeline.zcard(key)
        # 4. Set TTL to avoid memory leaks for inactive identifiers
        pipeline.expire(key, self.window)
        
        results = pipeline.execute()
        request_count = results[2]
        
        if request_count > self.limit:
            raise HTTPException(status_code=429, detail="Rate limit exceeded. Too many requests.")
        
        return True
