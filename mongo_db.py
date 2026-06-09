import os
from datetime import datetime, timezone
from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv()

_client: MongoClient | None = None


def get_db():
    global _client
    if _client is None:
        uri = os.environ["MONGO_URI"]
        _client = MongoClient(uri)
    return _client.get_database("video_search")


def get_conversations():
    db = get_db()
    col = db["conversations"]
    col.create_index("session_id")
    return col


def save_message(session_id: str, role: str, text: str, citations: list | None = None):
    col = get_conversations()
    col.insert_one({
        "session_id": session_id,
        "role": role,
        "text": text,
        "citations": citations or [],
        "created_at": datetime.now(timezone.utc),
    })


def get_history(session_id: str, limit: int = 50):
    col = get_conversations()
    cursor = col.find({"session_id": session_id}).sort("created_at", 1).limit(limit)
    return list(cursor)


def close():
    global _client
    if _client:
        _client.close()
        _client = None
