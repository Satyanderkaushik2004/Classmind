import csv
import time
import openpyxl
import uuid
import bcrypt
from io import BytesIO, StringIO
from typing import Optional, List, Dict
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import classroom_db
import auth_db

router = APIRouter(prefix="/api/classroom-system", tags=["Classroom System"])

# ── Role Authorization Helpers ──

def check_admin(request: Request):
    role = request.headers.get("X-User-Role")
    if role == "admin":
        return True
        
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        import main
        if token in main.admin_tokens:
            return True
            
    raise HTTPException(status_code=403, detail="Forbidden: Admin access required")

def check_teacher(request: Request):
    role = request.headers.get("X-User-Role")
    if role in ["teacher", "admin"]:
        return True
        
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        import main
        if token in main.admin_tokens:
            return True
            
    raise HTTPException(status_code=403, detail="Forbidden: Teacher or Admin access required")

def check_student(request: Request):
    role = request.headers.get("X-User-Role")
    if role in ["student", "teacher", "admin"]:
        return True
        
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        import main
        if token in main.admin_tokens:
            return True
            
    raise HTTPException(status_code=403, detail="Forbidden: Student, Teacher or Admin access required")

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

# ── Request Validation Models ──

class InstitutionReq(BaseModel):
    name: str
    code: str

class DepartmentReq(BaseModel):
    institution_id: str
    name: str
    code: str

class CourseReq(BaseModel):
    department_id: str
    name: str
    code: str
    duration_years: int

class SubjectReq(BaseModel):
    course_id: str
    name: str
    code: str
    semester: int

class ClassroomReq(BaseModel):
    course_id: str
    semester: int
    section: str
    academic_year: str
    teacher_id: Optional[str] = None

class AssignStudentsReq(BaseModel):
    classroom_id: str
    student_ids: List[str]

class AssignTeacherReq(BaseModel):
    classroom_id: str
    teacher_id: str
    subject_id: str

class TimetableReq(BaseModel):
    classroom_id: str
    day_of_week: int
    start_time: str
    end_time: str
    subject_id: str
    teacher_id: str

class StudentProfileReq(BaseModel):
    student_id: str
    roll_number: str
    registration_number: str
    course_id: str
    department_id: str
    semester: int
    section: str
    batch: str
    academic_year: str
    university_id: Optional[str] = None

class StartLectureReq(BaseModel):
    classroom_id: str
    teacher_id: str
    subject_id: str

class JoinLectureCodeReq(BaseModel):
    student_id: str
    lecture_code: str
    device_info: Optional[str] = None
    ip_address: Optional[str] = None
    geo_location: Optional[Dict[str, float]] = None

class LeaveLectureReq(BaseModel):
    lecture_id: str
    student_id: str

class EditAttendanceReq(BaseModel):
    status: str
    duration_seconds: int = 0

class PromoteStudentsReq(BaseModel):
    student_ids: List[str]
    new_semester: int
    new_academic_year: str

class TransferStudentReq(BaseModel):
    student_id: str
    new_classroom_id: str

class AcademicCalendarReq(BaseModel):
    date: str
    event_name: str
    is_holiday: bool = False

# ── API Endpoint Implementations ──

@router.post("/setup/institution")
async def setup_institution(req: InstitutionReq, request: Request):
    check_admin(request)
    try:
        doc = classroom_db.create_institution(req.name, req.code)
        return {"success": True, "institution": doc}
    except Exception as e:
        raise HTTPException(400, f"Failed to create institution: {e}")

@router.post("/setup/department")
async def setup_department(req: DepartmentReq, request: Request):
    check_admin(request)
    try:
        doc = classroom_db.create_department(req.institution_id, req.name, req.code)
        return {"success": True, "department": doc}
    except Exception as e:
        raise HTTPException(400, f"Failed to create department: {e}")

@router.post("/setup/course")
async def setup_course(req: CourseReq, request: Request):
    check_admin(request)
    try:
        doc = classroom_db.create_course(req.department_id, req.name, req.code, req.duration_years)
        return {"success": True, "course": doc}
    except Exception as e:
        raise HTTPException(400, f"Failed to create course: {e}")

