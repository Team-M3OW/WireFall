import redis as redis_lib

from api.config import settings

redis_client: redis_lib.Redis | None = None


def connect_redis():
    global redis_client
    try:
        redis_client = redis_lib.from_url(settings.redis_url, decode_responses=True)
        redis_client.ping()
        return redis_client
    except Exception:
        return None


def get_redis():
    return redis_client


def close_redis():
    global redis_client
    if redis_client:
        redis_client.close()
        redis_client = None
