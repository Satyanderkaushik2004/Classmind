import os
import time
import logging
from typing import Optional, Dict
from pymongo import MongoClient

log = logging.getLogger("vyom.auth_db")

# Read MongoDB URI and DB name from environment
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
DB_NAME = os.getenv("MONGO_DB_NAME", "vyom_db")

client = None
db = None

def get_db():
    global client, db
    if db is None:
        try:
            client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
            db = client[DB_NAME]
            # Verify connection
            client.server_info()
            log.info("Successfully connected to MongoDB at %s", MONGO_URI)
        except Exception as e:
            log.error("Failed to connect to MongoDB: %s", e)
            raise e
    return db

def init_db():
    try:
        database = get_db()
        # Create unique index on users.email
        database.users.create_index("email", unique=True)
        log.info("MongoDB authentication database initialized and indexes created.")
    except Exception as e:
        log.error("Failed to initialize MongoDB database: %s", e)

def create_user(
    user_id: str,
    full_name: str,
    email: str,
    password_hash: str,
    role: str,
    profile_photo: Optional[str] = None,
    email_verified: bool = False
) -> Dict:
    database = get_db()
    now_ms = int(time.time() * 1000)
    
    user_doc = {
        "_id": user_id,
        "full_name": full_name,
        "email": email.strip().lower(),
        "password_hash": password_hash,
        "role": role,
        "profile_photo": profile_photo,
        "email_verified": email_verified,
        "created_at": now_ms,
        "updated_at": now_ms
    }
    
    database.users.insert_one(user_doc)
    return user_doc

def create_student_profile(user_id: str):
    database = get_db()
    now_ms = int(time.time() * 1000)
    profile_doc = {
        "_id": user_id,
        "created_at": now_ms
    }
    database.student_profiles.insert_one(profile_doc)

def create_teacher_profile(
    user_id: str,
    organization: str,
    designation: str,
    department: str,
    phone: Optional[str] = None,
    bio: Optional[str] = None,
    is_verified_teacher: bool = False
):
    database = get_db()
    now_ms = int(time.time() * 1000)
    profile_doc = {
        "_id": user_id,
        "organization": organization,
        "designation": designation,
        "department": department,
        "phone": phone,
        "bio": bio,
        "is_verified_teacher": is_verified_teacher,
        "created_at": now_ms
    }
    database.teacher_profiles.insert_one(profile_doc)

def get_user_by_email(email: str) -> Optional[Dict]:
    database = get_db()
    user = database.users.find_one({"email": email.strip().lower()})
    return user

def get_teacher_profile(user_id: str) -> Optional[Dict]:
    database = get_db()
    profile = database.teacher_profiles.find_one({"_id": user_id})
    return profile

def update_user_password(email: str, password_hash: str) -> bool:
    database = get_db()
    now_ms = int(time.time() * 1000)
    result = database.users.update_one(
        {"email": email.strip().lower()},
        {"$set": {"password_hash": password_hash, "updated_at": now_ms}}
    )
    return result.modified_count > 0

def update_user_photo(email: str, photo_url: str) -> bool:
    database = get_db()
    now_ms = int(time.time() * 1000)
    result = database.users.update_one(
        {"email": email.strip().lower()},
        {"$set": {"profile_photo": photo_url, "updated_at": now_ms}}
    )
    return result.modified_count > 0