@router.post("/setup/subject")
async def setup_subject(req: SubjectReq, request: Request):
    check_admin(request)
    try:
        doc = classroom_db.create_subject(req.course_id, req.name, req.code, req.semester)
        return {"success": True, "subject": doc}
    except Exception as e:
        raise HTTPException(400, f"Failed to create subject: {e}")

@router.post("/setup/classroom")
async def setup_classroom(req: ClassroomReq, request: Request):
    check_admin(request)
    try:
        doc = classroom_db.create_classroom(req.course_id, req.semester, req.section, req.academic_year, req.teacher_id)
        return {"success": True, "classroom": doc}
    except Exception as e:
        raise HTTPException(400, f"Failed to create classroom: {e}")

@router.post("/setup/enroll-students")
async def enroll_students(req: AssignStudentsReq, request: Request):
    check_admin(request)
    try:
        enrolled = []
        for sid in req.student_ids:
            doc = classroom_db.create_classroom_member(req.classroom_id, sid, "admin_manual")
            enrolled.append(doc)
        return {"success": True, "enrolled_count": len(enrolled)}
    except Exception as e:
        raise HTTPException(400, f"Failed to enroll students: {e}")

@router.post("/setup/assign-teacher")
async def assign_teacher(req: AssignTeacherReq, request: Request):
    check_admin(request)
    try:
        doc = classroom_db.assign_classroom_teacher(req.classroom_id, req.teacher_id, req.subject_id)
        return {"success": True, "assignment": doc}
    except Exception as e:
        raise HTTPException(400, f"Failed to assign teacher: {e}")

@router.post("/setup/timetable")
async def setup_timetable(req: TimetableReq, request: Request):
    check_admin(request)
    try:
        doc = classroom_db.create_timetable(req.classroom_id, req.day_of_week, req.start_time, req.end_time, req.subject_id, req.teacher_id)
        return {"success": True, "timetable": doc}
    except Exception as e:
        raise HTTPException(400, f"Failed to create timetable slot: {e}")

@router.post("/setup/student-profile")
async def setup_student_profile(req: StudentProfileReq, request: Request):
    check_admin(request)
    try:
        doc = classroom_db.create_student_profile(
            req.student_id, req.roll_number, req.registration_number,
            req.course_id, req.department_id, req.semester, req.section,
            req.batch, req.academic_year, req.university_id
        )
        return {"success": True, "profile": doc}
    except Exception as e:
        raise HTTPException(400, f"Failed to create student profile: {e}")

@router.post("/setup/academic-calendar")
async def setup_academic_calendar(req: AcademicCalendarReq, request: Request):
    check_admin(request)
    try:
        doc = classroom_db.create_academic_calendar(req.date, req.event_name, req.is_holiday)
        return {"success": True, "calendar_event": doc}
    except Exception as e:
        raise HTTPException(400, f"Failed to create academic calendar event: {e}")

