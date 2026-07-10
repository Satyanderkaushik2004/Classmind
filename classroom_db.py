import os
import time
import uuid
import logging
import hashlib
from typing import Optional, List, Dict
from pymongo import MongoClient

log = logging.getLogger("vyom.classroom_db")

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
            client.server_info()
            log.info("Classroom DB successfully connected to MongoDB")
        except Exception as e:
            log.error("Classroom DB failed to connect to MongoDB: %s", e)
            raise e
    return db

def hash_lecture_code(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode("utf-8")).hexdigest()

def init_db():
    try:
        database = get_db()
        # Create indexes for all 20 collections
        database.institutions.create_index("code", unique=True)
        database.departments.create_index("code", unique=True)
        database.courses.create_index("code", unique=True)
        database.subjects.create_index([("course_id", 1), ("code", 1)], unique=True)
        database.classrooms.create_index([("course_id", 1), ("semester", 1), ("section", 1), ("academic_year", 1)], unique=True)
        database.classroom_members.create_index([("classroom_id", 1), ("student_id", 1)], unique=True)
        database.classroom_teachers.create_index([("classroom_id", 1), ("teacher_id", 1), ("subject_id", 1)], unique=True)
        database.timetables.create_index([("classroom_id", 1), ("day_of_week", 1), ("start_time", 1), ("end_time", 1)], unique=True)
        
        database.lectures.create_index("lecture_code_hash")
        database.lectures.create_index("classroom_id")
        database.lectures.create_index("status")
        
        database.attendance.create_index([("lecture_id", 1), ("student_id", 1)], unique=True)
        database.attendance_logs.create_index([("lecture_id", 1), ("student_id", 1)])
        database.academic_calendar.create_index("date", unique=True)
        database.student_enrollment_history.create_index("student_id")
        
        database.student_profiles.create_index("roll_number", unique=True)
        database.student_profiles.create_index("registration_number", unique=True)
        
        database.announcements.create_index("classroom_id")
        database.assignments.create_index([("classroom_id", 1), ("subject_id", 1)])
        database.quizzes.create_index([("classroom_id", 1), ("subject_id", 1)])
        database.notifications.create_index("user_id")

        log.info("MongoDB classroom database initialized with all 20 collections and indexes.")
    except Exception as e:
        log.error("Failed to initialize classroom database: %s", e)

# ── CRUD Operations ──

def create_institution(name: str, code: str) -> Dict:
    database = get_db()
    inst_id = "inst_" + uuid.uuid4().hex[:12]
    doc = {
        "_id": inst_id,
        "name": name,
        "code": code.strip().upper(),
        "created_at": int(time.time() * 1000)
    }
    database.institutions.insert_one(doc)
    return doc

def create_department(institution_id: str, name: str, code: str) -> Dict:
    database = get_db()
    dept_id = "dept_" + uuid.uuid4().hex[:12]
    doc = {
        "_id": dept_id,
        "institution_id": institution_id,
        "name": name,
        "code": code.strip().upper(),
        "created_at": int(time.time() * 1000)
    }
    database.departments.insert_one(doc)
    return doc

def create_course(department_id: str, name: str, code: str, duration_years: int) -> Dict:
    database = get_db()
    course_id = "course_" + uuid.uuid4().hex[:12]
    doc = {
        "_id": course_id,
        "department_id": department_id,
        "name": name,
        "code": code.strip().upper(),
        "duration_years": duration_years,
        "created_at": int(time.time() * 1000)
    }
    database.courses.insert_one(doc)
    return doc

def create_subject(course_id: str, name: str, code: str, semester: int) -> Dict:
    database = get_db()
    subj_id = "subj_" + uuid.uuid4().hex[:12]
    doc = {
        "_id": subj_id,
        "course_id": course_id,
        "name": name,
        "code": code.strip().upper(),
        "semester": semester,
        "created_at": int(time.time() * 1000)
    }
    database.subjects.insert_one(doc)
    return doc

def create_classroom(course_id: str, semester: int, section: str, academic_year: str, teacher_id: Optional[str] = None) -> Dict:
    database = get_db()
    class_id = "class_" + uuid.uuid4().hex[:12]
    doc = {
        "_id": class_id,
        "course_id": course_id,
        "semester": semester,
        "section": section.strip().upper(),
        "academic_year": academic_year.strip(),
        "teacher_id": teacher_id,
        "is_archived": False,
        "created_at": int(time.time() * 1000)
    }
    database.classrooms.insert_one(doc)
    return doc

