import sys
sys.path.insert(0, ".")
from db_connection import get_db
import time

db = get_db()
result = db.users.update_one(
    {"email": "robinsgupta09@gmail.com"},
    {"$set": {"role": "teacher"}}
)
print(f"Role updated: {result.modified_count} doc")

user = db.users.find_one({"email": "robinsgupta09@gmail.com"})
print(f"Name: {user['full_name']}, Role: {user['role']}")

existing = db.teacher_profiles.find_one({"_id": user["_id"]})
if not existing:
    db.teacher_profiles.insert_one({
        "_id": user["_id"],
        "organization": "VYOM School",
        "designation": "Teacher",
        "department": "General",
        "created_at": int(time.time() * 1000)
    })
    print("Teacher profile created!")
else:
    print("Teacher profile already exists.")