@router.post("/setup/enroll-bulk/{classroom_id}")
async def enroll_bulk_csv_excel(classroom_id: str, request: Request, file: UploadFile = File(...)):
    check_teacher(request)
    db = classroom_db.get_db()
    classroom = db.classrooms.find_one({"_id": classroom_id})
    if not classroom:
        raise HTTPException(404, "Classroom not found")
        
    course_id = classroom["course_id"]
    course = db.courses.find_one({"_id": course_id})
    department_id = course["department_id"] if course else ""
    
    students_enrolled = 0
    filename = file.filename.lower()
    
    try:
        rows = []
        if filename.endswith(".csv"):
            content = await file.read()
            decoded = content.decode("utf-8")
            csv_reader = csv.DictReader(StringIO(decoded))
            for r in csv_reader:
                rows.append(r)
        elif filename.endswith(".xlsx"):
            content = await file.read()
            wb = openpyxl.load_workbook(BytesIO(content))
            sheet = wb.active
            headers = [cell.value for cell in sheet[1]]
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if any(row):
                    rows.append(dict(zip(headers, row)))
        else:
            raise HTTPException(400, "Unsupported file format. Please upload CSV or XLSX.")

        for row in rows:
            email = row.get("Email") or row.get("email")
            full_name = row.get("Name") or row.get("name") or row.get("Full Name") or row.get("full_name")
            roll_number = row.get("Roll Number") or row.get("roll_number") or row.get("Roll No") or row.get("roll_no")
            reg_number = row.get("Registration Number") or row.get("registration_number") or row.get("Reg No") or row.get("reg_no")
            batch = row.get("Batch") or row.get("batch") or classroom["academic_year"]
            univ_id = row.get("University ID") or row.get("university_id") or None
            
            if not email or not full_name or not roll_number or not reg_number:
                continue
                
            email_clean = email.strip().lower()
            
            # Find or create user
            user = db.users.find_one({"email": email_clean})
            if not user:
                user_id = "u_" + uuid.uuid4().hex[:12]
                db.users.insert_one({
                    "_id": user_id,
                    "full_name": full_name.strip(),
                    "email": email_clean,
                    "password_hash": hash_password("TempPassword123!"),
                    "role": "student",
                    "profile_photo": None,
                    "email_verified": True,
                    "created_at": int(time.time() * 1000)
                })
            else:
                user_id = user["_id"]
                
            # Create student profile
            classroom_db.create_student_profile(
                student_id=user_id,
                roll_number=str(roll_number),
                registration_number=str(reg_number),
                course_id=course_id,
                department_id=department_id,
                semester=classroom["semester"],
                section=classroom["section"],
                batch=str(batch),
                academic_year=classroom["academic_year"],
                university_id=str(univ_id) if univ_id else None
            )
            
            # Enroll in classroom permanently
            classroom_db.create_classroom_member(classroom_id, user_id, "csv")
            students_enrolled += 1
            
        return {"success": True, "enrolled_count": students_enrolled}
    except Exception as e:
        raise HTTPException(400, f"Error processing bulk enrollment file: {e}")

# ── Lecture and Real-Time Attendance ──

@router.post("/lectures/start")
async def start_lecture_session(req: StartLectureReq, request: Request):
    check_teacher(request)
    try:
        doc = classroom_db.start_lecture(req.classroom_id, req.teacher_id, req.subject_id)
        # Never store plain-text code in DB; hashes only. Returns plain lecture_code to teacher.
        return {"success": True, "lecture": doc}
    except Exception as e:
        raise HTTPException(400, f"Failed to start lecture: {e}")

@router.post("/lectures/join-by-code")
async def join_lecture_by_code(req: JoinLectureCodeReq, request: Request):
    check_student(request)
    try:
        doc = classroom_db.record_attendance_join_by_code(
            req.lecture_code, req.student_id, int(time.time()),
            req.device_info, req.ip_address, req.geo_location
        )
        return {"success": True, "attendance": doc}
    except ValueError as ve:
        raise HTTPException(404, str(ve))
    except PermissionError as pe:
        raise HTTPException(403, str(pe))
    except Exception as e:
        raise HTTPException(400, f"Failed to join lecture: {e}")

@router.post("/lectures/leave")
async def leave_lecture(req: LeaveLectureReq, request: Request):
    check_student(request)
    try:
        success = classroom_db.record_attendance_leave(req.lecture_id, req.student_id, int(time.time()))
        return {"success": success}
    except Exception as e:
        raise HTTPException(400, f"Failed to leave lecture: {e}")

@router.post("/lectures/{lecture_id}/end")
async def end_lecture_session(lecture_id: str, request: Request):
    check_teacher(request)
    try:
        success = classroom_db.end_lecture(lecture_id, int(time.time()))
        return {"success": success}
    except Exception as e:
        raise HTTPException(400, f"Failed to end lecture: {e}")

@router.patch("/lectures/{lecture_id}/attendance/{student_id}")
async def force_edit_attendance(lecture_id: str, student_id: str, req: EditAttendanceReq, request: Request):
    role = request.headers.get("X-User-Role", "teacher")
    check_teacher(request)
    try:
        success = classroom_db.edit_attendance(lecture_id, student_id, req.status, role, req.duration_seconds)
        return {"success": success}
    except Exception as e:
        raise HTTPException(400, f"Failed to edit attendance: {e}")

# ── Dashboard Statistics ──

@router.get("/dashboards/student/{student_id}/attendance")
async def get_student_stats(student_id: str, request: Request):
    check_student(request)
    return classroom_db.get_student_dashboard_stats(student_id)