def create_classroom_member(classroom_id: str, student_id: str, enrollment_method: str = "admin_manual") -> Dict:
    database = get_db()
    doc = {
        "_id": "mem_" + uuid.uuid4().hex[:12],
        "classroom_id": classroom_id,
        "student_id": student_id,
        "enrolled_at": int(time.time() * 1000),
        "enrollment_method": enrollment_method
    }
    database.classroom_members.update_one(
        {"classroom_id": classroom_id, "student_id": student_id},
        {"$setOnInsert": doc},
        upsert=True
    )
    # Log to student enrollment history
    database.student_enrollment_history.insert_one({
        "_id": "eh_" + uuid.uuid4().hex[:12],
        "student_id": student_id,
        "classroom_id": classroom_id,
        "action": "enroll",
        "timestamp": int(time.time() * 1000)
    })
    return doc

def assign_classroom_teacher(classroom_id: str, teacher_id: str, subject_id: str) -> Dict:
    database = get_db()
    doc = {
        "_id": "tmap_" + uuid.uuid4().hex[:12],
        "classroom_id": classroom_id,
        "teacher_id": teacher_id,
        "subject_id": subject_id,
        "assigned_at": int(time.time() * 1000)
    }
    database.classroom_teachers.update_one(
        {"classroom_id": classroom_id, "teacher_id": teacher_id, "subject_id": subject_id},
        {"$setOnInsert": doc},
        upsert=True
    )
    return doc

def create_student_profile(
    student_id: str,
    roll_number: str,
    registration_number: str,
    course_id: str,
    department_id: str,
    semester: int,
    section: str,
    batch: str,
    academic_year: str,
    university_id: Optional[str] = None
) -> Dict:
    database = get_db()
    doc = {
        "_id": student_id,
        "roll_number": roll_number.strip().upper(),
        "registration_number": registration_number.strip().upper(),
        "university_id": university_id.strip().upper() if university_id else None,
        "course_id": course_id,
        "department_id": department_id,
        "semester": semester,
        "section": section.strip().upper(),
        "batch": batch.strip(),
        "academic_year": academic_year.strip(),
        "updated_at": int(time.time() * 1000)
    }
    database.student_profiles.update_one(
        {"_id": student_id},
        {"$set": doc},
        upsert=True
    )
    return doc

def create_timetable(classroom_id: str, day_of_week: int, start_time: str, end_time: str, subject_id: str, teacher_id: str) -> Dict:
    database = get_db()
    tt_id = "tt_" + uuid.uuid4().hex[:12]
    doc = {
        "_id": tt_id,
        "classroom_id": classroom_id,
        "day_of_week": day_of_week,
        "start_time": start_time.strip(),
        "end_time": end_time.strip(),
        "subject_id": subject_id,
        "teacher_id": teacher_id,
        "created_at": int(time.time() * 1000)
    }
    database.timetables.update_one(
        {"classroom_id": classroom_id, "day_of_week": day_of_week, "start_time": start_time.strip(), "end_time": end_time.strip()},
        {"$setOnInsert": doc},
        upsert=True
    )
    return doc

def create_academic_calendar(date_str: str, event_name: str, is_holiday: bool = False) -> Dict:
    database = get_db()
    doc = {
        "_id": "cal_" + uuid.uuid4().hex[:12],
        "date": date_str.strip(), # YYYYMMDD
        "event_name": event_name.strip(),
        "is_holiday": is_holiday,
        "created_at": int(time.time() * 1000)
    }
    database.academic_calendar.update_one(
        {"date": date_str.strip()},
        {"$set": doc},
        upsert=True
    )
    return doc

# ── Lecture & Attendance Engine ──

def start_lecture(classroom_id: str, teacher_id: str, subject_id: str) -> Dict:
    database = get_db()
    lecture_id = "lect_" + uuid.uuid4().hex[:12]
    
    # Generate unique 6 character temporary code, e.g. DBM472
    import random
    import string
    chars = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    code_hash = hash_lecture_code(chars)
    
    now = int(time.time())
    lecture_date = int(time.strftime("%Y%m%d"))
    doc = {
        "_id": lecture_id,
        "classroom_id": classroom_id,
        "teacher_id": teacher_id,
        "subject_id": subject_id,
        "lecture_date": lecture_date,
        "start_time": now,
        "end_time": 0,
        "lecture_code_hash": code_hash,
        "status": "active"
    }
    database.lectures.insert_one(doc)
    
    # Return document along with cleartext code (only exposed here on start)
    return_doc = doc.copy()
    return_doc["lecture_code"] = chars
    return return_doc

