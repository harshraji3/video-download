import os
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


def close():
    global _client
    if _client:
        _client.close()
        _client = None