@router.get("/dashboards/teacher/{teacher_id}/classes")
async def get_teacher_classes(teacher_id: str, request: Request):
    check_teacher(request)
    db = classroom_db.get_db()
    
    # Query classroom_teachers to find teacher assigned classes
    assignments = list(db.classroom_teachers.find({"teacher_id": teacher_id}))
    classroom_ids = [a["classroom_id"] for a in assignments]
    
    classrooms = list(db.classrooms.find({"_id": {"$in": classroom_ids}, "is_archived": False}))
    courses = {c["_id"]: c["name"] for c in db.courses.find()}
    
    my_classes = []
    for c in classrooms:
        course_name = courses.get(c["course_id"], "B.Tech")
        my_classes.append({
            "classroom_id": c["_id"],
            "name": f"{course_name} Sem-{c['semester']} {c['section']}"
        })
    return {"success": True, "classes": my_classes}

@router.get("/dashboards/teacher/classroom/{classroom_id}/attendance")
async def get_teacher_stats(classroom_id: str, request: Request):
    check_teacher(request)
    return classroom_db.get_teacher_classroom_stats(classroom_id)

@router.get("/dashboards/teacher/classroom/{classroom_id}/attendance/export")
async def export_classroom_attendance(classroom_id: str, request: Request):
    check_teacher(request)
    db = classroom_db.get_db()
    classroom = db.classrooms.find_one({"_id": classroom_id})
    if not classroom:
        raise HTTPException(404, "Classroom not found")
        
    members = list(db.classroom_members.find({"classroom_id": classroom_id}))
    member_ids = [m["student_id"] for m in members]
    
    users_cursor = db.users.find({"_id": {"$in": member_ids}})
    user_names = {u["_id"]: u["full_name"] for u in users_cursor}
    
    profiles_cursor = db.student_profiles.find({"_id": {"$in": member_ids}})
    roll_numbers = {p["_id"]: p.get("roll_number", "N/A") for p in profiles_cursor}
    
    lectures = list(db.lectures.find({"classroom_id": classroom_id, "status": "ended"}))
    lectures.sort(key=lambda x: x["start_time"])
    
    subjects_cursor = db.subjects.find()
    subj_codes = {s["_id"]: s["code"] for s in subjects_cursor}
    
    attendance_recs = list(db.attendance.find({"lecture_id": {"$in": [l["_id"] for l in lectures]}}))
    att_map = {}
    for a in attendance_recs:
        key = (a["lecture_id"], a["student_id"])
        att_map[key] = a["status"]

    output = StringIO()
    writer = csv.writer(output)
    
    header = ["Roll Number", "Name"]
    for l in lectures:
        date_str = time.strftime("%d/%m/%Y %H:%M", time.localtime(l["start_time"]))
        sub_code = subj_codes.get(l["subject_id"], "Sub")
        header.append(f"{date_str} ({sub_code})")
    header.append("Overall Attendance %")
    
    writer.writerow(header)
    
    for sid in member_ids:
        row = [
            roll_numbers.get(sid, "N/A"),
            user_names.get(sid, "Unknown")
        ]
        
        present_count = 0
        total_slots = len(lectures)
        
        for l in lectures:
            status = att_map.get((l["_id"], sid), "absent")
            row.append(status.capitalize())
            if status in ["present", "late", "excused"]:
                present_count += 1
                
        pct = round((present_count / total_slots) * 100, 2) if total_slots > 0 else 0.0
        row.append(f"{pct}%")
        writer.writerow(row)
        
    output.seek(0)
    filename = f"attendance_{classroom['section']}_{classroom['academic_year']}.csv"
    
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

# ── Semester & Course Management ──