def record_attendance_join_by_code(
    lecture_code: str,
    student_id: str,
    join_time: int,
    device_info: Optional[str] = None,
    ip_address: Optional[str] = None,
    geo_location: Optional[Dict] = None
) -> Dict:
    database = get_db()
    code_hash = hash_lecture_code(lecture_code)
    
    # Find active lecture matching hashed code
    lecture = database.lectures.find_one({"lecture_code_hash": code_hash, "status": "active"})
    if not lecture:
        raise ValueError("Active lecture with this code not found or has expired.")
        
    classroom_id = lecture["classroom_id"]
    
    # Verify student is a permanent member of this classroom
    member = database.classroom_members.find_one({"classroom_id": classroom_id, "student_id": student_id})
    if not member:
        raise PermissionError("Student is not permanently enrolled in this classroom.")
        
    # Check late check-in
    status = "present"
    if join_time - lecture["start_time"] > 900: # 15 minutes late threshold
        status = "late"
        
    att_doc = {
        "lecture_id": lecture["_id"],
        "subject_id": lecture["subject_id"],
        "student_id": student_id,
        "join_time": join_time,
        "leave_time": 0,
        "duration_seconds": 0,
        "status": status,
        "source": "lecture_code",
        "device_info": device_info,
        "ip_address": ip_address,
        "geo_location": geo_location
    }
    
    database.attendance.update_one(
        {"lecture_id": lecture["_id"], "student_id": student_id},
        {"$set": att_doc},
        upsert=True
    )
    
    # Audit log entry in attendance_logs
    database.attendance_logs.insert_one({
        "_id": "log_" + uuid.uuid4().hex[:12],
        "lecture_id": lecture["_id"],
        "student_id": student_id,
        "action": "join",
        "timestamp": join_time,
        "ip_address": ip_address,
        "device_info": device_info
    })
    
    return att_doc

def record_attendance_leave(lecture_id: str, student_id: str, leave_time: int) -> bool:
    database = get_db()
    att = database.attendance.find_one({"lecture_id": lecture_id, "student_id": student_id})
    if not att:
        return False
        
    duration = max(0, leave_time - att.get("join_time", leave_time))
    status = att.get("status", "present")
    
    # If student left very early (e.g. before 10 minutes), they can be marked left early
    if duration < 600:
        status = "left_early"
        
    database.attendance.update_one(
        {"lecture_id": lecture_id, "student_id": student_id},
        {"$set": {"leave_time": leave_time, "duration_seconds": duration, "status": status}}
    )
    
    database.attendance_logs.insert_one({
        "_id": "log_" + uuid.uuid4().hex[:12],
        "lecture_id": lecture_id,
        "student_id": student_id,
        "action": "leave",
        "timestamp": leave_time,
        "ip_address": att.get("ip_address"),
        "device_info": att.get("device_info")
    })
    return True

def end_lecture(lecture_id: str, end_time: int) -> bool:
    database = get_db()
    lecture = database.lectures.find_one({"_id": lecture_id})
    if not lecture or lecture["status"] == "ended":
        return False
        
    classroom_id = lecture["classroom_id"]
    subject_id = lecture["subject_id"]
    
    # 1. Compare permanent classroom members vs actual attendees
    members = list(database.classroom_members.find({"classroom_id": classroom_id}))
    member_ids = [m["student_id"] for m in members]
    
    attendees = list(database.attendance.find({"lecture_id": lecture_id}))
    attendee_ids = [a["student_id"] for a in attendees]
    
    absent_ids = list(set(member_ids) - set(attendee_ids))
    if absent_ids:
        bulk_absent = []
        for sid in absent_ids:
            bulk_absent.append({
                "_id": "att_" + uuid.uuid4().hex[:12],
                "lecture_id": lecture_id,
                "subject_id": subject_id,
                "student_id": sid,
                "join_time": 0,
                "leave_time": 0,
                "duration_seconds": 0,
                "status": "absent",
                "source": "lecture_code",
                "device_info": None,
                "ip_address": None,
                "geo_location": None
            })
        database.attendance.insert_many(bulk_absent)
        
    # 2. Mark lecture ended & clear/expire the lecture code
    database.lectures.update_one(
        {"_id": lecture_id},
        {"$set": {"status": "ended", "end_time": end_time, "lecture_code_hash": None}}
    )
    return True

