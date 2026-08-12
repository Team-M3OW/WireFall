from pymongo import MongoClient

from api.config import settings

mongo_client: MongoClient | None = None


def connect_mongo():
    global mongo_client
    import os
    mongo_uri = os.getenv("MONGO_URI") or settings.mongo_uri
    if not mongo_uri:
        return None
    try:
        mongo_client = MongoClient(mongo_uri)
        mongo_client.admin.command("ping")
        return mongo_client
    except Exception:
        mongo_client = None
        return None


def get_db():
    if mongo_client is None:
        return None
    return mongo_client.get_database(settings.mongo_db)


def get_collection():
    db = get_db()
    if db is None:
        return None
    return db.get_collection(settings.mongo_collection)


def close_mongo():
    global mongo_client
    if mongo_client:
        mongo_client.close()
        mongo_client = None
