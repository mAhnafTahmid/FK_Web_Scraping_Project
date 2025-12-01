# crawler/db.py
from datetime import datetime, timezone
import os
from motor.motor_asyncio import AsyncIOMotorClient
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

MONGO_URI = os.getenv("MONGO_URI")
MONGO_DB = os.getenv("MONGO_DB")

_client = None
_db = None


def get_client():
    """Initialize and return the MongoDB AsyncIOMotorClient singleton."""
    global _client, _db
    if _client is None:
        _client = AsyncIOMotorClient(MONGO_URI)
        _db = _client[MONGO_DB]
    return _client


def get_db():
    """Return the MongoDB database instance, initializing if needed."""
    global _db
    if _db is None:
        get_client()
    return _db


async def upsert_book(book_dict):
    """Insert or update a book document in the books collection."""
    db = get_db()
    await db.books.update_one(
        {"_id": book_dict["_id"]}, {"$set": book_dict}, upsert=True
    )


async def insert_snapshot(snapshot):
    """Insert a snapshot into book_snapshots and return its string ID."""
    db = get_db()
    res = await db.book_snapshots.insert_one(snapshot)
    return str(res.inserted_id)


async def log_change(change_doc):
    """Insert a change record into the change_log collection."""
    db = get_db()
    await db.change_log.insert_one(change_doc)


async def mark_all_changes_as_old():
    """
    Set recent='old' for all change_log entries.
    """
    db = get_db()
    await db.change_log.update_many({}, {"$set": {"recent": "old"}})


async def log_change_entry(book_id, change_type):
    """
    Insert a new change_log entry with recent='new'.
    change_type is either 'new' or 'updated'.
    """
    db = get_db()
    doc = {
        "book_id": book_id,
        "change_type": change_type,  # new or updated
        "recent": "new",
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
    }
    await db.change_log.insert_one(doc)
    return doc