def edit_attendance(lecture_id: str, student_id: str, status: str, editor_role: str, duration_seconds: int = 0) -> bool:
    database = get_db()
    lecture = database.lectures.find_one({"_id": lecture_id})
    if not lecture:
        return False
        
    source = "teacher_manual" if editor_role == "teacher" else "admin_manual"
    
    database.attendance.update_one(
        {"lecture_id": lecture_id, "student_id": student_id},
        {
            "$set": {
                "status": status,
                "duration_seconds": duration_seconds,
                "subject_id": lecture["subject_id"],
                "source": source
            }
        },
        upsert=True
    )
    
    # Always log attendance modification in attendance_logs
    database.attendance_logs.insert_one({
        "_id": "log_" + uuid.uuid4().hex[:12],
        "lecture_id": lecture_id,
        "student_id": student_id,
        "action": f"edit_{status}",
        "timestamp": int(time.time()),
        "ip_address": "system_dashboard",
        "device_info": f"Modified by {editor_role}"
    })
    return True

# ── Dynamic Attendance Dashboard Calculation ──

def get_student_dashboard_stats(student_id: str) -> Dict:
    database = get_db()
    
    # 1. Overall stats
    records = list(database.attendance.find({"student_id": student_id}))
    total = len(records)
    
    present_statuses = ["present", "late", "excused", "left_early"]
    present_count = sum(1 for r in records if r["status"] in present_statuses)
    overall_pct = round((present_count / total) * 100, 2) if total > 0 else 0.0
    
    # 2. Subject-wise stats
    subject_map = {}
    subjects_cursor = database.subjects.find()
    subj_names = {s["_id"]: f"{s['code']}: {s['name']}" for s in subjects_cursor}
    
    for r in records:
        sid = r["subject_id"]
        if sid not in subject_map:
            subject_map[sid] = {"total": 0, "present": 0}
        subject_map[sid]["total"] += 1
        if r["status"] in present_statuses:
            subject_map[sid]["present"] += 1
            
    subject_stats = {}
    for sid, counts in subject_map.items():
        name = subj_names.get(sid, "Unknown Subject")
        subject_stats[name] = round((counts["present"] / counts["total"]) * 100, 2)
        
    # 3. Monthly stats
    monthly_map = {}
    for r in records:
        lecture = database.lectures.find_one({"_id": r["lecture_id"]})
        if lecture:
            month_str = time.strftime("%B %Y", time.localtime(lecture["start_time"]))
            if month_str not in monthly_map:
                monthly_map[month_str] = {"total": 0, "present": 0}
            monthly_map[month_str]["total"] += 1
            if r["status"] in present_statuses:
                monthly_map[month_str]["present"] += 1
                
    monthly_stats = {}
    for m, counts in monthly_map.items():
        monthly_stats[m] = round((counts["present"] / counts["total"]) * 100, 2)
        
    # 4. History timeline
    history = []
    lectures_cache = {l["_id"]: l for l in database.lectures.find({"_id": {"$in": [r["lecture_id"] for r in records]}})}
    for r in records:
        l = lectures_cache.get(r["lecture_id"])
        if l:
            history.append({
                "date": time.strftime("%d/%m/%Y %H:%M", time.localtime(l["start_time"])),
                "subject": subj_names.get(r["subject_id"], "Unknown"),
                "status": r["status"]
            })
            
    # 5. Today's Classes & Lecture Status
    today_classes = []
    today_active_lectures = []
    
    # Find student classrooms
    memberships = list(database.classroom_members.find({"student_id": student_id}))
    classroom_ids = [m["classroom_id"] for m in memberships]
    
    # Timetables for today (0=Monday, 6=Sunday)
    day_idx = (time.localtime().tm_wday)
    tt_slots = list(database.timetables.find({"classroom_id": {"$in": classroom_ids}, "day_of_week": day_idx}))
    for tt in tt_slots:
        today_classes.append({
            "subject": subj_names.get(tt["subject_id"], "Unknown"),
            "time": f"{tt['start_time']} - {tt['end_time']}"
        })
        
    # Active lectures today for enrolled classrooms
    active_lects = list(database.lectures.find({"classroom_id": {"$in": classroom_ids}, "status": "active"}))
    for al in active_lects:
        # Check if student already joined
        student_att = database.attendance.find_one({"lecture_id": al["_id"], "student_id": student_id})
        joined = student_att is not None
        today_active_lectures.append({
            "lecture_id": al["_id"],
            "subject": subj_names.get(al["subject_id"], "Unknown"),
            "joined": joined
        })
        
    # Announcements, Assignments, Quizzes, Notifications
    ann = list(database.announcements.find({"classroom_id": {"$in": classroom_ids}}).sort("created_at", -1).limit(5))
    ass = list(database.assignments.find({"classroom_id": {"$in": classroom_ids}}).sort("created_at", -1).limit(5))
    qiz = list(database.quizzes.find({"classroom_id": {"$in": classroom_ids}}).sort("created_at", -1).limit(5))
    notif = list(database.notifications.find({"user_id": student_id, "is_read": False}))
    
    return {
        "overall_attendance_percent": overall_pct,
        "subject_wise_attendance": subject_stats,
        "monthly_attendance": monthly_stats,
        "semester_attendance": overall_pct,
        "history": history,
        "today_classes": today_classes,
        "today_lecture_status": today_active_lectures,
        "announcements": [{"title": a.get("title"), "content": a.get("content")} for a in ann],
        "assignments": [{"title": a.get("title"), "due_date": a.get("due_date")} for a in ass],
        "quizzes": [{"title": q.get("title"), "due_date": q.get("due_date")} for q in qiz],
        "notifications_count": len(notif)
    }

