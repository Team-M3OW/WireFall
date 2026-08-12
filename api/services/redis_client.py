import redis as redis_lib

from api.config import settings

redis_client: redis_lib.Redis | None = None


def connect_redis():
    global redis_client
    import os
    try:
        redis_url = os.getenv("REDIS_URL") or settings.redis_url
        client = redis_lib.from_url(redis_url, decode_responses=True)
        client.ping()
        redis_client = client
        return redis_client
    except Exception:
        redis_client = None
        return None


def get_redis():
    return redis_client


def close_redis():
    global redis_client
    if redis_client:
        redis_client.close()
        redis_client = None
