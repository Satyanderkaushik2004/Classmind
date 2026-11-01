import os
import logging
from pymongo import MongoClient

log = logging.getLogger("vyom.db_connection")

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "vyom_db")

_client = None
_db = None
_is_mock = False

def get_db():
    global _client, _db, _is_mock
    if _db is None:
        try:
            # Short timeout to fail fast if MongoDB is not running locally
            _client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=2000)
            _db = _client[DB_NAME]
            # Verify connection
            _client.server_info()
            log.info("Successfully connected to MongoDB at %s", MONGO_URI)
            _is_mock = False
        except Exception as e:
            log.warning("Failed to connect to MongoDB at %s. Falling back to in-memory mongomock database. Error: %s", MONGO_URI, e)
            try:
                import mongomock
                # Create a single shared in-memory MongoClient
                _client = mongomock.MongoClient()
                _db = _client[DB_NAME]
                _is_mock = True
                log.info("Successfully initialized in-memory mongomock database.")
            except Exception as mock_e:
                log.error("Failed to fall back to mongomock: %s", mock_e)
                raise e
    return _db