def get_teacher_classroom_stats(classroom_id: str) -> Dict:
    database = get_db()
    classroom = database.classrooms.find_one({"_id": classroom_id})
    if not classroom:
        return {}
        
    members = list(database.classroom_members.find({"classroom_id": classroom_id}))
    member_ids = [m["student_id"] for m in members]
    total_students = len(member_ids)
    
    lectures = list(database.lectures.find({"classroom_id": classroom_id}))
    total_lectures = len(lectures)
    
    # Calculate attendance counts per student
    student_att_map = {sid: {"present": 0, "total": 0} for sid in member_ids}
    present_statuses = ["present", "late", "excused", "left_early"]
    
    all_attendance = list(database.attendance.find({"lecture_id": {"$in": [l["_id"] for l in lectures]}}))
    for a in all_attendance:
        sid = a["student_id"]
        if sid in student_att_map:
            student_att_map[sid]["total"] += 1
            if a["status"] in present_statuses:
                student_att_map[sid]["present"] += 1
                
    low_attendance = []
    users_cursor = database.users.find({"_id": {"$in": member_ids}})
    user_names = {u["_id"]: u["full_name"] for u in users_cursor}
    
    profiles_cursor = database.student_profiles.find({"_id": {"$in": member_ids}})
    roll_numbers = {p["_id"]: p.get("roll_number", "N/A") for p in profiles_cursor}
    
    for sid, counts in student_att_map.items():
        pct = round((counts["present"] / counts["total"]) * 100, 2) if counts["total"] > 0 else 0.0
        if pct < 75.0:
            low_attendance.append({
                "student_id": sid,
                "name": user_names.get(sid, "Unknown Student"),
                "roll_number": roll_numbers.get(sid, "N/A"),
                "attendance_percent": pct,
                "present": counts["present"],
                "total": counts["total"]
            })
            
    low_attendance.sort(key=lambda x: x["attendance_percent"])
    
    subjects_cursor = database.subjects.find()
    subj_names = {s["_id"]: s["name"] for s in subjects_cursor}
    
    recent_lectures = []
    lectures.sort(key=lambda x: x["start_time"], reverse=True)
    for l in lectures[:10]:
        recent_lectures.append({
            "lecture_id": l["_id"],
            "date": time.strftime("%d/%m/%Y %H:%M", time.localtime(l["start_time"])),
            "subject": subj_names.get(l["subject_id"], "Unknown"),
            "status": l["status"]
        })
        
    return {
        "total_students": total_students,
        "total_lectures": total_lectures,
        "low_attendance_students": low_attendance,
        "recent_lectures": recent_lectures
    }