@router.post("/admin/semesters/archive/{classroom_id}")
async def archive_classroom(classroom_id: str, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    res = db.classrooms.update_one({"_id": classroom_id}, {"$set": {"is_archived": True}})
    if res.modified_count > 0:
        return {"success": True, "message": "Classroom archived successfully."}
    raise HTTPException(400, "Classroom could not be archived or is already archived.")

@router.post("/admin/students/transfer")
async def transfer_student(req: TransferStudentReq, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    classroom = db.classrooms.find_one({"_id": req.new_classroom_id})
    if not classroom:
        raise HTTPException(404, "Target classroom not found")
        
    db.classroom_members.delete_many({"student_id": req.student_id})
    classroom_db.create_classroom_member(req.new_classroom_id, req.student_id, "transfer")
    
    db.student_profiles.update_one(
        {"_id": req.student_id},
        {"$set": {"semester": classroom["semester"], "section": classroom["section"], "academic_year": classroom["academic_year"]}}
    )
    
    # Audit log entry in student_enrollment_history
    db.student_enrollment_history.insert_one({
        "_id": "eh_" + uuid.uuid4().hex[:12],
        "student_id": req.student_id,
        "classroom_id": req.new_classroom_id,
        "action": "transfer",
        "timestamp": int(time.time() * 1000)
    })
    return {"success": True, "message": "Student transferred successfully."}

@router.post("/admin/students/promote")
async def promote_students(req: PromoteStudentsReq, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.student_profiles.update_many(
        {"_id": {"$in": req.student_ids}},
        {"$set": {"semester": req.new_semester, "academic_year": req.new_academic_year}}
    )
    
    # Log promotion history records
    bulk_history = []
    for sid in req.student_ids:
        bulk_history.append({
            "_id": "eh_" + uuid.uuid4().hex[:12],
            "student_id": sid,
            "classroom_id": "promoted_sem_" + str(req.new_semester),
            "action": "promote",
            "timestamp": int(time.time() * 1000)
        })
    if bulk_history:
        db.student_enrollment_history.insert_many(bulk_history)
        
    return {"success": True, "message": f"Successfully promoted {len(req.student_ids)} students to semester {req.new_semester}."}

# ── Admin CRUD Endpoints ──

class EditInstitutionReq(BaseModel):
    name: str
    code: str

class EditDepartmentReq(BaseModel):
    name: str
    code: str

class EditCourseReq(BaseModel):
    name: str
    code: str
    duration_years: int

class EditSubjectReq(BaseModel):
    name: str
    code: str
    semester: int

class EditClassroomReq(BaseModel):
    semester: int
    section: str
    academic_year: str
    teacher_id: Optional[str] = None

class CreateStudentReq(BaseModel):
    email: str
    full_name: str
    roll_number: str
    registration_number: str
    course_id: str
    department_id: str
    semester: int
    section: str
    batch: str
    academic_year: str
    university_id: Optional[str] = None

class CreateTeacherReq(BaseModel):
    email: str
    full_name: str
    organization: str
    designation: str
    department: str
    phone: Optional[str] = None
    bio: Optional[str] = None

@router.get("/admin/dashboard-stats")
async def get_admin_dashboard_stats(request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    
    total_students = db.student_profiles.count_documents({})
    total_teachers = db.teacher_profiles.count_documents({})
    total_departments = db.departments.count_documents({})
    total_courses = db.courses.count_documents({})
    total_subjects = db.subjects.count_documents({})
    total_classrooms = db.classrooms.count_documents({})
    active_lectures = db.lectures.count_documents({"status": "active"})
    
    # Calculate today's attendance percent
    import datetime
    today_str = datetime.date.today().strftime("%Y%m%d")
    today_lectures = list(db.lectures.find({"lecture_date": int(today_str)}))
    today_lect_ids = [l["_id"] for l in today_lectures]
    
    present_statuses = ["present", "late", "excused", "left_early"]
    total_att = db.attendance.count_documents({"lecture_id": {"$in": today_lect_ids}})
    present_att = db.attendance.count_documents({"lecture_id": {"$in": today_lect_ids}, "status": {"$in": present_statuses}})
    today_att_pct = round((present_att / total_att) * 100, 2) if total_att > 0 else 0.0
    
    # Recent Activities
    recent_logs = list(db.attendance_logs.find().sort("timestamp", -1).limit(5))
    activities = []
    
    uids = [l["student_id"] for l in recent_logs]
    users = {u["_id"]: u["full_name"] for u in db.users.find({"_id": {"$in": uids}})}
    
    for l in recent_logs:
        name = users.get(l["student_id"], "Student")
        action = l["action"]
        timestamp_str = time.strftime("%H:%M:%S", time.localtime(l["timestamp"]))
        activities.append({
            "activity": f"{name} performed check-in '{action}'",
            "time": timestamp_str
        })
        
    return {
        "total_students": total_students,
        "total_teachers": total_teachers,
        "total_departments": total_departments,
        "total_courses": total_courses,
        "total_subjects": total_subjects,
        "total_classrooms": total_classrooms,
        "active_lectures": active_lectures,
        "today_attendance_percent": today_att_pct,
        "recent_activities": activities
    }

# 1. Institutions List & CRUD
@router.get("/setup/institutions")
async def get_institutions(request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    return {"success": True, "institutions": list(db.institutions.find())}

@router.put("/setup/institution/{id}")
async def edit_institution(id: str, req: EditInstitutionReq, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.institutions.update_one({"_id": id}, {"$set": {"name": req.name, "code": req.code.upper()}})
    return {"success": True}

@router.delete("/setup/institution/{id}")
async def delete_institution(id: str, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.institutions.delete_one({"_id": id})
    return {"success": True}

# 2. Departments List & CRUD
@router.get("/setup/departments")
async def get_departments(request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    return {"success": True, "departments": list(db.departments.find())}

@router.put("/setup/department/{id}")
async def edit_department(id: str, req: EditDepartmentReq, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.departments.update_one({"_id": id}, {"$set": {"name": req.name, "code": req.code.upper()}})
    return {"success": True}

@router.delete("/setup/department/{id}")
async def delete_department(id: str, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.departments.delete_one({"_id": id})
    return {"success": True}

# 3. Courses List & CRUD
@router.get("/setup/courses")
async def get_courses(request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    return {"success": True, "courses": list(db.courses.find())}

@router.put("/setup/course/{id}")
async def edit_course(id: str, req: EditCourseReq, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.courses.update_one({"_id": id}, {"$set": {"name": req.name, "code": req.code.upper(), "duration_years": req.duration_years}})
    return {"success": True}

@router.delete("/setup/course/{id}")
async def delete_course(id: str, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.courses.delete_one({"_id": id})
    return {"success": True}

# 4. Subjects List & CRUD
@router.get("/setup/subjects")
async def get_subjects(request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    return {"success": True, "subjects": list(db.subjects.find())}

@router.put("/setup/subject/{id}")
async def edit_subject(id: str, req: EditSubjectReq, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.subjects.update_one({"_id": id}, {"$set": {"name": req.name, "code": req.code.upper(), "semester": req.semester}})
    return {"success": True}

@router.delete("/setup/subject/{id}")
async def delete_subject(id: str, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.subjects.delete_one({"_id": id})
    return {"success": True}

# 5. Classrooms List & CRUD
@router.get("/setup/classrooms")
async def get_classrooms(request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    return {"success": True, "classrooms": list(db.classrooms.find())}

@router.put("/setup/classroom/{id}")
async def edit_classroom(id: str, req: EditClassroomReq, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.classrooms.update_one({"_id": id}, {"$set": {"semester": req.semester, "section": req.section.upper(), "academic_year": req.academic_year, "teacher_id": req.teacher_id}})
    return {"success": True}

@router.delete("/setup/classroom/{id}")
async def delete_classroom(id: str, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.classrooms.delete_one({"_id": id})
    return {"success": True}

# 6. Students List & CRUD
@router.get("/setup/students")
async def get_students(request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    users = list(db.users.find({"role": "student"}))
    user_ids = [u["_id"] for u in users]
    profiles = {p["_id"]: p for p in db.student_profiles.find({"_id": {"$in": user_ids}})}
    
    student_list = []
    for u in users:
        p = profiles.get(u["_id"], {})
        student_list.append({
            "student_id": u["_id"],
            "full_name": u["full_name"],
            "email": u["email"],
            "roll_number": p.get("roll_number", "N/A"),
            "registration_number": p.get("registration_number", "N/A"),
            "course_id": p.get("course_id", "N/A"),
            "department_id": p.get("department_id", "N/A"),
            "semester": p.get("semester", 1),
            "section": p.get("section", "A"),
            "batch": p.get("batch", "N/A"),
            "academic_year": p.get("academic_year", "N/A"),
            "university_id": p.get("university_id", "N/A")
        })
    return {"success": True, "students": student_list}

@router.post("/setup/student")
async def create_student(req: CreateStudentReq, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    
    if db.users.find_one({"email": req.email.strip().lower()}):
        raise HTTPException(400, "Email is already registered.")
        
    student_id = "u_" + uuid.uuid4().hex[:12]
    db.users.insert_one({
        "_id": student_id,
        "full_name": req.full_name.strip(),
        "email": req.email.strip().lower(),
        "password_hash": hash_password("TempPassword123!"),
        "role": "student",
        "profile_photo": None,
        "email_verified": True,
        "created_at": int(time.time() * 1000)
    })
    classroom_db.create_student_profile(
        student_id, req.roll_number, req.registration_number,
        req.course_id, req.department_id, req.semester, req.section,
        req.batch, req.academic_year, req.university_id
    )
    return {"success": True, "student_id": student_id}

@router.put("/setup/student/{id}")
async def edit_student(id: str, req: CreateStudentReq, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.users.update_one({"_id": id}, {"$set": {"full_name": req.full_name, "email": req.email.strip().lower()}})
    classroom_db.create_student_profile(
        id, req.roll_number, req.registration_number,
        req.course_id, req.department_id, req.semester, req.section,
        req.batch, req.academic_year, req.university_id
    )
    return {"success": True}

@router.delete("/setup/student/{id}")
async def delete_student(id: str, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.users.delete_one({"_id": id})
    db.student_profiles.delete_one({"_id": id})
    db.classroom_members.delete_many({"student_id": id})
    return {"success": True}

# 7. Teachers List & CRUD
@router.get("/setup/teachers")
async def get_teachers(request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    users = list(db.users.find({"role": "teacher"}))
    user_ids = [u["_id"] for u in users]
    profiles = {p["_id"]: p for p in db.teacher_profiles.find({"_id": {"$in": user_ids}})}
    
    teacher_list = []
    for u in users:
        p = profiles.get(u["_id"], {})
        teacher_list.append({
            "teacher_id": u["_id"],
            "full_name": u["full_name"],
            "email": u["email"],
            "organization": p.get("organization", "N/A"),
            "designation": p.get("designation", "N/A"),
            "department": p.get("department", "N/A"),
            "phone": p.get("phone", "N/A"),
            "bio": p.get("bio", "N/A")
        })
    return {"success": True, "teachers": teacher_list}

@router.post("/setup/teacher")
async def create_teacher(req: CreateTeacherReq, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    
    if db.users.find_one({"email": req.email.strip().lower()}):
        raise HTTPException(400, "Email is already registered.")
        
    teacher_id = "u_" + uuid.uuid4().hex[:12]
    db.users.insert_one({
        "_id": teacher_id,
        "full_name": req.full_name.strip(),
        "email": req.email.strip().lower(),
        "password_hash": hash_password("TempPassword123!"),
        "role": "teacher",
        "profile_photo": None,
        "email_verified": True,
        "created_at": int(time.time() * 1000)
    })
    db.teacher_profiles.insert_one({
        "_id": teacher_id,
        "organization": req.organization.strip(),
        "designation": req.designation.strip(),
        "department": req.department.strip(),
        "phone": req.phone,
        "bio": req.bio,
        "is_verified_teacher": True,
        "created_at": int(time.time() * 1000)
    })
    return {"success": True, "teacher_id": teacher_id}

@router.put("/setup/teacher/{id}")
async def edit_teacher(id: str, req: CreateTeacherReq, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.users.update_one({"_id": id}, {"$set": {"full_name": req.full_name, "email": req.email.strip().lower()}})
    db.teacher_profiles.update_one({"_id": id}, {"$set": {
        "organization": req.organization,
        "designation": req.designation,
        "department": req.department,
        "phone": req.phone,
        "bio": req.bio
    }})
    return {"success": True}

@router.delete("/setup/teacher/{id}")
async def delete_teacher(id: str, request: Request):
    check_admin(request)
    db = classroom_db.get_db()
    db.users.delete_one({"_id": id})
    db.teacher_profiles.delete_one({"_id": id})
    db.classroom_teachers.delete_many({"teacher_id": id})
    return {"success": True}

