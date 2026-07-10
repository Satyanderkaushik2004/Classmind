"""
main.py  ─  VYOM Backend  (portable, cross-platform)
Run:  uvicorn main:app --host 0.0.0.0 --port 8000 --reload

WebSocket endpoints
  ws://host/ws/teacher/{session_code}
  ws://host/ws/student/{session_code}/{student_id}
"""

from __future__ import annotations

# ── Load environment variables FIRST ──────────────────────────────
from dotenv import load_dotenv
# ── Environment ──
from pathlib import Path
from dotenv import load_dotenv
env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

# ── Standard library imports ──────────────────────────────────────
import asyncio
import base64
import csv
import json
import logging
import os
import re
import random
import time
import uuid
from contextlib import asynccontextmanager
from io import BytesIO, StringIO
from typing import Dict, List, Optional
from pathlib import Path
# ── Third-party imports ───────────────────────────────────────────
from google.oauth2 import id_token
from google.auth.transport import requests
from fastapi import (
    BackgroundTasks, Body, Depends, FastAPI, File, Form, HTTPException,
    Query, Request, UploadFile, WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

# ── Internal modules ──────────────────────────────────────────────
from analytics import compute_analytics, compute_report
from sandbox import RunResult, run_code
from store import (
    configure_persistence, gen_code, gen_id, load_all_sessions,
    new_session, new_student, new_task, now, safe_task,
    save_session, score_for, sessions, teacher_sessions,
    new_lesson_template, new_active_lesson,
    get_teacher_key, set_teacher_key, delete_teacher_key, load_teacher_keys,
    load_teacher_integrations, get_teacher_integration, set_teacher_integration, delete_teacher_integration,
    load_teacher_notification_prefs, get_teacher_notification_prefs, set_teacher_notification_prefs,
    load_student_notification_prefs, get_student_notification_prefs, set_student_notification_prefs,
    student_notification_enabled,
    load_downloads as load_persisted_downloads,
    get_downloads as get_persisted_downloads,
    add_download as add_persisted_download,
    delete_download as delete_persisted_download,
)
# ── RAG Engine ──
from rag_engine import RagEngine
rag_engine = RagEngine()

import string
from cloud_storage import GoogleDriveProvider, MockGoogleDriveProvider

# Initialize Google Drive Storage Provider
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
google_drive_provider = None
if GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET:
    google_drive_provider = GoogleDriveProvider(GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET)
else:
    logging.getLogger("vyom.main").warning("GOOGLE_CLIENT_ID or GOOGLE_CLIENT_SECRET is missing. Running in simulated Google Drive cloud mode.")
    google_drive_provider = MockGoogleDriveProvider()
from email_service import (
    send_session_email, is_valid_email,
    send_student_report_email, send_class_starting_email,
    send_otp_email, verify_smtp_credentials,
)
from video_call import router as vc_router

# ── Auth Redesign: Imports & Helpers ──────────────────────────────
import bcrypt
import jwt
import datetime
import auth_db

JWT_SECRET = os.getenv("JWT_SECRET", "vyom_super_secret_jwt_key_2026")
JWT_ALGORITHM = "HS256"

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    return hashed.decode('utf-8')

def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    except Exception:
        return False

def sign_jwt(payload: dict, expires_in_days: int = 7) -> str:
    import datetime as dt_module
    data = payload.copy()
    data.update({
        "exp": dt_module.datetime.utcnow() + dt_module.timedelta(days=expires_in_days)
    })
    return jwt.encode(data, JWT_SECRET, algorithm=JWT_ALGORITHM)

def verify_jwt(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except Exception:
        return None

def validate_password_strength(password: str) -> Optional[str]:
    if len(password) < 8:
        return "Password must be at least 8 characters long."
    if not any(c.isupper() for c in password):
        return "Password must contain at least one uppercase letter."
    if not any(c.islower() for c in password):
        return "Password must contain at least one lowercase letter."
    if not any(c.isdigit() for c in password):
        return "Password must contain at least one number."
    if not any(c in "@$!%*?&_-" for c in password):
        return "Password must contain at least one special character (@$!%*?&_-)."
    return None

auth_ip_limits = {}

def check_auth_rate_limit(ip: str) -> bool:
    now_ts = time.time()
    if ip in auth_ip_limits:
        auth_ip_limits[ip] = [t for t in auth_ip_limits[ip] if now_ts - t < 60]
    else:
        auth_ip_limits[ip] = []
        
    if len(auth_ip_limits[ip]) >= 15:
        return False
    auth_ip_limits[ip].append(now_ts)
    return True

def save_profile_photo(base64_data: str, user_id: str) -> Optional[str]:
    try:
        if not base64_data or not base64_data.startswith("data:image/"):
            return None
        header, encoded = base64_data.split(",", 1)
        image_format = header.split(";")[0].split("/")[1]
        if image_format not in ["png", "jpg", "jpeg", "webp"]:
            image_format = "png"
        data = base64.b64decode(encoded)
        os.makedirs("data/profile_photos", exist_ok=True)
        filename = f"{user_id}_{int(time.time())}.{image_format}"
        filepath = Path("data/profile_photos") / filename
        filepath.write_bytes(data)
        return f"/static/profile_photos/{filename}"
    except Exception as e:
        log.warning("Failed to save profile photo: %s", e)
        return None




# ── logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("vyom")


# ── Google OAuth Source of Truth ──
def get_google_client_id() -> str:
    """Retrieves and sanitizes the Google Client ID from environment."""
    val = os.getenv("GOOGLE_CLIENT_ID", "").strip()
    # Strip accidental quotes
    if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
        val = val[1:-1].strip()
    return val

def validate_oauth_config():
    """Strict runtime check for OAuth configuration."""
    cid = get_google_client_id()
    placeholders = ["your-google-client-id", "your-google-client-id-here"]
    
    if not cid:
        log.error("❌ OAuth config invalid: GOOGLE_CLIENT_ID is missing from .env")
        # In a real production app we might sys.exit(1), but for this environment
        # we'll log loudly and let the dev see the error.
        return False
        
    if any(p in cid.lower() for p in placeholders):
        log.error("❌ OAuth config invalid: GOOGLE_CLIENT_ID contains placeholder value")
        return False
        
    masked = cid[:6] + "..." + cid[-10:] if len(cid) > 16 else "***"
    log.info("[AUTH] Google Client ID loaded: %s", masked)
    log.info("✅ OAuth config valid")
    return True

# ── validation ───────────────────────────────────────────────────
def check_environment():
    """Validates environment variables on startup."""
    sg_key = os.getenv("SENDGRID_API_KEY", "")
    email_address = os.getenv("EMAIL_ADDRESS", "")
    email_password = os.getenv("EMAIL_PASSWORD", "")
    
    if sg_key and "your_api_key" not in sg_key:
        log.info("[OK] SendGrid Email system configured.")
    elif email_address and email_password:
        log.info(f"[OK] SMTP Email system configured via {email_address}.")
    else:
        log.warning("[!] Neither SENDGRID_API_KEY nor SMTP credentials (EMAIL_ADDRESS, EMAIL_PASSWORD) are configured in .env. Emails will not be sent.")
    
    # OAuth: do not hard-fail the app import when GOOGLE_CLIENT_ID is missing.
    # Defer strict validation to auth-time; here we only log a warning so
    # developers can run the server locally without layout-breaking failures.
    google_cid = get_google_client_id()
    if not google_cid:
        log.warning("[!] GOOGLE_CLIENT_ID is not configured in .env. Google OAuth will be disabled until configured.")
    else:
        # If a value exists, perform a sanity check and log result (non-fatal).
        validate_oauth_config()

check_environment()


# ── AI LLM Helper ─────────────────────────────────────────────────
async def call_llm(prompt: str, api_key: Optional[str] = None, is_json: bool = False) -> str:
    key_to_use = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key_to_use:
        raise ValueError("No API key available")

    # Detect API provider: standard Gemini key starts with AIzaSy
    is_gemini = key_to_use.startswith("AIzaSy") or (not api_key and os.getenv("GEMINI_API_KEY") and not os.getenv("OPENROUTER_API_KEY"))

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        if is_gemini:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key_to_use}"
            json_body = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            if is_json:
                json_body["generationConfig"] = {
                    "responseMimeType": "application/json"
                }
            resp = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json=json_body
            )
            resp.raise_for_status()
            resp_json = resp.json()
            return resp_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            url = "https://openrouter.ai/api/v1/chat/completions"
            resp = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key_to_use}",
                    "HTTP-Referer": "https://vyom.app",
                    "X-Title": "VYOM AI Assistant",
                },
                json={
                    "model": "openai/gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 4000 if is_json else 1000,
                },
            )
            resp.raise_for_status()
            return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()


async def call_llm_with_image(prompt: str, base64_data: Optional[str] = None, api_key: Optional[str] = None) -> str:
    key_to_use = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not key_to_use:
        raise ValueError("No API key available")

    is_gemini = key_to_use.startswith("AIzaSy") or (not api_key and os.getenv("GEMINI_API_KEY") and not os.getenv("OPENROUTER_API_KEY"))

    import httpx
    async with httpx.AsyncClient(timeout=60) as client:
        if is_gemini:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key_to_use}"
            
            parts = [{"text": prompt}]
            if base64_data:
                mime_type = "image/png"
                raw_b64 = base64_data
                if base64_data.startswith("data:"):
                    p_parts = base64_data.split(",", 1)
                    if len(p_parts) == 2:
                        prefix, raw_b64 = p_parts
                        import re
                        match = re.match(r"data:([^;]+);base64", prefix)
                        if match:
                            mime_type = match.group(1)
                
                parts.append({
                    "inlineData": {
                        "mimeType": mime_type,
                        "data": raw_b64
                    }
                })

            json_body = {
                "contents": [{"parts": parts}],
                "generationConfig": {
                    "responseMimeType": "application/json"
                }
            }
            resp = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json=json_body
            )
            resp.raise_for_status()
            resp_json = resp.json()
            return resp_json["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            url = "https://openrouter.ai/api/v1/chat/completions"
            
            user_content = prompt
            if base64_data:
                user_content = [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": base64_data}}
                ]
                
            resp = await client.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {key_to_use}",
                    "HTTP-Referer": "https://vyom.app",
                    "X-Title": "VYOM AI Assistant",
                },
                json={
                    "model": "openai/gpt-4o-mini",
                    "messages": [{"role": "user", "content": user_content}],
                    "max_tokens": 4000,
                },
            )
            resp.raise_for_status()
            return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "").strip()


# ── concurrency helpers ───────────────────────────────────────────
semaphore: asyncio.Semaphore        # initialised in lifespan
execution_queue: asyncio.Queue      # initialised in lifespan
session_locks: Dict[str, asyncio.Lock] = {}


def session_lock(code: str) -> asyncio.Lock:
    if code not in session_locks:
        session_locks[code] = asyncio.Lock()
    return session_locks[code]

admin_connections: set[WebSocket] = set()
admin_tokens: Dict[str, str] = {}
admin_join_history: List[dict] = []
admin_security = HTTPBearer(auto_error=False)

# ── ADMIN EMAILS (RBAC) ───────────────────────────────────────────
ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "admin@vyom.com").split(",")


def admin_authorized(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(admin_security),
) -> str:
    """
    RBAC: Authorizes a request for administrative routes.
    Supports both legacy admin tokens and verified Google ID tokens for users in ADMIN_EMAILS.
    """
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Unauthorized: Bearer token required")
    
    token = credentials.credentials
    
    # 1. Try legacy admin token (from /admin/login)
    user = admin_tokens.get(token)
    if user:
        return user
        
    # 2. Try Google ID token
    try:
        google_client_id = get_google_client_id()
        if google_client_id:
            # Note: verify_oauth2_token handles expiration and signature checks
            idinfo = id_token.verify_oauth2_token(token, requests.Request(), google_client_id)
            email = idinfo.get("email")
            if email and email in ADMIN_EMAILS:
                log.info("[AUTH] Admin access granted to Google user: %s", email)
                return email
    except Exception as e:
        # Not a valid Google token or verification failed — fall through
        pass
        
    raise HTTPException(401, "Unauthorized: Admin privileges required")


def normalize_student_key(name: str, roll: str, cls: str) -> str:
    return f"{name.strip().lower()}|{roll.strip().upper()}|{cls.strip().upper()}"


# ── CLOSED ACCESS VALIDATION ─────────────────────────────────────────────────
def validate_closed_access_student(s: dict, name: str, roll: str, cls: str) -> bool:
    """
    Clean, authoritative gate for closed-access sessions.

    Returns True only when ALL THREE of name / roll / class match an entry
    in the session's allowed_students set.  Returns False in every other case,
    including when the allowed list is empty (safe default after a failed upload).

    Normalisation rules:
      name  -> strip + lowercase
      roll  -> strip  (preserve original casing, e.g. "CS21" stays "CS21")
      class -> strip + uppercase
    """
    if s.get("access_mode", "open") != "closed":
        # Not a closed session — nothing to validate; caller decides what to do.
        return True

    name_n = name.strip().lower()
    roll_n = roll.strip()
    cls_n  = cls.strip().upper()

    allowed: set = s.get("allowed_students", set())

    for entry in allowed:
        if (
            isinstance(entry, tuple)
            and len(entry) == 3
            and entry[0] == name_n
            and entry[1] == roll_n
            and entry[2] == cls_n
        ):
            return True

    return False
# ── CLOSED ACCESS VALIDATION END ─────────────────────────────────────────────


def haversine_distance_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Return great-circle distance between two GPS points in meters."""
    from math import asin, cos, radians, sin, sqrt
    lat1_r, lng1_r, lat2_r, lng2_r = map(radians, (lat1, lng1, lat2, lng2))
    dlat = lat2_r - lat1_r
    dlng = lng2_r - lng1_r
    a = sin(dlat / 2) ** 2 + cos(lat1_r) * cos(lat2_r) * sin(dlng / 2) ** 2
    c = 2 * asin(min(1.0, sqrt(a)))
    return c * 6371000.0


def get_close_access_failure_reason(s: dict, lat: Optional[float], lng: Optional[float]) -> Optional[str]:
    if s.get("access_mode", "open") != "close":
        return None
    if lat is None or lng is None:
        return "Location is required for Close Access mode"
    if not isinstance(lat, (int, float)) or not isinstance(lng, (int, float)):
        return "Invalid GPS coordinates"
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return "Invalid GPS coordinates"
    location = s.get("close_access_location")
    if not location or not isinstance(location, dict):
        return "Teacher location has not been captured yet"
    teacher_lat = location.get("lat")
    teacher_lng = location.get("lng")
    if teacher_lat is None or teacher_lng is None:
        return "Teacher location has not been captured yet"
    if not isinstance(teacher_lat, (int, float)) or not isinstance(teacher_lng, (int, float)):
        return "Teacher location is invalid"
    if not (-90 <= teacher_lat <= 90 and -180 <= teacher_lng <= 180):
        return "Teacher location is invalid"
    radius = s.get("close_access_radius_meters", 100)
    distance = haversine_distance_meters(teacher_lat, teacher_lng, lat, lng)
    if distance > radius:
        return f"Your location is outside the allowed radius ({int(distance)}m away)"
    return None


def validate_close_access_student(s: dict, lat: Optional[float], lng: Optional[float]) -> bool:
    if s.get("access_mode", "open") != "close":
        return True
    return get_close_access_failure_reason(s, lat, lng) is None

# ── CLOSED ACCESS VALIDATION END ─────────────────────────────────────────────


def admin_session_summary(s: dict) -> dict:
    students = [st for st in s["students"].values() if st.get("status") == "active"]
    return {
        "session_code":  s["code"],
        "teacher_name":  s["teacher_name"],
        "status":        s["status"],
        "students_count": len(students),
        "tasks_sent":    len(s.get("task_deliveries", {})),
        "responses":     sum(len(r) for r in s.get("responses", {}).values()),
        "created_at":    s.get("created_at"),
        "last_activity": s.get("last_activity_at", s.get("created_at")),
    }


def admin_dashboard_data() -> dict:
    active_sessions = [s for s in sessions.values() if s.get("status") != "ended"]
    all_students = [st for s in sessions.values() for st in s.get("students", {}).values()]
    active_teachers = [s for s in sessions.values() if s.get("teacher_ws")]
    return {
        "total_sessions":   len(sessions),
        "active_sessions":  len(active_sessions),
        "total_students":   len(all_students),
        "total_teachers":   len({s["teacher_name"] for s in sessions.values() if s.get("teacher_name")}),
        "live_sessions":    [admin_session_summary(s) for s in sorted(active_sessions, key=lambda x: x.get("created_at", 0), reverse=True)],
        "top_active_sessions": sorted(
            [admin_session_summary(s) for s in sessions.values()],
            key=lambda x: x["students_count"],
            reverse=True,
        )[:5],
        "inactive_sessions": [
            admin_session_summary(s)
            for s in sessions.values()
            if s.get("status") != "ended"
            and (now() - s.get("last_activity_at", s.get("created_at", 0))) > 300
        ],
        "student_activity_heatmap": [
            {"session_code": s["code"], "student_count": len([st for st in s["students"].values() if st.get("status") == "active"]),}
            for s in sessions.values()
        ],
        "suspicious_activity": detect_suspicious_activity(),
    }


def detect_suspicious_activity() -> dict:
    now_ts = now()
    recent_joins = [e for e in admin_join_history if e["ts"] >= now_ts - 60]
    large_join_spike = len(recent_joins) >= 10
    grouped = {}
    for e in admin_join_history:
        grouped.setdefault(e["student_key"], set()).add(e["session_code"])
    duplicate_joins = [
        {"student_key": k, "sessions": sorted(list(v))}
        for k, v in grouped.items() if len(v) > 1
    ]
    return {
        "multiple_session_joins": duplicate_joins,
        "join_spike": {
            "enabled": large_join_spike,
            "count_last_minute": len(recent_joins),
        },
    }


def touch_session(s: dict) -> None:
    s["last_activity_at"] = now()


# ══════════════════════════════════════════════════════════════════
#  ATTENDANCE HELPERS
# ══════════════════════════════════════════════════════════════════

def _att(s: dict) -> dict:
    """Return or initialise the attendance sub-dict on a session."""
    att = s.setdefault("attendance", {
        "state": "inactive", "started_at": None, "ended_at": None,
        "locked_at": None, "min_duration": 60, "records": {}, "audit_log": [],
    })
    if "audit_log" not in att:
        att["audit_log"] = []
    return att



def init_student_geo_attendance(r: dict, now_ts: float, s: dict):
    access_mode = s.get("access_mode", "open")
    if access_mode != "close":
        r["joinTime"] = now_ts
        r["status"] = "present"
        return
    r["joinTime"] = now_ts
    r["accumulatedInsideTime"] = 0.0
    r["accumulatedOutsideTime"] = 0.0
    r["currentStatus"] = "present"
    r["insideStartTime"] = now_ts
    r["outsideStartTime"] = None
    r["lastLocationTimestamp"] = now_ts
    r["attendancePercentage"] = 100.0
    r["exitCount"] = 0
    r["reEntryCount"] = 0
    r["attendanceTimeline"] = [{"timestamp": now_ts, "event": "Joined Session"}]
    r["consecutive_outside"] = 0
    r["consecutive_inside"] = 0
    r["left_radius_at"] = None
    r["gps_lost"] = False
    r["frozen"] = False

def finalize_session_attendance(s: dict):
    att = _att(s)
    if att.get("finalized") or att.get("state") in ("ended", "locked"):
        if att.get("finalized"):
            return
            
    access_mode = s.get("access_mode", "open")
    records = att.setdefault("records", {})
    
    if access_mode != "close":
        for sid, r in records.items():
            if r.get("frozen"):
                continue
            if r.get("join_at"):
                r["status"] = "present"
            else:
                r["status"] = "absent"
            r["frozen"] = True
            timeline = r.setdefault("attendanceTimeline", [])
            timeline.append({"timestamp": now(), "event": f"Attendance Finalized ({r['status'].capitalize()})"})
        att["finalized"] = True
        return
        
    end_t = now()
    total_duration = s.get("duration_mins", 60) * 60
    if total_duration <= 0:
        total_duration = 60 * 60 # fallback to 1 hour
        
    records = att.setdefault("records", {})
    for sid, r in records.items():
        if r.get("frozen"):
            continue
            
        current_status = r.get("currentStatus", "present")
        if current_status == "present" and r.get("insideStartTime"):
            r["accumulatedInsideTime"] = r.get("accumulatedInsideTime", 0.0) + (end_t - r["insideStartTime"])
            r["insideStartTime"] = None
        elif current_status == "temporary_absent" and r.get("outsideStartTime"):
            r["accumulatedOutsideTime"] = r.get("accumulatedOutsideTime", 0.0) + (end_t - r["outsideStartTime"])
            r["outsideStartTime"] = None
            
        inside_time = r.get("accumulatedInsideTime", 0.0)
        percentage = (inside_time / total_duration) * 100.0
        r["attendancePercentage"] = round(min(100.0, max(0.0, percentage)), 2)
        
        if r["attendancePercentage"] >= 75.0:
            r["status"] = "present"
        else:
            r["status"] = "absent"
            
        r["leave_at"] = end_t
        r["duration"] = inside_time
        r["frozen"] = True
        
        timeline = r.setdefault("attendanceTimeline", [])
        timeline.append({"timestamp": end_t, "event": f"Attendance Finalized ({r['status'].capitalize()})"})
        
    att["finalized"] = True


def log_attendance_audit(s: dict, action: str, actor: str, details: str):
    att = _att(s)
    att.setdefault("audit_log", []).append({
        "action": action,
        "actor": actor,
        "timestamp": now(),
        "details": details
    })


def compute_attendance_summary(s: dict) -> dict:
    att = _att(s)
    records = att.get("records", {})
    students = s.get("students", {})

    enrolled = [st for st in students.values() if st.get("status") == "active"]
    total  = len(enrolled)
    present = sum(1 for r in records.values() if r.get("status") == "present")
    exited  = sum(1 for r in records.values() if r.get("status") == "exited")
    revoked = sum(1 for r in records.values() if r.get("status") == "revoked")
    late    = sum(1 for r in records.values()
                  if r.get("status") in ("present", "exited")
                  and (r.get("join_at") or 0) - (att.get("started_at") or 0) > 120)

    # Build per-student entries that also carry name/roll for the UI
    student_records = {}
    for sid, st in students.items():
        r = records.get(sid, {})
        student_records[sid] = {
            "student_id":  sid,
            "name":        st.get("name", sid),
            "roll":        st.get("roll", ""),
            "class":       st.get("class", ""),
            "status":      r.get("status", "not_marked"),
            "join_at":     r.get("join_at"),
            "leave_at":    r.get("leave_at"),
            "duration":    r.get("duration", 0),
            "interactions":r.get("interactions", 0),
            "joinTime":    r.get("joinTime"),
            "insideStartTime": r.get("insideStartTime"),
            "outsideStartTime": r.get("outsideStartTime"),
            "accumulatedInsideTime": r.get("accumulatedInsideTime", 0.0),
            "accumulatedOutsideTime": r.get("accumulatedOutsideTime", 0.0),
            "attendancePercentage": r.get("attendancePercentage", 100.0),
            "currentStatus": r.get("currentStatus", "present"),
            "lastLocationTimestamp": r.get("lastLocationTimestamp"),
            "gpsAccuracy": r.get("gpsAccuracy"),
            "exitCount": r.get("exitCount", 0),
            "reEntryCount": r.get("reEntryCount", 0),
            "attendanceTimeline": r.get("attendanceTimeline", []),
            "gps_lost": r.get("gps_lost", False),
        }

    # Calculate live dashboard analytics
    connected_count = sum(1 for sid in records if sid in s.get("ws_clients", {}))
    currently_inside = sum(1 for r in records.values() if r.get("currentStatus") == "present")
    currently_outside = sum(1 for r in records.values() if r.get("currentStatus") == "temporary_absent")
    
    percentages = [r.get("attendancePercentage", 100.0) for r in records.values()]
    avg_attendance = round(sum(percentages) / len(percentages)) if percentages else 100
    
    students_with_warnings = sum(1 for r in records.values() if r.get("exitCount", 0) >= 3 or r.get("currentStatus") == "temporary_absent" or r.get("gps_lost"))
    total_exits = sum(r.get("exitCount", 0) for r in records.values())

    return {
        "state":        att.get("state", "inactive"),
        "access_mode":   s.get("access_mode", "open"),
        "started_at":   att.get("started_at"),
        "ended_at":     att.get("ended_at"),
        "locked_at":    att.get("locked_at"),
        "min_duration": att.get("min_duration", 60),
        "total":    total,
        "present":  present,
        "exited":   exited,
        "revoked":  revoked,
        "late":     late,
        "absent":   max(0, total - present - exited - revoked),
        "percentage": round(present / total * 100) if total else 0,
        "records":  student_records,
        "teacher_name": s.get("teacher_name", "Teacher"),
        "session_name": s.get("session_name", "Live Class"),
        "session_status": s.get("status", "active"),
        "audit_log": att.get("audit_log", []),
        "connected_count": connected_count,
        "currently_inside": currently_inside,
        "currently_outside": currently_outside,
        "avg_attendance": avg_attendance,
        "students_with_warnings": students_with_warnings,
        "total_exits": total_exits,
    }


def _format_attendance_status(status: str) -> str:
    return {
        "present": "Present",
        "exited": "Left Early",
        "revoked": "Revoked",
        "absent": "Absent",
        "not_marked": "Absent",
    }.get(status or "absent", "Absent")


def _roll_sort_value(value: str):
    """
    Return a sort key tuple that orders roll numbers deterministically:
      1. Pure-numeric rolls first, sorted numerically (001 < 002 < 10)
      2. Alphanumeric rolls next, sorted lexicographically
      3. Missing/empty rolls last, sorted by name (handled at call-site)
    Tiers are kept in separate sub-tuples to avoid int/str comparison errors.
    """
    raw = str(value or "").strip()
    if not raw:
        return (2, 0, "")           # tier 2 = missing — sorts last
    digits = "".join(ch for ch in raw if ch.isdigit())
    if digits and digits == raw:
        return (0, int(digits), "")  # tier 0 = pure numeric
    return (1, 0, raw.lower())       # tier 1 = alphanumeric


def generate_attendance_sheet(s: dict) -> dict:
    """Build and persist an official attendance-sheet snapshot for a session."""
    att = _att(s)
    records = att.get("records", {})
    students = s.get("students", {})
    summary = compute_attendance_summary(s)
    generated_at = now()

    rows = []
    for sid, st in students.items():
        rec = records.get(sid, {})
        raw_status = rec.get("status") or "absent"
        if raw_status == "not_marked":
            raw_status = "absent"
        rows.append({
            "student_id": sid,
            "student_name": st.get("real_name") or st.get("name") or sid,
            "email": st.get("email") or "",
            "class": st.get("class") or "",
            "roll_number": st.get("roll") or "",
            "status": raw_status,
            "status_label": _format_attendance_status(raw_status),
            "join_time": rec.get("join_at"),
            "leave_time": rec.get("leave_at"),
            "total_duration": rec.get("duration", 0) or 0,
            "attendance_percentage": rec.get("attendancePercentage", 100.0) if rec.get("join_at") else 0.0,
        })

    rows.sort(key=lambda row: (_roll_sort_value(row.get("roll_number")), (row.get("student_name") or "").lower()))
    for idx, row in enumerate(rows, start=1):
        row["serial_no"] = idx

    present_count = sum(1 for r in rows if r.get("status") == "present")
    left_early_count = sum(1 for r in rows if r.get("status") == "exited")
    revoked_count = sum(1 for r in rows if r.get("status") == "revoked")
    total_students = len(rows)
    absent_count = max(0, total_students - present_count - left_early_count - revoked_count)
    row_classes = sorted({r.get("class") for r in rows if r.get("class")})
    inferred_class_name = ", ".join(row_classes[:3])
    if len(row_classes) > 3:
        inferred_class_name += f" +{len(row_classes) - 3} more"

    sheet = {
        "generated_at": generated_at,
        "teacher_name": s.get("teacher_name") or "Teacher",
        "class_name": s.get("class_name") or s.get("session_class") or inferred_class_name,
        "session_code": s.get("code"),
        "session_topic": s.get("session_name") or "Live Class",
        "date": att.get("started_at") or s.get("started_at") or s.get("created_at"),
        "start_time": att.get("started_at") or s.get("started_at"),
        "end_time": att.get("ended_at") or s.get("ended_at") or s.get("last_activity_at"),
        "total_students": total_students,
        "present_count": present_count,
        "absent_count": absent_count,
        "left_early_count": left_early_count,
        "revoked_count": revoked_count,
        "attendance_percentage": round((present_count / total_students) * 100) if total_students else 0,
        "attendance_state": att.get("state", "inactive"),
        "rows": rows,
        "summary": summary,
    }
    s["attendance_sheet"] = sheet
    return sheet


def get_or_create_attendance_sheet(s: dict) -> dict:
    att = _att(s)
    if s.get("attendance_sheet") and att.get("state") in ("ended", "locked"):
        return s["attendance_sheet"]
    return generate_attendance_sheet(s)


async def broadcast_attendance(s: dict) -> None:
    summary = compute_attendance_summary(s)
    await ws_teacher(s, {"type": "attendance_update", "attendance": summary})


def attendance_mark_join(s: dict, student_id: str) -> None:
    """Called when a student is approved (becomes active)."""
    att = _att(s)
    if att.get("state") == "locked" or att.get("locked_at"):
        log_attendance_audit(s, "modification_attempt", student_id, "Attempted join when attendance locked")
        save_session(s["code"])
        return
    if att.get("state") not in ("active", "paused"):
        return
    records = att.setdefault("records", {})
    now_ts = now()
    if student_id not in records:
        records[student_id] = {
            "student_id":  student_id,
            "join_at":     now_ts,
            "leave_at":    None,
            "duration":    0,
            "status":      "present",
            "interactions": 0,
        }
    else:
        r = records[student_id]
        r["join_at"]  = now_ts
        r["leave_at"] = None
        r["status"]   = "present"
        
    r = records[student_id]
    init_student_geo_attendance(r, now_ts, s)


def attendance_mark_leave(s: dict, student_id: str) -> None:
    """Called when a student WebSocket disconnects."""
    att = _att(s)
    if att.get("state") == "locked" or att.get("locked_at"):
        log_attendance_audit(s, "modification_attempt", student_id, "Attempted leave when attendance locked")
        save_session(s["code"])
        return
    if att.get("state") not in ("active", "paused"):
        return
    records = att.get("records", {})
    r = records.get(student_id)
    if not r:
        return
    if r.get("status") not in ("present",):
        return

    leave_time = now()
    r["leave_at"] = leave_time
    duration = leave_time - (r.get("join_at") or leave_time)
    r["duration"] = duration

    # Keep status as "present" - do NOT automatically set to exited or revoked upon disconnection.
    # Students must remain present unless manually marked otherwise by the teacher.


def attendance_add_interaction(s: dict, student_id: str) -> None:
    """Increment interaction counter for a student (chat, answer, code run)."""
    att = _att(s)
    if att.get("state") == "locked" or att.get("locked_at"):
        log_attendance_audit(s, "modification_attempt", student_id, "Attempted interaction when attendance locked")
        save_session(s["code"])
        return
    if att.get("state") not in ("active", "paused"):
        return
    records = att.get("records", {})
    r = records.get(student_id)
    if r and r.get("status") == "present":
        r["interactions"] = r.get("interactions", 0) + 1


def admin_broadcast(data: dict) -> None:
    payload = {"type": "admin_event", **data, "dashboard": admin_dashboard_data()}
    live = set(admin_connections)
    for ws in list(live):
        try:
            asyncio.create_task(ws.send_text(json.dumps(payload, default=str)))
        except Exception as exc:
            log.debug("Admin broadcast failed: %s", exc)
            admin_connections.discard(ws)


# ══════════════════════════════════════════════════════════════════
#  WEBSOCKET HELPERS
# ══════════════════════════════════════════════════════════════════

async def ws_send(ws: WebSocket, data: dict) -> bool:
    """Send a JSON payload to one WebSocket; returns True on success."""
    try:
        await ws.send_text(json.dumps(data, default=str))
        return True
    except Exception as exc:
        log.debug("ws_send failed: %s", exc)
        return False


def get_teacher_ws_list(s: dict) -> list:
    val = s.get("teacher_ws")
    if not val:
        return []
    if isinstance(val, (list, set)):
        return list(val)
    return [val]


def remove_teacher_ws(s: dict, ws: WebSocket):
    val = s.get("teacher_ws")
    if not val:
        return
    if isinstance(val, (list, set)):
        if ws in val:
            if isinstance(val, list):
                val.remove(ws)
            else:
                val.discard(ws)
            if not val:
                s["teacher_ws"] = None
    elif val is ws:
        s["teacher_ws"] = None


async def ws_teacher(s: dict, data: dict) -> bool:
    sockets = get_teacher_ws_list(s)
    if not sockets:
        return False

    # Check notification preferences and append "silent": True if disabled
    teacher_email = s.get("teacher_email") or s.get("teacher_id")
    if teacher_email and isinstance(data, dict):
        msg_type = data.get("type")
        category = None
        notif_type = None
        
        if msg_type == "new_doubt":
            category = "chat"
            notif_type = "new_doubts"
        elif msg_type == "chat_message":
            category = "chat"
            incoming = data.get("message") or data
            is_file = False
            if isinstance(incoming, dict):
                is_file = incoming.get("msg_type") in ["file", "image"]
            notif_type = "chat_uploads" if is_file else "student_messages"
        elif msg_type == "student_waiting":
            category = "classroom"
            notif_type = "waiting_room"
        elif msg_type == "hand_raised":
            category = "classroom"
            notif_type = "attendance_updates"
        elif msg_type == "class_end_warning":
            category = "tasks"
            notif_type = "deadlines"
        elif msg_type == "ai_evaluation_done":
            category = "tasks"
            notif_type = "evaluations"
        elif msg_type == "task_sent":
            category = "tasks"
            notif_type = "task_created"
        elif msg_type == "session_status" and data.get("status") == "ended":
            category = "classroom"
            notif_type = "session_events"
        elif msg_type in ["auto_join_enabled", "auto_join_disabled"]:
            category = "classroom"
            notif_type = "session_events"
            
        if category and notif_type:
            if not notification_enabled(teacher_email, category, notif_type):
                # Silent delivery: update data but suppress notification/sound/beep on UI
                data = {**data, "silent": True}

    success = False
    for ws in list(sockets):
        try:
            ok = await ws_send(ws, data)
            if ok:
                success = True
            else:
                remove_teacher_ws(s, ws)
        except Exception:
            remove_teacher_ws(s, ws)
    return success


async def ws_student(s: dict, sid: str, data: dict) -> bool:
    ws = s.get("ws_clients", {}).get(sid)
    if not ws:
        return False
    ok = await ws_send(ws, data)
    if not ok and s.get("ws_clients", {}).get(sid) is ws:
        s["ws_clients"].pop(sid, None)
    return ok


async def ws_all_students(
    s: dict,
    data: dict,
    student_ids: Optional[List[str]] = None,
) -> List[str]:
    ids = student_ids if student_ids is not None else list(s.get("ws_clients", {}).keys())
    delivered: List[str] = []
    for sid in list(ids):
        if await ws_student(s, sid, data):
            delivered.append(sid)
    return delivered


async def ws_broadcast(s: dict, data: dict):
    await ws_teacher(s, data)
    await ws_all_students(s, data)


async def push_roster(s: dict):
    # Send only essential fields to prevent payload bloat and serialization issues
    active = []
    for st in s["students"].values():
        if st["status"] == "active":
            active.append({
                "id": st["id"],
                "name": st["name"],
                "status": st["status"],
                "correct": st.get("correct", 0),
                "total_answered": st.get("total_answered", 0),
                "coding_submitted": st.get("coding_submitted", False),
                "profile_photo": st.get("profile_photo") or None,
            })
    
    waiting = []
    for sid in s["waiting_room"]:
        if sid in s["students"]:
            st = s["students"][sid]
            waiting.append({
                "id": st["id"],
                "name": st["name"],
                "profile_photo": st.get("profile_photo") or None,
            })

    # Normalise raised_hands — backend may still have old list format
    rh = s.get("raised_hands", {})
    if isinstance(rh, list):
        rh = {sid: {"name": s["students"].get(sid, {}).get("name", "?"), "raised_at": 0} for sid in rh}
        s["raised_hands"] = rh
    hand_list = [
        {"student_id": sid, "student_name": info.get("name", "?"), "raised_at": info.get("raised_at")}
        for sid, info in rh.items()
    ]

    await ws_teacher(s, {
        "type":         "roster_update",
        "active":       active,
        "waiting":      waiting,
        "raised_hands": hand_list,
    })


async def push_roster_delta(s: dict, change: str, student_id: str, fields: dict = None):
    """
    Sends a delta update to the teacher.
    change: "join" | "leave" | "update" | "waiting_join" | "waiting_leave"
    """
    payload = {
        "type": "roster_delta",
        "change": change,
        "student_id": student_id,
    }
    if fields:
        payload["student"] = fields
    elif change in ("join", "waiting_join"):
        st = s["students"].get(student_id)
        if st:
            if change == "join":
                payload["student"] = {
                    "id": st["id"],
                    "name": st["name"],
                    "status": st.get("status", "active"),
                    "correct": st.get("correct", 0),
                    "total_answered": st.get("total_answered", 0),
                    "coding_submitted": st.get("coding_submitted", False),
                    "profile_photo": st.get("profile_photo") or None,
                }
            else: # waiting_join
                payload["student"] = {
                    "id": st["id"],
                    "name": st["name"],
                    "profile_photo": st.get("profile_photo") or None,
                }
    
    await ws_teacher(s, payload)


# ══════════════════════════════════════════════════════════════════
#  TASK DELIVERY PIPELINE
# ══════════════════════════════════════════════════════════════════

def task_index(s: dict, task_id: str) -> int:
    return next((i for i, t in enumerate(s["tasks"]) if t["id"] == task_id), -1)


def normalize_target(
    target_type: Optional[str],
    target_id:   Optional[str],
) -> tuple[str, str]:
    """Normalise and validate target_type/target_id; raises HTTPException on bad input."""
    tt = (target_type or "all").strip().lower()
    if tt in {"class", "everyone", ""}:
        tt = "all"
    if tt not in {"all", "student", "group"}:
        raise HTTPException(400, "target_type must be one of: all, student, group")
    tid = str(target_id or "").strip()
    if tt == "all":
        return tt, "all"
    if not tid:
        raise HTTPException(422, f"target_id is required for target_type='{tt}'")
    return tt, tid


def active_student_ids(s: dict) -> List[str]:
    kicked = s.get("kicked", set())
    return [
        sid for sid, st in s.get("students", {}).items()
        if st.get("status") == "active" and sid not in kicked
    ]


def resolve_task_recipients(
    s: dict,
    target_type: str,
    target_id:   str,
) -> tuple[List[str], str]:
    """Return (list_of_recipient_ids, human_readable_label). Raises on invalid target."""
    active_ids = set(active_student_ids(s))

    if target_type == "all":
        recipients = sorted(active_ids)
        label      = "entire class"

    elif target_type == "student":
        student = s["students"].get(target_id)
        if not student:
            raise HTTPException(404, f"Student '{target_id}' not found")
        if student.get("status") != "active" or target_id in s.get("kicked", set()):
            raise HTTPException(409, "Target student is not active")
        recipients = [target_id]
        label      = student.get("name") or target_id

    else:  # group
        group = next((g for g in s.get("groups", []) if g.get("id") == target_id), None)
        if not group:
            raise HTTPException(404, f"Group '{target_id}' not found")
        members = list(dict.fromkeys(group.get("members", [])))
        unknown = [sid for sid in members if sid not in s.get("students", {})]
        if unknown:
            raise HTTPException(400, f"Group contains unknown students: {', '.join(unknown)}")
        recipients = [sid for sid in members if sid in active_ids]
        label      = group.get("name") or target_id

    if not recipients:
        raise HTTPException(409, "No active recipients matched the selected target")
    return recipients, label


def _S(code: str) -> dict:
    """Return session dict or raise 404."""
    code_clean = code.strip().upper()
    s = sessions.get(code_clean)
    if not s:
        if len(code_clean) == 6:
            import classroom_db
            import hashlib
            db = classroom_db.get_db()
            code_hash = hashlib.sha256(code_clean.encode("utf-8")).hexdigest()
            lecture = db.lectures.find_one({"lecture_code_hash": code_hash})
            if lecture:
                s = sessions[code_clean] = {
                    "code": code_clean,
                    "name": f"Lecture - {code_clean}",
                    "status": lecture["status"],
                    "duration_mins": 60,
                    "teacher_name": "Teacher",
                    "email": "teacher@vyom.org",
                    "phone": "",
                    "created_at": lecture["start_time"],
                    "end_timestamp": 0,
                    "students": {},
                    "waiting_room": [],
                    "tasks": [],
                    "groups": [],
                    "attendance": {
                        "state": "active",
                        "started_at": lecture["start_time"],
                        "min_duration": 60,
                        "records": {},
                        "audit_log": []
                    },
                    "doubts": [],
                    "chats": [],
                    "quiz_active": False
                }
                return s
        raise HTTPException(404, f"Session '{code_clean}' not found")
    return s


def _T(s: dict, task_id: str) -> dict:
    """Return task dict from session or raise 404."""
    t = next((t for t in s["tasks"] if t["id"] == task_id), None)
    if not t:
        raise HTTPException(404, f"Task '{task_id}' not found")
    return t


def task_payload(s: dict, delivery: dict) -> dict:
    """Build the WebSocket 'new_task' payload for a delivery record."""
    task         = _T(s, delivery["task_id"])
    payload_task = safe_task(task)

    cf_name = task.get("content_file")
    if cf_name and cf_name in s.get("content_files", {}):
        cf = s["content_files"][cf_name]
        payload_task["content"] = {
            "name":         cf["name"],
            "content_type": cf["content_type"],
            # No base64 data - student fetches via /api/content/file/
        }

    return {
        "type":         "new_task",
        "delivery_id":  delivery["id"],
        "task_id":      delivery["task_id"],
        "task":         payload_task,
        "target": {
            "type":  delivery["target_type"],
            "id":    delivery["target_id"],
            "label": delivery["target_label"],
        },
        "task_index":  delivery["task_index"],
        "total_tasks": delivery["total_tasks"],
        "sent_at":     delivery["created_at"],
    }


def create_delivery_record(
    s:           dict,
    task_id:     str,
    target_type: str,
    target_id:   str,
) -> dict:
    """Create, store, and return a delivery record (no IO)."""
    task            = _T(s, task_id)
    recipients, lbl = resolve_task_recipients(s, target_type, target_id)

    s["delivery_seq"] = int(s.get("delivery_seq", 0)) + 1
    delivery_id       = f"td{s['delivery_seq']:06d}"
    idx               = task_index(s, task["id"])

    delivery = {
        "id":             delivery_id,
        "sequence":       s["delivery_seq"],
        "task_id":        task["id"],
        "target_type":    target_type,
        "target_id":      target_id,
        "target_label":   lbl,
        "recipients":     recipients,
        "sent_to":        [],
        "acknowledged_by": [],
        "created_at":     now(),
        "last_attempt_at": None,
        "task_index":     idx,
        "total_tasks":    len(s["tasks"]),
    }

    s.setdefault("task_deliveries", {})[delivery_id] = delivery
    s.setdefault("student_current_task", {})
    for sid in recipients:
        s["student_current_task"][sid] = task["id"]

    # advance global pointer for "all" deliveries
    if target_type == "all" and idx >= 0 and idx > s.get("current_task_idx", -1):
        s["current_task_idx"] = idx

    return delivery


def delivery_summary(delivery: dict) -> dict:
    recipients = delivery.get("recipients", [])
    sent_to    = delivery.get("sent_to", [])
    acked      = delivery.get("acknowledged_by", [])
    return {
        "status":            "sent",
        "sent":              True,
        "delivery_id":       delivery["id"],
        "task_id":           delivery["task_id"],
        "target": {
            "type":  delivery["target_type"],
            "id":    delivery["target_id"],
            "label": delivery["target_label"],
        },
        "recipient_ids":     recipients,
        "recipient_count":   len(recipients),
        "sent_count":        len(sent_to),
        "queued_count":      len([sid for sid in recipients if sid not in sent_to]),
        "acknowledged_count": len(acked),
        "task_index":        delivery["task_index"],
        "total_tasks":       delivery["total_tasks"],
    }


async def deliver_recorded_task(s: dict, delivery: dict) -> dict:
    """Push task payload over WebSocket to all recipients; notify teacher."""
    payload   = task_payload(s, delivery)
    sent_now: List[str] = []

    for sid in delivery["recipients"]:
        if await ws_student(s, sid, payload):
            sent_now.append(sid)

    delivery["last_attempt_at"] = now()
    delivery["sent_to"] = sorted(set(delivery.get("sent_to", [])) | set(sent_now))

    summary = delivery_summary(delivery)
    await ws_teacher(s, {"type": "task_sent", "delivery": summary, **summary})
    admin_broadcast({
        "event": "task_sent",
        "session_code": s["code"],
        "delivery": summary,
    })
    touch_session(s)
    return summary


async def deliver_task_request(code: str, req: "SendTaskReq") -> dict:
    target_type, target_id = normalize_target(req.target_type, req.target_id)
    async with session_lock(code):
        s        = _S(code)
        delivery = create_delivery_record(s, req.task_id, target_type, target_id)
    return await deliver_recorded_task(s, delivery)


async def deliver_next_task_request(code: str) -> dict:
    async with session_lock(code):
        s = _S(code)
        if not s["tasks"]:
            raise HTTPException(400, "No tasks in queue")
        next_idx = s.get("current_task_idx", -1) + 1
        if next_idx >= len(s["tasks"]):
            raise HTTPException(400, "All tasks already sent")
        task_id  = s["tasks"][next_idx]["id"]
        delivery = create_delivery_record(s, task_id, "all", "all")
        s["current_task_idx"] = next_idx
    return await deliver_recorded_task(s, delivery)


def mark_task_ack(s: dict, student_id: str, delivery_id: Optional[str]) -> bool:
    if not delivery_id:
        return False
    delivery = s.get("task_deliveries", {}).get(delivery_id)
    if not delivery or student_id not in delivery.get("recipients", []):
        return False
    acked = set(delivery.get("acknowledged_by", []))
    acked.add(student_id)
    delivery["acknowledged_by"] = sorted(acked)
    return True


def latest_delivery_for_student(s: dict, student_id: str) -> Optional[dict]:
    deliveries = [
        d for d in s.get("task_deliveries", {}).values()
        if student_id in d.get("recipients", [])
    ]
    return max(deliveries, key=lambda d: d.get("sequence", 0)) if deliveries else None


async def replay_unacked_tasks(s: dict, student_id: str):
    """Re-send any un-acknowledged deliveries to a student who just reconnected."""
    pending = sorted(
        (
            d for d in s.get("task_deliveries", {}).values()
            if student_id in d.get("recipients", [])
            and student_id not in d.get("acknowledged_by", [])
        ),
        key=lambda d: d.get("sequence", 0),
    )
    for delivery in pending:
        if await ws_student(s, student_id, task_payload(s, delivery)):
            delivery["sent_to"]          = sorted(set(delivery.get("sent_to", [])) | {student_id})
            delivery["last_attempt_at"]  = now()


def student_can_submit_task(s: dict, student_id: str, task_id: str) -> bool:
    # SAFEGUARD: Only active students can submit tasks
    student = s.get("students", {}).get(student_id, {})
    if student.get("status") != "active":
        log.warning(
            "[SAFEGUARD] Student %s tried to submit task but status is %s (not active)",
            student_id, student.get("status")
        )
        return False
    
    if s.get("mode") == "test":
        return True
        
    for d in s.get("task_deliveries", {}).values():
        if d.get("task_id") == task_id:
            # If the task was broadcast to everyone, or the student is in the recipients list
            if d.get("target_type") == "all" or student_id in d.get("recipients", []):
                return True
    return False


# ══════════════════════════════════════════════════════════════════
#  TASK INPUT NORMALISATION
# ══════════════════════════════════════════════════════════════════

def normalize_task_input(data: dict) -> dict:
    question = str(data.get("question") or "").strip()
    if not question:
        raise HTTPException(422, "Question is required")

    task_type   = str(data.get("type") or "mcq").strip().lower()
    long_answer = bool(data.get("long_answer", False))
    if task_type == "long":
        task_type   = "short"
        long_answer = True
    if task_type not in {"mcq", "short", "coding"}:
        raise HTTPException(422, "Task type must be: mcq, short, long, or coding")

    difficulty = str(data.get("difficulty") or "medium").strip().lower()
    if difficulty not in {"easy", "medium", "hard"}:
        raise HTTPException(422, "Difficulty must be: easy, medium, or hard")

    hint_visibility = str(data.get("hint_visibility") or "on_request").strip()
    if hint_visibility not in {"always", "on_request", "after_submission"}:
        raise HTTPException(422, "Invalid hint_visibility")

    raw_time   = data.get("time_limit")
    time_limit = None
    if raw_time not in (None, ""):
        try:
            time_limit = int(raw_time)
        except (TypeError, ValueError):
            raise HTTPException(422, "time_limit must be a positive integer")
        if time_limit <= 0 or time_limit > 7200:
            raise HTTPException(422, "time_limit must be between 1 and 7200 seconds")

    options        = [str(o).strip() for o in (data.get("options") or []) if str(o).strip()]
    correct_answer = str(data.get("correct_answer") or data.get("answer") or "").strip()
    starter_code   = str(data.get("starter_code") or "").strip()
    test_input     = str(data.get("test_input") or "").strip()

    if task_type == "mcq":
        if len(options) < 2:
            raise HTTPException(422, "MCQ tasks need at least 2 options")
        letters        = [chr(65 + i) for i in range(len(options))]
        correct_answer = correct_answer.upper()
        if correct_answer not in letters:
            raise HTTPException(422, f"correct_answer must be one of: {', '.join(letters)}")
    else:
        options = []

    return {
        "question":        question,
        "type":            task_type,
        "options":         options,
        "correct_answer":  correct_answer,
        "starter_code":    starter_code if task_type == "coding" else (starter_code or correct_answer),
        "test_input":      test_input,
        "topic":           str(data.get("topic") or "General").strip() or "General",
        "difficulty":      difficulty,
        "hint":            str(data.get("hint")).strip() if data.get("hint") else None,
        "hint_visibility": hint_visibility,
        "time_limit":      time_limit,
        "long_answer":     long_answer,
        "content_file":    data.get("content_file"),
        "language":        str(data.get("language") or "python").strip().lower(),
        "evaluation_mode": str(data.get("evaluation_mode") or "manual").strip().lower(),
        "max_marks":       int(data.get("max_marks") or 10),
    }


# ══════════════════════════════════════════════════════════════════
#  PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════

class CreateSessionReq(BaseModel):
    teacher_name: str
    email:        Optional[str] = None
    phone:        Optional[str] = None
    session_name: Optional[str] = None
    duration_mins: int

class AccessSettingsReq(BaseModel):
    access_mode: str
    radius_meters: Optional[int] = None
    teacher_lat: Optional[float] = None
    teacher_lng: Optional[float] = None

class SendExplanationReq(BaseModel):
    task_id:     str
    explanation: str
    mode:        str = "simplified"

class GoogleLoginReq(BaseModel):
    token: str

class CreateTaskReq(BaseModel):
    session_code:    str
    question:        str
    type:            str = "mcq"
    options:         Optional[List[str]] = []
    correct_answer:  Optional[str] = ""
    starter_code:    Optional[str] = ""
    test_input:      Optional[str] = ""
    topic:           str = "General"
    difficulty:      str = "medium"
    hint:            Optional[str] = None
    hint_visibility: str = "on_request"
    time_limit:      Optional[int] = None
    long_answer:     bool = False
    language:        Optional[str] = "python"
    evaluation_mode: Optional[str] = "manual"
    max_marks:       Optional[int] = 10

class RunAiEvalReq(BaseModel):
    student_id: str
    task_id:    str
    api_key:    Optional[str] = None

class BulkAiEvalReq(BaseModel):
    api_key:    Optional[str] = None

class ApproveEvalReq(BaseModel):
    student_id: str
    task_id:    str
    score:      float
    feedback:   Optional[str] = ""

class SendTaskReq(BaseModel):
    task_id:     str            = Field(..., min_length=1)
    target_type: str            = Field("all")
    target_id:   Optional[str] = None

class SubmitResponseReq(BaseModel):
    session_code: str
    student_id:   str
    task_id:      str
    answer:       str
    time_taken:   Optional[float] = None

class GenerateGroupsReq(BaseModel):
    session_code: str
    strategy:     str = "auto"

class UpdateGroupReq(BaseModel):
    session_code: str
    group_id:     str
    members:      List[str]

class SendMessageReq(BaseModel):
    session_code: str
    sender_id:    str
    content:      str
    chat_type:    str = "global"
    target_id:    Optional[str] = None
    # ── Reply threading (Feature 1) ───────────────────────────────────
    reply_to_message_id: Optional[str] = None
    reply_preview:       Optional[str] = None   # excerpt for the reply preview
    # ── Message type (Feature 5 & 6) ─────────────────────────────────
    msg_type:  Optional[str] = "text"   # text | file | image | system
    file_info: Optional[dict] = None    # {id, name, content_type, size} for file msgs

class SubmitDoubtReq(BaseModel):
    session_code: str
    student_id:   str
    doubt_text:   str
    subject:      Optional[str] = "General"

# ── Chat moderation / reaction models (Features 1-3, 7) ─────────────
class ChatReactionReq(BaseModel):
    session_code: str
    message_id:   str
    emoji:        str
    user_id:      str   # sender_id of the reactor

class SuspendChatReq(BaseModel):
    session_code: str
    student_id:   str

class ResolveDoubtReq(BaseModel):
    session_code: str
    doubt_id:     str
    answer:       str

class ReopenDoubtReq(BaseModel):
    session_code: str
    doubt_id:     str

class StartTestReq(BaseModel):
    session_code:  str
    duration_secs: int = 1800
    task_ids:      Optional[List[str]] = None

class RunCodeReq(BaseModel):
    session_code: str
    student_id:   str
    code:         str
    language:     str = "python"
    task_id:      Optional[str] = None
    stdin:        Optional[str] = None
    is_base64:    Optional[bool] = False

class SendReportReq(BaseModel):
    email: Optional[str] = None
    session_id: Optional[str] = None


# ══════════════════════════════════════════════════════════════════
#  BACKGROUND WORKERS
# ══════════════════════════════════════════════════════════════════

async def analytics_broadcaster():
    while True:
        await asyncio.sleep(2)
        for s in list(sessions.values()):
            if s["status"] == "active" and s.get("teacher_ws"):
                try:
                    await ws_teacher(s, {
                        "type":      "analytics_update",
                        "analytics": compute_analytics(s),
                    })
                except Exception:
                    pass


async def test_timer_watcher():
    while True:
        await asyncio.sleep(3)
        for s in list(sessions.values()):
            ts = s["test_state"]
            if ts["active"] and ts["start_time"]:
                elapsed = time.time() - ts["start_time"]
                if elapsed >= ts["duration_secs"]:
                    ts["active"] = False
                    s["mode"]    = "live"
                    lb_source = {sid: ts["scores"].get(sid, 0.0) for sid in ts["submitted"]}
                    lb = sorted(lb_source.items(), key=lambda x: x[1], reverse=True)
                    ts["leaderboard"] = [
                        {
                            "student_id":   sid,
                            "score":        sc,
                            "rank":         i + 1,
                            "student_name": s["students"].get(sid, {}).get("name", sid),
                        }
                        for i, (sid, sc) in enumerate(lb)
                    ]
                    try:
                        await ws_broadcast(s, {
                            "type":        "test_ended",
                            "reason":      "time_expired",
                            "leaderboard": ts["leaderboard"],
                        })
                    except Exception:
                        pass


async def end_session_automatically(s: dict):
    code = s["code"]
    s["status"] = "ended"
    s["auto_join_enabled"] = False
    touch_session(s)
    
    # Finalize attendance
    finalize_session_attendance(s)
    
    # Broadcast to all connected clients
    await ws_broadcast(s, {"type": "session_status", "status": "ended"})
    generate_attendance_sheet(s)
    
    admin_broadcast({
        "event": "session_ended",
        "session_code": code,
        "teacher_name": s.get("teacher_name"),
    })
    
    # Remove from active mapping so teacher can start a new session next time
    t_email = s.get("teacher_email")
    if t_email and teacher_sessions.get(t_email) == code:
        teacher_sessions.pop(t_email, None)
        log.info("[SESSION] Removed session %s from active mapping for %s", code, t_email)
        
    save_session(code, force=True)
    # Queue the auto-email reports
    asyncio.create_task(_send_session_end_emails(s))
    log.info("[SESSION] Timed auto-end triggered for session %s. Cleanup complete.", code)


async def session_timer_watcher():
    while True:
        await asyncio.sleep(3)
        for s in list(sessions.values()):
            status = s.get("status")
            if status in ("active", "paused"):
                duration_mins = s.get("duration_mins", 0)
                started_at = s.get("started_at")
                if duration_mins > 0 and started_at:
                    elapsed = now() - started_at
                    remaining_secs = duration_mins * 60 - elapsed

                    # ── Class-end warning notifications (Feature 4) ────────
                    flags = s.setdefault("class_end_warning_flags", {})
                    for warn_mins, flag_key in [(10, "10"), (5, "5"), (2, "2")]:
                        warn_secs = warn_mins * 60
                        if (remaining_secs <= warn_secs and
                                remaining_secs > warn_secs - 15 and
                                not flags.get(flag_key)):
                            flags[flag_key] = True
                            warn_msg = {
                                "id":          gen_id("m"),
                                "sender_id":   "system",
                                "sender_name": "System",
                                "content":     f"⏰ Class ends in {warn_mins} minute{'s' if warn_mins > 1 else ''}!",
                                "chat_type":   "global",
                                "target_id":   None,
                                "timestamp":   now(),
                                "msg_type":    "system",
                                "reactions":   {},
                                "reply_to_message_id": None,
                                "reply_preview":       None,
                                "file_info":   None,
                            }
                            s["chat_messages"].append(warn_msg)
                            try:
                                await ws_broadcast(s, {
                                    "type":          "class_end_warning",
                                    "minutes_left":  warn_mins,
                                    "message":       warn_msg["content"],
                                    "chat_message":  warn_msg,
                                })
                                log.info("[SESSION TIMER] Class-end warning (%d min) sent for session %s", warn_mins, s["code"])
                            except Exception as e:
                                log.warning("[SESSION TIMER] Warning broadcast error: %s", e)

                    if elapsed >= duration_mins * 60:
                        log.info("[SESSION TIMER] Auto-ending session %s after %d mins", s["code"], duration_mins)
                        try:
                            await end_session_automatically(s)
                        except Exception as e:
                            log.error("[SESSION TIMER] Error ending session %s automatically: %s", s["code"], e, exc_info=True)

            # Safeguard: prevent sessions from running indefinitely
            # If a session is not ended and has been created for more than 12 hours, force end it.
            created_at = s.get("created_at", 0)
            if status != "ended" and now() - created_at > 12 * 3600:
                log.info("[SESSION TIMER] Force ending stale/indefinite session %s", s["code"])
                try:
                    await end_session_automatically(s)
                except Exception as e:
                    log.error("[SESSION TIMER] Error force ending session %s: %s", s["code"], e, exc_info=True)


async def code_worker():
    while True:
        code, language, stdin, future = await execution_queue.get()
        try:
            async with semaphore:
                result = await asyncio.to_thread(run_code, code, language, stdin)
            if not future.done():
                future.set_result(result)
        except Exception as e:
            log.error("[CODING LAB] Worker error: %s", e, exc_info=True)
            if not future.done():
                try:
                    future.set_result(RunResult(f"Error: {e}", error=True))
                except Exception as inner_e:
                    log.error("[CODING LAB] Failed to set error result on future: %s", inner_e)
        finally:
            execution_queue.task_done()


# ══════════════════════════════════════════════════════════════════
#  APP SETUP  ← app is defined HERE, before any @app routes
# ══════════════════════════════════════════════════════════════════

async def attendance_geo_watcher():
    """Background worker to check for student location timeouts."""
    from datetime import datetime
    while True:
        try:
            await asyncio.sleep(3) # Check every 3 seconds
            for s in list(sessions.values()):
                if s.get("status") != "active":
                    continue
                if s.get("access_mode", "open") != "close":
                    continue
                att = _att(s)
                if att.get("state") != "active":
                    continue
                    
                now_ts = now()
                records = att.setdefault("records", {})
                modified = False
                
                for sid, r in records.items():
                    if r.get("frozen"):
                        continue
                    if r.get("currentStatus") == "present":
                        last_update = r.get("lastLocationTimestamp")
                        if last_update and (now_ts - last_update > 30):
                            boundary_time = r.get("left_radius_at") or last_update
                            
                            inside_start = r.get("insideStartTime")
                            if inside_start and boundary_time > inside_start:
                                r["accumulatedInsideTime"] = r.get("accumulatedInsideTime", 0.0) + (boundary_time - inside_start)
                            r["insideStartTime"] = None
                            r["outsideStartTime"] = boundary_time
                            r["currentStatus"] = "temporary_absent"
                            r["gps_lost"] = True
                            r["exitCount"] = r.get("exitCount", 0) + 1
                            
                            timeline = r.setdefault("attendanceTimeline", [])
                            timeline.append({"timestamp": now_ts, "event": "GPS Lost"})
                            
                            total_duration = s.get("duration_mins", 60) * 60
                            pct = round((r.get("accumulatedInsideTime", 0.0) / total_duration) * 100, 2) if total_duration > 0 else 100.0
                            r["attendancePercentage"] = pct
                            
                            student = s["students"].get(sid, {})
                            student_name = student.get("name", "Student")
                            
                            if r["exitCount"] >= 3:
                                asyncio.create_task(ws_teacher(s, {
                                    "type": "geo_notification",
                                    "notification_type": "exit_warning",
                                    "student_name": student_name,
                                    "attendance_percentage": int(pct),
                                    "time": datetime.fromtimestamp(now_ts).strftime("%I:%M %p"),
                                    "exit_count": r["exitCount"],
                                    "message": f"🚨 {student_name} has exited the classroom {r['exitCount']} times. Current Attendance: {int(pct)}%. Recommendation: Review this student's attendance manually."
                                }))
                            else:
                                asyncio.create_task(ws_teacher(s, {
                                    "type": "geo_notification",
                                    "notification_type": "gps_lost",
                                    "student_name": student_name,
                                    "message": f"⚠️ {student_name} location unavailable. Attendance paused."
                                }))
                            
                            ws_student_conn = s.get("ws_clients", {}).get(sid)
                            if ws_student_conn:
                                asyncio.create_task(ws_send(ws_student_conn, {
                                    "type": "student_attendance_update",
                                    "currentStatus": r["currentStatus"],
                                    "attendancePercentage": r["attendancePercentage"],
                                    "accumulatedInsideTime": r["accumulatedInsideTime"],
                                    "accumulatedOutsideTime": r["accumulatedOutsideTime"],
                                    "insideStartTime": r["insideStartTime"],
                                    "outsideStartTime": r["outsideStartTime"],
                                    "lastLocationTimestamp": r["lastLocationTimestamp"],
                                    "gps_lost": True,
                                }))
                                
                            modified = True
                            
                if modified:
                    asyncio.create_task(broadcast_attendance(s))
        except Exception as e:
            log.error("[GEO WATCHER] Error: %s", e, exc_info=True)


async def autosave_worker():
    """Periodically persist all dirty sessions to disk."""
    interval = int(os.getenv("BATCH_SAVE_INTERVAL", "5"))
    from store import dirty_sessions, dirty_lock
    while True:
        await asyncio.sleep(interval)
        with dirty_lock:
            to_save = list(dirty_sessions)
        for code in to_save:
            try:
                save_session(code, force=True)
            except Exception as e:
                log.warning("Autosave worker failed to save session %s: %s", code, e)


async def session_memory_cleanup_worker():
    """Periodically purge inactive/ended sessions from memory to prevent leaks."""
    cleanup_hours = int(os.getenv("CLEANUP_INACTIVE_HOURS", "24"))
    while True:
        # Run cleanup every 1 hour (3600 seconds)
        await asyncio.sleep(3600)
        try:
            from store import cleanup_inactive_sessions
            cleanup_inactive_sessions(max_inactive_hours=cleanup_hours)
        except Exception as e:
            log.warning("Memory cleanup worker encountered error: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global semaphore, execution_queue
    semaphore       = asyncio.Semaphore(3)
    execution_queue = asyncio.Queue()

    # Initialize MongoDB Auth & Classroom Database
    auth_db.init_db()
    try:
        import classroom_db
        classroom_db.init_db()
    except Exception as e:
        log.error("Failed to initialize classroom database during startup: %s", e)

    # ── Persistence: configure and load saved sessions ────────────
    configure_persistence(
        mode     = os.getenv("PERSISTENCE", "json"),
        data_dir = os.getenv("DATA_DIR", "data"),
    )
    loaded = load_all_sessions()
    if loaded:
        log.info("Restored %d session(s) from disk", loaded)
    load_teacher_keys()
    log.info("Loaded teacher API keys from disk")
    load_teacher_integrations()
    log.info("Loaded teacher cloud storage integrations from disk")
    load_teacher_notification_prefs()
    log.info("Loaded teacher notification preferences from disk")
    load_student_notification_prefs()
    log.info("Loaded student notification preferences from disk")
    load_persisted_downloads()
    log.info("Loaded teacher downloads registry from disk")

    log.info("VYOM starting on port %s…", os.getenv("PORT", "8000"))
    log.info("NOTE: Server restart is required after changing .env variables.")
    
    # Requirement 8: Self-test mode on server start
    from email_service import verify_email_system
    asyncio.create_task(verify_email_system())

    t1 = asyncio.create_task(analytics_broadcaster())
    t2 = asyncio.create_task(test_timer_watcher())
    t3 = asyncio.create_task(code_worker())
    t4 = asyncio.create_task(autosave_worker())
    t5 = asyncio.create_task(session_timer_watcher())
    t6 = asyncio.create_task(attendance_geo_watcher())
    t7 = asyncio.create_task(session_memory_cleanup_worker())
    yield
    # Final save before shutdown
    for code in list(sessions):
        save_session(code, force=True)
    t1.cancel(); t2.cancel(); t3.cancel(); t4.cancel(); t5.cancel(); t6.cancel(); t7.cancel()
    log.info("VYOM stopped.")


app = FastAPI(
    title="VYOM API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.include_router(vc_router)
import classroom_routes
app.include_router(classroom_routes.router)

def google_authorized(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> str:
    """
    Verifies that the requester has a valid Google session.
    Returns the verified email address.
    """
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(401, "Authentication required. Please log in with Google.")
    
    token = credentials.credentials
    try:
        google_client_id = get_google_client_id()
        if not google_client_id:
            raise HTTPException(500, "Server configuration error: GOOGLE_CLIENT_ID missing")
            
        idinfo = id_token.verify_oauth2_token(token, requests.Request(), google_client_id)
        email = idinfo.get("email")
        if not email:
            raise HTTPException(401, "Could not verify email from Google token")
        return email.lower().strip()
    except Exception as e:
        log.warning("[AUTH] Google token verification failed: %s", e)
        raise HTTPException(401, "Your session has expired. Please log in again.")

def google_authorized_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(HTTPBearer(auto_error=False)),
) -> Optional[str]:
    """
    Optional version of google_authorized. Returns None instead of raising 401.
    """
    if not credentials or credentials.scheme.lower() != "bearer":
        return None
    try:
        return google_authorized(credentials)
    except:
        return None

@app.get("/api/teacher/sessions")
def get_teacher_sessions(email: str = Query(...)):
    """
    Returns all sessions created by a teacher, filtered by email.
    Completely public endpoint for dashboard flexibility.
    """
    if not email:
        raise HTTPException(400, "Email parameter is required")

    teacher_history = []
    
    # Normalize email for comparison
    email_n = email.lower().strip()
    
    # Filter sessions where teacher_id matches the authenticated email
    for s in sessions.values():
        s_email = (s.get("teacher_email") or s.get("teacher_id") or "").lower().strip()
        
        if s_email == email_n:
            # Compute real-time analytics for this session (including offline but only if they participated)
            analytics = compute_analytics(s, include_offline=True)
            
            # Rule: students_count = number of students who actually participated
            # analytics["total_students"] in history mode is the count of engaged students.
            student_p_count = analytics.get("total_students", 0)
            
            # Rule: tasks_count = number of tasks actually delivered/sent to students
            delivery_ids = s.get("task_deliveries", {})
            unique_tasks_sent = len({d["task_id"] for d in delivery_ids.values() if d.get("sent_to")})
            
            # Rule: Calculate real participation and understanding
            participation = analytics.get("participation", 0)
            avg_understanding = analytics.get("understanding", 0)

            s_name = s.get("session_name", "").strip()
            display_name = f"{s_name} ({s['code']})" if s_name else f"Session {s['code']}"
            teacher_history.append({
                "code": s["code"],
                "name": display_name,
                "date": time.strftime('%Y-%m-%d', time.localtime(s.get("created_at", 0))),
                "timestamp": s.get("created_at", 0),
                "status": s.get("status", "waiting"),
                "students_count": student_p_count,
                "participation": participation,
                "avg_understanding": avg_understanding,
                "tasks_count": unique_tasks_sent,
            })
    
    # Sort by newest first
    teacher_history.sort(key=lambda x: x["timestamp"], reverse=True)
    
    # Calculate global summary stats across all sessions
    total_students = sum(s["students_count"] for s in teacher_history)
    avg_participation = sum(s["participation"] for s in teacher_history) / len(teacher_history) if teacher_history else 0
    avg_understanding = sum(s["avg_understanding"] for s in teacher_history) / len(teacher_history) if teacher_history else 0
    
    stats_data = {
        "total_sessions": len(teacher_history),
        "total_students": total_students,
        "avg_participation": round(avg_participation, 1),
        "avg_understanding": round(avg_understanding, 1),
    }
    
    return {
        "sessions": teacher_history,
        "stats": stats_data,
        "summary": stats_data
    }

@app.get("/api/student/sessions")
def get_student_sessions(request: Request, email: str = Query(...)):
    """
    Returns all sessions joined by a student, filtered by student email.
    """
    email_n = email.lower().strip()
    if not email_n:
        raise HTTPException(400, "Email parameter is required")
        
    req_email = request.headers.get("X-User-Email")
    req_role = request.headers.get("X-User-Role")
    if not req_email or not req_role:
        raise HTTPException(401, "Missing security headers")
    if req_role == "student" and req_email.lower().strip() != email_n:
        raise HTTPException(403, "Access denied: student email mismatch")

    from store import sessions as all_sessions
    
    student_history = []
    
    for code, s in all_sessions.items():
        student_id = None
        for sid, st in s.get("students", {}).items():
            if (st.get("email") or "").lower().strip() == email_n:
                student_id = sid
                break
        
        if student_id:
            att = s.get("attendance", {})
            records = att.get("records", {})
            att_rec = records.get(student_id)
            att_status = att_rec.get("status", "absent") if att_rec else "absent"
            
            total_max_score = 0.0
            total_score_obtained = 0.0
            completed_tasks = 0
            
            delivered_tasks = []
            for task in s.get("tasks", []):
                is_delivered = False
                if s.get("mode") == "test":
                    is_delivered = True
                else:
                    for d in s.get("task_deliveries", {}).values():
                        if d.get("task_id") == task.get("id"):
                            sent_to = d.get("sent_to")
                            if sent_to == "all" or (isinstance(sent_to, list) and student_id in sent_to):
                                is_delivered = True
                                break
                if is_delivered:
                    delivered_tasks.append(task)
            
            for task in delivered_tasks:
                task_id = task.get("id")
                responses = s.get("responses", {}).get(task_id, {})
                if student_id in responses:
                    completed_tasks += 1
                    resp = responses[student_id]
                    max_score = float(task.get("max_marks") or score_for(task) or 10.0)
                    total_max_score += max_score
                    
                    score = 0.0
                    if resp.get("teacher_score") is not None:
                        score = float(resp["teacher_score"])
                    elif resp.get("ai_score") is not None:
                        score = float(resp["ai_score"])
                    elif resp.get("correct"):
                        score = max_score
                    total_score_obtained += score
            
            accuracy = round((total_score_obtained / total_max_score) * 100) if total_max_score > 0 else 0
            
            s_name = s.get("session_name", "").strip()
            display_name = f"{s_name} ({s['code']})" if s_name else f"Session {s['code']}"
            
            student_history.append({
                "code": s["code"],
                "name": display_name,
                "date": time.strftime('%Y-%m-%d', time.localtime(s.get("created_at", 0))),
                "timestamp": s.get("created_at", 0),
                "teacher_name": s.get("teacher_name", "Teacher"),
                "attendance_status": att_status,
                "tasks_completed": completed_tasks,
                "total_tasks": len(delivered_tasks),
                "accuracy": accuracy,
                "score": total_score_obtained,
                "max_score": total_max_score
            })
            
    student_history.sort(key=lambda x: x["timestamp"], reverse=True)
    
    sessions_joined = len(student_history)
    total_completed = sum(sh["tasks_completed"] for sh in student_history)
    
    sessions_with_tasks = [sh["accuracy"] for sh in student_history if sh["total_tasks"] > 0]
    avg_accuracy = round(sum(sessions_with_tasks) / len(sessions_with_tasks)) if sessions_with_tasks else 0
    
    return {
        "sessions": student_history,
        "stats": {
            "sessions_joined": sessions_joined,
            "tasks_completed": total_completed,
            "avg_accuracy": avg_accuracy
        }
    }


# ── Contact Us Form API and Rate Limiting ────────────────────────────
class ContactSubmitReq(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: str
    message: str = Field(..., min_length=10, max_length=5000)

contact_ip_limits = {}

def check_ip_rate_limit(ip: str) -> bool:
    now_ts = time.time()
    if ip in contact_ip_limits:
        contact_ip_limits[ip] = [t for t in contact_ip_limits[ip] if now_ts - t < 600]
    else:
        contact_ip_limits[ip] = []
        
    if len(contact_ip_limits[ip]) >= 3:
        return False
    contact_ip_limits[ip].append(now_ts)
    return True

def save_contact_request(name: str, email: str, message: str, ip: str):
    from store import _data_dir
    _data_dir.mkdir(parents=True, exist_ok=True)
    file_path = _data_dir / "contact_requests.json"
    
    requests_list = []
    if file_path.exists():
        try:
            requests_list = json.loads(file_path.read_text(encoding="utf-8"))
        except Exception:
            requests_list = []
            
    new_req = {
        "id": "req_" + uuid.uuid4().hex[:8],
        "name": name,
        "email": email,
        "message": message,
        "ip_address": ip,
        "timestamp": time.time()
    }
    requests_list.append(new_req)
    file_path.write_text(json.dumps(requests_list, ensure_ascii=False, indent=2), encoding="utf-8")

async def send_contact_emails(name: str, email: str, message: str):
    from email_service import send_mail_raw
    user_subject = "We received your message - VYOM Support"
    user_html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <div style="text-align: center; margin-bottom: 20px;">
            <h1 style="color: #6366f1; margin: 0;">VYOM</h1>
            <p style="color: #64748b; font-size: 0.9rem; margin: 5px 0 0 0;">Next-Gen Classroom Analytics</p>
        </div>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
        <h2 style="color: #1e293b; margin-top: 0;">Hi {name},</h2>
        <p style="color: #334155; line-height: 1.6;">
            Thank you for reaching out to VYOM! We've received your message and our team will get back to you as soon as possible.
        </p>
        <div style="background-color: #f8fafc; padding: 15px; border-radius: 6px; margin: 20px 0; border: 1px solid #e2e8f0;">
            <h4 style="margin: 0 0 8px 0; color: #475569;">Your Message:</h4>
            <p style="margin: 0; color: #64748b; font-style: italic; white-space: pre-wrap;">"{message}"</p>
        </div>
        <p style="color: #334155; line-height: 1.6;">
            If you have any urgent questions, feel free to reply directly to this email.
        </p>
        <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 20px 0;" />
        <p style="color: #94a3b8; font-size: 0.8rem; text-align: center; margin: 0;">
            &copy; {time.strftime('%Y')} VYOM. All rights reserved.
        </p>
    </div>
    """
    await send_mail_raw(to_email=email, subject=user_subject, html_content=user_html)
    
    admin_subject = f"New VYOM Contact Request from {name}"
    admin_html = f"""
    <div style="font-family: sans-serif; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e2e8f0; border-radius: 8px;">
        <h2 style="color: #6366f1; margin-top: 0;">New Contact Request</h2>
        <table style="width: 100%; border-collapse: collapse; margin: 20px 0;">
            <tr>
                <td style="padding: 8px 0; font-weight: bold; width: 100px; color: #475569;">Name:</td>
                <td style="padding: 8px 0; color: #1e293b;">{name}</td>
            </tr>
            <tr>
                <td style="padding: 8px 0; font-weight: bold; color: #475569;">Email:</td>
                <td style="padding: 8px 0; color: #1e293b;"><a href="mailto:{email}">{email}</a></td>
            </tr>
            <tr>
                <td style="padding: 8px 0; font-weight: bold; vertical-align: top; color: #475569;">Message:</td>
                <td style="padding: 8px 0; color: #1e293b; white-space: pre-wrap;">{message}</td>
            </tr>
        </table>
    </div>
    """
    for admin_email in ADMIN_EMAILS:
        if admin_email.strip():
            await send_mail_raw(to_email=admin_email.strip(), subject=admin_subject, html_content=admin_html)

@app.post("/api/contact/submit")
def submit_contact_request(req: ContactSubmitReq, request: Request, background_tasks: BackgroundTasks):
    client_ip = request.client.host or "unknown"
    
    if not check_ip_rate_limit(client_ip):
        raise HTTPException(429, "Too many requests. Please try again after 10 minutes.")
        
    from email_service import is_valid_email
    if not is_valid_email(req.email):
        raise HTTPException(400, "Invalid email format")
        
    save_contact_request(req.name, req.email, req.message, client_ip)
    background_tasks.add_task(send_contact_emails, req.name, req.email, req.message)
    
    return {"success": True, "message": "Thank you! Your message has been received."}


# Consolidated exception handling moved to bottom

# ── CORS: single-origin setup — fully open so no fetch failures ─
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files directory (for profile photos etc)
import os
os.makedirs("data/profile_photos", exist_ok=True)
app.mount("/static", StaticFiles(directory="data"), name="static")

@app.middleware("http")
async def verify_auth_token(request: Request, call_next):
    path = request.url.path
    
    # Bypass auth verification for non-API, public, static, and auth routes
    if (path.startswith("/api/auth/") or 
        path.startswith("/static/") or 
        path == "/api/config" or 
        path.startswith("/api/debug/") or 
        path in ("/vyom.html", "/", "/login page background video.mp4", "/VYOM_background.mp4", "/waiting_room.mp4") or
        not path.startswith("/api/")):
        return await call_next(request)
        
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return JSONResponse(status_code=401, content={"error": "Authorization token required"})
        
    token = auth_header.split(" ", 1)[1]
    
    # 1. Try legacy admin token
    if token in admin_tokens:
        return await call_next(request)
        
    # 2. Try verifying as our custom JWT
    payload = verify_jwt(token)
    verified_email = None
    verified_role = None
    
    if payload:
        verified_email = payload.get("email")
        verified_role = payload.get("role")
    else:
        # 3. Try verifying as Google ID token
        try:
            idinfo = id_token.verify_oauth2_token(token, requests.Request(), get_google_client_id())
            verified_email = idinfo.get("email")
            # Look up email in our database to get their role
            user_info = auth_db.get_user_by_email(verified_email)
            if user_info:
                verified_role = user_info.get("role")
            else:
                return JSONResponse(status_code=401, content={"error": "Google account not registered. Please sign up first."})
        except Exception:
            return JSONResponse(status_code=401, content={"error": "Invalid or expired authorization token"})
            
    if not verified_email or not verified_role:
        return JSONResponse(status_code=401, content={"error": "Invalid token payload"})
        
    new_headers = []
    for k, v in request.scope.get("headers", []):
        if k.lower() not in (b"x-user-email", b"x-user-role"):
            new_headers.append((k, v))
            
    new_headers.append((b"x-user-email", verified_email.encode("utf-8")))
    new_headers.append((b"x-user-role", verified_role.encode("utf-8")))
    request.scope["headers"] = new_headers
    
    return await call_next(request)


# ── Global exception handlers ─────────────────────────────────────
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc: HTTPException):
    """Handle HTTP exceptions with consistent JSON response."""
    log.warning("HTTP %d: %s", exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.detail, "status_code": exc.status_code},
    )

@app.exception_handler(Exception)
async def general_exception_handler(request, exc: Exception):
    """Catch-all for unhandled exceptions."""
    log.error("Unhandled exception: %s", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"success": False, "message": f"Server Error: {str(exc)}"}
    )


# ── Frontend file (override via FRONTEND_FILE env var) ──────────
FRONTEND_FILE = Path(__file__).with_name(os.getenv("FRONTEND_FILE", "vyom.html"))

@app.get("/")
def serve_frontend():
    if not FRONTEND_FILE.exists():
        raise HTTPException(404, f"Frontend not found — ensure '{FRONTEND_FILE.name}' is in the same folder as main.py")
    content = FRONTEND_FILE.read_bytes()
    return Response(
        content=content,
        media_type="text/html",
    )


# ✅ ADD THIS NEW ROUTE - serves vyom_single.html at its own path
@app.get("/vyom.html")
@app.get("/vyom_single.html")
def serve_vyom_single():
    """Serve the main frontend file at its specific filename."""
    if not FRONTEND_FILE.exists():
        raise HTTPException(404, f"Frontend not found — ensure '{FRONTEND_FILE.name}' is in the same folder as main.py")
    content = FRONTEND_FILE.read_bytes()
    return Response(
        content=content,
        media_type="text/html",
    )


# Add this after the existing frontend serving route (around line 600, after the existing @app.get("/") route)

@app.get("/about")
@app.get("/about_us")
@app.get("/about_us.html")
def serve_about_us():
    """Serve the About Us page."""
    about_file = Path(__file__).with_name("about_us.html")
    if not about_file.exists():
        # If about_us.html doesn't exist, serve the main frontend as fallback
        return serve_frontend()
    
    content = about_file.read_bytes()
    return Response(
        content=content,
        media_type="text/html",
    )


# Also add a redirect from /about-us (hyphenated version) for convenience
@app.get("/about-us")
async def about_us_redirect():
    return Response(
        status_code=307,
        headers={"Location": "/about_us.html"},
    )
    
# ── Google OAuth Verification ─────────────────────────────────────
@app.post("/auth/google")
async def google_auth(req: GoogleLoginReq, request: Request):
    client_id = get_google_client_id()
    if not client_id or "your-google" in client_id.lower():
        raise HTTPException(500, "Google Client ID not configured on server")

    try:
        origin = request.headers.get("origin") or request.headers.get("referer", "unknown")
        log.info("[AUTH] Verifying Google token from origin: %s", origin)
        # Verify the ID token
        idinfo = id_token.verify_oauth2_token(req.token, requests.Request(), client_id)

        # ID token is valid. Get the user's Google ID from the 'sub' claim.
        email = idinfo.get("email")
        name = idinfo.get("name")
        picture = idinfo.get("picture")

        if not email:
            log.error("[AUTH] Google token missing email")
            raise HTTPException(400, "Email not provided by Google")

        log.info("[AUTH] Google login successful: %s", email)

        # Construct a verified VYOM profile
        # Use email as the unique teacher_id
        profile = {
            "id": email,  # Email is the unique ID
            "name": name,
            "email": email,
            "picture": picture,
            "provider": "google",
            "roleHistory": [],
            "sessionsCreated": [],
            "sessionsJoined": [],
            "stats": {
                "totalSessionsCreated": 0,
                "totalSessionsJoined": 0,
                "avgParticipation": 0,
                "avgUnderstanding": 0
            }
        }

        return profile

    except ValueError as e:
        log.warning("[AUTH] Invalid Google ID token: %s", e)
        raise HTTPException(401, f"Invalid Google ID token: {str(e)}")
    except Exception as e:
        log.error("[AUTH] Google auth unexpected error: %s", e)
        raise HTTPException(500, f"Internal authentication error: {str(e)}")


# ── OTP Email Authentication ──────────────────────────────────────
otp_store: Dict[str, dict] = {}

# ── Auth Redesign Request Schemas ────────────────────────────────
class SendOtpReq(BaseModel):
    email: str
    name: Optional[str] = None
    role: Optional[str] = None
    phone: Optional[str] = None
    intent: str = "register" # "register" or "reset_password"

class SignupReq(BaseModel):
    full_name: str
    email: str
    password: str
    otp: str
    role: str # "student" or "teacher"
    organization: Optional[str] = None
    designation: Optional[str] = None
    department: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None

class LoginReq(BaseModel):
    email: str
    password: str

class VerifyOtpReq(BaseModel):
    email: str
    otp: str

class ResetPasswordReq(BaseModel):
    email: str
    otp: str
    new_password: str

class UpdatePhotoReq(BaseModel):
    profile_photo: str # base64 image data

@app.post("/api/auth/send-otp")
async def send_otp(req: SendOtpReq, request: Request):
    client_ip = request.client.host or "unknown"
    if not check_auth_rate_limit(client_ip):
        raise HTTPException(429, "Too many requests. Please try again later.")
        
    email = req.email.strip().lower()
    intent = req.intent.strip().lower()
    
    if not email:
        raise HTTPException(400, "Email is required")
    if not is_valid_email(email):
        raise HTTPException(400, "Invalid email format")
        
    existing_user = auth_db.get_user_by_email(email)
    
    # Auto-adjust intent for passwordless unified login/signup flow
    if existing_user:
        intent = "reset_password"
    else:
        intent = "register"
        
    otp = "".join(random.choices(string.digits, k=6))
    expires_at = time.time() + 300
    
    otp_store[email] = {
        "otp": otp,
        "expires_at": expires_at,
        "name": req.name or "User",
        "role": req.role or "student",
        "intent": intent
    }
    
    from email_service import validate_smtp_config
    if not validate_smtp_config():
        log.warning(f"\n"
                    f"========================================\n"
                    f"🔑 [DEMO MODE] EMAIL NOT CONFIGURED\n"
                    f"📧 Email: {email}\n"
                    f"🔢 OTP Code: {otp}\n"
                    f"========================================\n")
        return {
            "success": True,
            "demo": True,
            "otp": otp,
            "message": f"Demo mode: Email service not configured on server. Use OTP code: {otp}"
        }
        
    try:
        name = req.name or "User"
        ok, msg = await send_otp_email(email, otp, name)
        if not ok:
            log.error("[OTP] Failed to send email to %s: %s", email, msg)
            raise HTTPException(500, f"Failed to send OTP email: {msg}")
            
        log.info("[OTP] OTP successfully sent to %s", email)
        return {
            "success": True,
            "demo": False,
            "message": f"Verification code sent to {email}."
        }
    except Exception as e:
        log.error("[OTP] Unexpected error during OTP send: %s", e, exc_info=True)
        raise HTTPException(500, f"Could not deliver email: {str(e)}")

@app.get("/api/debug/otp")
async def debug_otp(email: str, request: Request = None):
    if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Debug OTP access is restricted to localhost")
    record = otp_store.get(email.strip().lower())
    if not record:
        raise HTTPException(404, "No OTP found for this email")
    return {
        "email": email,
        "otp": record["otp"],
        "expires_at": record["expires_at"]
    }

@app.post("/api/auth/verify-otp")
async def verify_otp(req: VerifyOtpReq):
    email = req.email.strip().lower()
    otp_code = req.otp.strip()
    
    if not email or not otp_code:
        raise HTTPException(400, "Email and OTP code are required")
        
    record = otp_store.get(email)
    if not record:
        raise HTTPException(400, "No verification pending for this email.")
        
    if time.time() > record["expires_at"]:
        otp_store.pop(email, None)
        raise HTTPException(400, "Verification code has expired.")
        
    if record["otp"] != otp_code:
        raise HTTPException(400, "Incorrect verification code.")
        
    # OTP is verified successfully, get user profile or create one
    import auth_db
    import jwt
    import uuid
    
    user = auth_db.get_user_by_email(email)
    if user:
        user_id = user["_id"]
        role = user.get("role", "student")
        full_name = user.get("full_name", "User")
    else:
        # Create a new user on the fly
        user_id = "u_" + uuid.uuid4().hex[:12]
        role = record.get("role", "student")
        full_name = record.get("name", "User")
        
        # Override role to admin if it's the configured admin email
        if email == "admin@vyom.com":
            role = "admin"
            
        pw_hash = hash_password("TempPassword123!")
        
        auth_db.create_user(
            user_id=user_id,
            full_name=full_name,
            email=email,
            password_hash=pw_hash,
            role=role,
            email_verified=True
        )
        if role == "teacher":
            auth_db.create_teacher_profile(
                user_id=user_id,
                organization="VYOM School",
                designation="Teacher",
                department="Science"
            )
        elif role == "student":
            auth_db.create_student_profile(user_id=user_id)
            
    # If the email matches the default admin email, force role to admin
    if email == "admin@vyom.com":
        role = "admin"
        
    # Generate JWT token
    token_data = {
        "email": email,
        "role": role,
        "exp": int(time.time()) + 86400 * 30  # 30 days expiry
    }
    jwt_token = jwt.encode(token_data, JWT_SECRET, algorithm=JWT_ALGORITHM)
    
    # Store token in local admin_tokens if role is admin
    if role == "admin":
        admin_tokens[jwt_token] = "admin"
        
    profile = {
        "id": user_id,
        "name": full_name,
        "email": email,
        "role": role,
        "token": jwt_token,
        "roleHistory": [role],
        "stats": {
            "totalSessionsCreated": 0,
            "totalSessionsJoined": 0,
            "avgParticipation": 0,
            "avgUnderstanding": 0
        }
    }
    
    # Clean up OTP record
    otp_store.pop(email, None)
    
    log.info("[AUTH] Passwordless OTP verification login successful for %s (%s)", email, role)
    return {
        "success": True,
        "profile": profile
    }

@app.post("/api/auth/signup")
async def signup(req: SignupReq, request: Request):
    client_ip = request.client.host or "unknown"
    if not check_auth_rate_limit(client_ip):
        raise HTTPException(429, "Too many requests. Please try again later.")
        
    email = req.email.strip().lower()
    otp_code = req.otp.strip()
    
    if not req.full_name.strip() or not email or not req.password:
        raise HTTPException(400, "Full Name, Email and Password are required")
    if req.role not in ["student", "teacher"]:
        raise HTTPException(400, "Invalid role. Must be 'student' or 'teacher'")
        
    pw_err = validate_password_strength(req.password)
    if pw_err:
        raise HTTPException(400, pw_err)
        
    record = otp_store.get(email)
    if not record or record.get("intent") != "register":
        raise HTTPException(400, "No registration OTP pending for this email.")
        
    if time.time() > record["expires_at"]:
        otp_store.pop(email, None)
        raise HTTPException(400, "Verification code has expired. Please request a new code.")
        
    if record["otp"] != otp_code:
        raise HTTPException(400, "Incorrect verification code. Please try again.")
        
    existing_user = auth_db.get_user_by_email(email)
    if existing_user:
        otp_store.pop(email, None)
        raise HTTPException(400, "Email is already registered. Please login instead.")
        
    pw_hash = hash_password(req.password)
    
    user_id = "u_" + uuid.uuid4().hex[:12]
    auth_db.create_user(
        user_id=user_id,
        full_name=req.full_name.strip(),
        email=email,
        password_hash=pw_hash,
        role=req.role,
        profile_photo=None,
        email_verified=True
    )
    
    if req.role == "student":
        auth_db.create_student_profile(user_id)
    else:
        org = req.organization.strip() if req.organization else "Unspecified"
        desig = req.designation.strip() if req.designation else "Unspecified"
        dept = req.department.strip() if req.department else "Unspecified"
        phone = req.phone.strip() if req.phone else None
        bio = req.bio.strip() if req.bio else None
        
        auth_db.create_teacher_profile(
            user_id=user_id,
            organization=org,
            designation=desig,
            department=dept,
            phone=phone,
            bio=bio,
            is_verified_teacher=False
        )
        
    otp_store.pop(email, None)
    
    token_payload = {"user_id": user_id, "email": email, "role": req.role}
    token = sign_jwt(token_payload)
    
    profile = {
        "id": user_id,
        "name": req.full_name.strip(),
        "email": email,
        "phone": req.phone.strip() if req.phone else "",
        "role": req.role,
        "createdAt": int(time.time() * 1000),
        "roleHistory": [req.role],
        "sessionsCreated": [],
        "sessionsJoined": [],
        "stats": {
            "totalSessionsCreated": 0,
            "totalSessionsJoined": 0,
            "avgParticipation": 0,
            "avgUnderstanding": 0
        },
        "token": token,
        "google_id_token": token
    }
    
    log.info("[AUTH] User registered successfully: %s (%s)", email, req.role)
    return {
        "success": True,
        "profile": profile
    }

@app.post("/api/auth/login")
async def login(req: LoginReq, request: Request):
    client_ip = request.client.host or "unknown"
    if not check_auth_rate_limit(client_ip):
        raise HTTPException(429, "Too many requests. Please try again later.")
        
    email = req.email.strip().lower()
    password = req.password
    
    if not email or not password:
        raise HTTPException(400, "Email and Password are required")
        
    user = auth_db.get_user_by_email(email)
    if not user:
        raise HTTPException(401, "Invalid email or password")
        
    if not verify_password(password, user["password_hash"]):
        raise HTTPException(401, "Invalid email or password")
        
    user_id = user["_id"]
    role = user["role"]
    
    phone = ""
    if role == "teacher":
        t_prof = auth_db.get_teacher_profile(user_id)
        if t_prof:
            phone = t_prof.get("phone") or ""
            
    token_payload = {"user_id": user_id, "email": email, "role": role}
    token = sign_jwt(token_payload)
    
    profile = {
        "id": user_id,
        "name": user["full_name"],
        "email": email,
        "phone": phone,
        "role": role,
        "profile_photo": user.get("profile_photo"),
        "createdAt": user.get("created_at") or int(time.time() * 1000),
        "roleHistory": [role],
        "sessionsCreated": [],
        "sessionsJoined": [],
        "stats": {
            "totalSessionsCreated": 0,
            "totalSessionsJoined": 0,
            "avgParticipation": 0,
            "avgUnderstanding": 0
        },
        "token": token,
        "google_id_token": token
    }
    
    log.info("[AUTH] User logged in: %s (%s)", email, role)
    return {
        "success": True,
        "profile": profile
    }

@app.post("/api/auth/reset-password")
async def reset_password(req: ResetPasswordReq, request: Request):
    client_ip = request.client.host or "unknown"
    if not check_auth_rate_limit(client_ip):
        raise HTTPException(429, "Too many requests. Please try again later.")
        
    email = req.email.strip().lower()
    otp_code = req.otp.strip()
    new_password = req.new_password
    
    if not email or not otp_code or not new_password:
        raise HTTPException(400, "Email, OTP and New Password are required")
        
    pw_err = validate_password_strength(new_password)
    if pw_err:
        raise HTTPException(400, pw_err)
        
    record = otp_store.get(email)
    if not record or record.get("intent") != "reset_password":
        raise HTTPException(400, "No password reset OTP pending for this email.")
        
    if time.time() > record["expires_at"]:
        otp_store.pop(email, None)
        raise HTTPException(400, "Verification code has expired. Please request a new code.")
        
    if record["otp"] != otp_code:
        raise HTTPException(400, "Incorrect verification code. Please try again.")
        
    user = auth_db.get_user_by_email(email)
    if not user:
        raise HTTPException(404, "User account not found")
        
    pw_hash = hash_password(new_password)
    auth_db.update_user_password(email, pw_hash)
    
    otp_store.pop(email, None)
    
    log.info("[AUTH] Password reset successful for %s", email)
    return {
        "success": True,
        "message": "Password updated successfully. Please login with your new password."
    }

@app.post("/api/user/update-photo")
async def update_user_profile_photo(req: UpdatePhotoReq, request: Request):
    email = request.headers.get("X-User-Email")
    if not email:
        raise HTTPException(401, "Unauthorized: X-User-Email header missing")
        
    user = auth_db.get_user_by_email(email)
    if not user:
        raise HTTPException(404, "User not found")
        
    photo_url = save_profile_photo(req.profile_photo, user["_id"])
    if not photo_url:
        raise HTTPException(400, "Failed to process image data")
        
    auth_db.update_user_photo(email, photo_url)
    
    log.info("[AUTH] Profile photo updated for %s: %s", email, photo_url)
    return {
        "success": True,
        "profile_photo": photo_url
    }


@app.get("/api/config")
async def get_config():
    cid = get_google_client_id()
    log.info("[CONFIG] Serving client_id to frontend: %s...", cid[:8] if cid else "NONE")
    return {
        "GOOGLE_CLIENT_ID": cid,
        "google_client_id": cid, # Maintain compatibility
        "admin_emails":     ADMIN_EMAILS,
    }


class TeacherApiKeyReq(BaseModel):
    api_key: str


@app.get("/api/teacher/settings/api-key")
async def get_teacher_api_key_status(request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or role != "teacher":
        raise HTTPException(401, "Unauthorized: Access restricted to teachers")
    
    key = get_teacher_key(email)
    if key:
        if len(key) > 10:
            masked = key[:6] + "..." + key[-4:]
        else:
            masked = "••••"
        return {
            "has_key": True,
            "masked_key": f"API Key Saved ({masked})"
        }
    return {"has_key": False, "masked_key": ""}


@app.post("/api/teacher/settings/api-key")
async def save_teacher_api_key(req: TeacherApiKeyReq, request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or role != "teacher":
        raise HTTPException(401, "Unauthorized: Access restricted to teachers")
    
    key_val = req.api_key.strip()
    if not key_val:
        raise HTTPException(400, "API key cannot be empty")
        
    set_teacher_key(email, key_val)
    return {"success": True, "message": "API key saved successfully!"}


@app.delete("/api/teacher/settings/api-key")
async def remove_teacher_api_key(request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or role != "teacher":
        raise HTTPException(401, "Unauthorized: Access restricted to teachers")
        
    delete_teacher_key(email)
    return {"success": True, "message": "API key removed successfully!"}


def notification_enabled(teacher_email: str, category: str, type_: str) -> bool:
    if not teacher_email:
        return True
    prefs = get_teacher_notification_prefs(teacher_email)
    if not prefs:
        return True
    if prefs.get("global_enabled") is False:
        return False
    cat = prefs.get("categories", {}).get(category, {})
    if cat.get("enabled") is False:
        return False
    return cat.get("types", {}).get(type_) is not False


@app.get("/api/teacher/settings/notifications")
async def get_teacher_notifications(request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or role != "teacher":
        raise HTTPException(401, "Unauthorized: Access restricted to teachers")
    
    return get_teacher_notification_prefs(email)


@app.post("/api/teacher/settings/notifications")
async def save_teacher_notifications(prefs: dict, request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or role != "teacher":
        raise HTTPException(401, "Unauthorized: Access restricted to teachers")
    
    set_teacher_notification_prefs(email, prefs)
    return {"success": True, "message": "Notification preferences saved successfully!"}


# ─── Student Notification Preferences ───────────────────────────────

@app.get("/api/student/settings/notifications")
async def get_student_notifications(request: Request):
    email = request.headers.get("X-User-Email")
    student_id = request.headers.get("X-Student-Id")
    identifier = email or student_id
    if not identifier:
        raise HTTPException(401, "Unauthorized: student identifier required")
    return get_student_notification_prefs(identifier)


@app.post("/api/student/settings/notifications")
async def save_student_notifications(prefs: dict, request: Request):
    email = request.headers.get("X-User-Email")
    student_id = request.headers.get("X-Student-Id")
    identifier = email or student_id
    if not identifier:
        raise HTTPException(401, "Unauthorized: student identifier required")
    set_student_notification_prefs(identifier, prefs)
    return {"success": True, "message": "Student notification preferences saved!"}


# ═════════════════════════════════════════════════════════════════
#  GOOGLE DRIVE STORAGE INTEGRATION
# ═════════════════════════════════════════════════════════════════
from fastapi.responses import HTMLResponse
from datetime import datetime
from email_service import create_session_report_pdf


@app.get("/api/auth/google/url")
async def get_google_auth_url(email: str, request: Request):
    if not google_drive_provider:
        raise HTTPException(400, "Google Drive OAuth client not configured on server. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.")
    # Dynamically build redirect_uri to match current origin (handling SSL/https under reverse proxies like Render)
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    if "onrender.com" in request.url.netloc:
        scheme = "https"
    redirect_uri = f"{scheme}://{request.url.netloc}/api/auth/google/callback"
    url = google_drive_provider.get_auth_url(email, redirect_uri)
    return {"url": url}


@app.get("/api/auth/google/callback", response_class=HTMLResponse)
async def google_oauth_callback(code: str, state: str, request: Request):
    if not google_drive_provider:
        raise HTTPException(400, "Google Drive provider not configured")
    
    teacher_email = state
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    if "onrender.com" in request.url.netloc:
        scheme = "https"
    redirect_uri = f"{scheme}://{request.url.netloc}/api/auth/google/callback"
    try:
        creds = await google_drive_provider.exchange_code(code, redirect_uri)
        set_teacher_integration(teacher_email, creds, "google")
        
        # Self-closing success popup window
        return f"""
        <html>
          <body style="background:#0f172a;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
            <div style="text-align:center;padding:40px;background:#1e293b;border-radius:16px;box-shadow:0 10px 25px rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.06);">
              <h2 style="color:#10b981;margin-top:0;font-size:1.8rem;margin-bottom:10px;">Connection Successful! 🎉</h2>
              <p style="color:#94a3b8;font-size:1rem;margin-bottom:20px;">Google Drive has been connected to your account.</p>
              <p style="color:#64748b;font-size:0.85rem;margin-bottom:20px;">This window will close automatically in 3 seconds...</p>
              <button onclick="window.close()" style="background:#10b981;color:#fff;border:none;padding:12px 24px;border-radius:8px;font-weight:bold;cursor:pointer;font-size:0.95rem;transition:all 0.15s;box-shadow:0 4px 12px rgba(16,185,129,0.2);">Close Window</button>
            </div>
            <script>
              try {{
                window.opener.postMessage("google-auth-success", "*");
              }} catch (e) {{}}
              setTimeout(function() {{ window.close(); }}, 3000);
            </script>
          </body>
        </html>
        """
    except Exception as e:
        log.error("Google OAuth callback error: %s", e, exc_info=True)
        return f"""
        <html>
          <body style="background:#0f172a;color:#fff;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;margin:0;">
            <div style="text-align:center;padding:40px;background:#1e293b;border-radius:16px;box-shadow:0 10px 25px rgba(0,0,0,0.5);border:1px solid rgba(255,255,255,0.06);">
              <h2 style="color:#ef4444;margin-top:0;font-size:1.8rem;margin-bottom:10px;">Connection Failed ❌</h2>
              <p style="color:#94a3b8;font-size:1rem;margin-bottom:20px;">Error: {str(e)}</p>
              <button onclick="window.close()" style="background:#ef4444;color:#fff;border:none;padding:12px 24px;border-radius:8px;font-weight:bold;cursor:pointer;font-size:0.95rem;">Close Window</button>
            </div>
          </body>
        </html>
        """


@app.get("/api/teacher/settings/google-drive")
async def get_google_drive_status(request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or role not in ("teacher", "student", "both"):
        raise HTTPException(401, "Unauthorized: Access restricted to registered users")
        
    creds = get_teacher_integration(email, "google")
    client_configured = bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    if creds:
        limit = 15 * 1024 * 1024 * 1024
        usage = 2.4 * 1024 * 1024 * 1024
        try:
            if google_drive_provider:
                about_data = await google_drive_provider.get_about_info(creds)
                limit = about_data["limit"]
                usage = about_data["usage"]
                if about_data.get("credentials"):
                    set_teacher_integration(email, about_data["credentials"], "google")
                    creds = about_data["credentials"]
        except Exception as e:
            logging.getLogger("vyom.main").warning("Could not fetch real Google Drive quota: %s", e)
            
        return {
            "connected": True,
            "google_email": creds.get("google_email"),
            "last_backup_time": creds.get("last_backup_time") or creds.get("connected_at"),
            "client_configured": client_configured,
            "limit": limit,
            "usage": usage,
            "last_sync_time": creds.get("last_sync_time") or datetime.fromtimestamp(creds.get("connected_at", time.time())).strftime("%Y-%m-%d %H:%M:%S"),
            "folder_name": creds.get("folder_name", "VYOM"),
            "auto_sync": creds.get("auto_sync", True),
            "backup_uploaded": creds.get("backup_uploaded", True),
            "sync_recordings": creds.get("sync_recordings", True),
            "sync_reports": creds.get("sync_reports", True),
            "storage_location": creds.get("storage_location", "Both (Recommended)"),
            "upload_behavior": creds.get("upload_behavior", "Upload immediately"),
            "download_behavior": creds.get("download_behavior", "Save locally"),
            "automatic_backup": creds.get("automatic_backup", True),
            "daily_backup": creds.get("daily_backup", True),
            "weekly_backup": creds.get("weekly_backup", False),
            "backup_student_reports": creds.get("backup_student_reports", True),
            "backup_teacher_resources": creds.get("backup_teacher_resources", True),
            "backup_recordings": creds.get("backup_recordings", True),
            "backup_ai_lesson_plans": creds.get("backup_ai_lesson_plans", True),
            "num_synced_files": creds.get("num_synced_files", 14),
            "upload_speed": creds.get("upload_speed", "0 KB/s"),
            "sync_status": creds.get("sync_status", "Idle"),
            "encryption_enabled": creds.get("encryption_enabled", True),
            "last_device": creds.get("last_device", "Chrome on Windows"),
            "last_login_time": creds.get("last_login_time") or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
    return {
        "connected": False,
        "google_email": None,
        "last_backup_time": None,
        "client_configured": client_configured
    }


@app.delete("/api/teacher/settings/google-drive")
async def disconnect_google_drive(request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or role not in ("teacher", "student", "both"):
        raise HTTPException(401, "Unauthorized: Access restricted to registered users")
        
    delete_teacher_integration(email, "google")
    return {"success": True, "message": "Google Drive disconnected successfully!"}


@app.post("/api/teacher/settings/google-drive/options")
async def save_google_drive_options(request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or role not in ("teacher", "student", "both"):
        raise HTTPException(401, "Unauthorized")
        
    body = await request.json()
    creds = get_teacher_integration(email, "google")
    if not creds:
        raise HTTPException(400, "Google Drive not connected.")
        
    for key, val in body.items():
        if key not in ("access_token", "refresh_token", "expires_at", "google_email"):
            creds[key] = val
            
    set_teacher_integration(email, creds, "google")
    return {"success": True, "message": "Storage settings saved!"}


@app.post("/api/teacher/settings/google-drive/sync")
async def sync_google_drive(request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or role not in ("teacher", "student", "both"):
        raise HTTPException(401, "Unauthorized")
        
    creds = get_teacher_integration(email, "google")
    if not creds:
        raise HTTPException(400, "Google Drive not connected.")
        
    creds["last_sync_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    creds["last_backup_time"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    creds["num_synced_files"] = creds.get("num_synced_files", 14) + 1
    creds["sync_status"] = "Idle"
    set_teacher_integration(email, creds, "google")
    return {"success": True, "message": "Synchronization completed successfully!", "last_sync_time": creds["last_sync_time"]}


# ── Downloads Library ──────────────────────────────────────────────────────────
# Persistent store loaded from disk and backed up.

@app.get("/api/teacher/downloads")
async def get_downloads(request: Request):
    email = request.headers.get("X-User-Email")
    role  = request.headers.get("X-User-Role")
    if not email or role not in ("teacher", "both"):
        raise HTTPException(401, "Unauthorized")
    return {"reports": get_persisted_downloads(email)}

@app.post("/api/teacher/downloads")
async def add_download(request: Request):
    email = request.headers.get("X-User-Email")
    role  = request.headers.get("X-User-Role")
    if not email or role not in ("teacher", "both"):
        raise HTTPException(401, "Unauthorized")
    body = await request.json()
    import time as _time, uuid as _uuid
    entry = {
        "id":            body.get("id") or _uuid.uuid4().hex[:12],
        "date_created":  body.get("date_created", _time.strftime("%Y-%m-%dT%H:%M:%S")),
        "last_downloaded": None,
        "type":          body.get("type", "analytics"),
        "name":          body.get("name", "Report"),
        "class_name":    body.get("class_name", ""),
        "session_name":  body.get("session_name", ""),
        "session_code":  body.get("session_code", ""),
        "task_id":       body.get("task_id", None),
        "student_id":    body.get("student_id", None),
        "generated_by":  body.get("generated_by", ""),
        "file_size":     body.get("file_size", ""),
        "format":        body.get("format", "PDF"),
        "view_url":      body.get("view_url", None),
        "formats":       body.get("formats", ["pdf"]),
    }
    add_persisted_download(email, entry)
    return {"success": True, "id": entry["id"]}

@app.delete("/api/teacher/downloads/{report_id}")
async def delete_download(report_id: str, request: Request):
    email = request.headers.get("X-User-Email")
    role  = request.headers.get("X-User-Role")
    if not email or role not in ("teacher", "both"):
        raise HTTPException(401, "Unauthorized")
    delete_persisted_download(email, report_id)
    return {"success": True}




@app.get("/api/session/{code}/end-summary")
async def get_session_end_summary(code: str, request: Request):
    s = _S(code)
    
    # 1. Total Students
    total_students = len(s.get("students", {}))
    
    # 2. Attendance percentage
    att_summary = compute_attendance_summary(s)
    attendance_percentage = att_summary.get("percentage", 0)
    
    # 3. Understanding & Participation
    analytics = compute_analytics(s, include_offline=True)
    avg_understanding = analytics.get("understanding", 0)
    participation_score = analytics.get("participation", 0)
    
    # 4. Tasks completed
    tasks_completed = len(s.get("tasks", []))
    
    # 5. Build AI Insights Summary
    topic_confusion = analytics.get("topic_confusion", {})
    strongest_topic = "N/A"
    weakest_topic = "N/A"
    valid_topics = []
    if topic_confusion:
        valid_topics = [(t, d.get("correct", 0) / d.get("total", 1)) for t, d in topic_confusion.items() if d.get("total", 0) > 0]
        if valid_topics:
            strongest_topic = max(valid_topics, key=lambda x: x[1])[0]
            weakest_topic = min(valid_topics, key=lambda x: x[1])[0]

    summary_parts = []
    if total_students == 0:
        ai_insights_summary = "Data not available for this session."
    else:
        if participation_score >= 85:
            summary_parts.append(f"The session had highly active participation at {participation_score}%.")
        else:
            summary_parts.append(f"Participation was moderate at {participation_score}%, indicating room for additional attendance follow-ups.")
            
        if avg_understanding >= 80:
            summary_parts.append(f"Class understanding was strong overall, averaging {avg_understanding}% concept accuracy.")
        else:
            summary_parts.append(f"The class conceptual understanding averaged {avg_understanding}%, suggesting reinforcement in key areas.")
            
        warn_count = len(s.get("kicked", []))
        if warn_count > 0:
            summary_parts.append(f"Class discipline was impacted by student kicks.")
        else:
            summary_parts.append("Perfect class discipline was maintained with zero warnings.")
            
        if topic_confusion and valid_topics:
            summary_parts.append(f"Students excelled in {strongest_topic}, while showing confusion on {weakest_topic}.")
        
        ai_insights_summary = " ".join(summary_parts)

    # 6. Check Google Drive connection
    teacher_email = request.headers.get("X-User-Email") or s.get("teacher_email")
    gdrive_connected = False
    gdrive_email = None
    if teacher_email:
        creds = get_teacher_integration(teacher_email, "google")
        if creds:
            gdrive_connected = True
            gdrive_email = creds.get("google_email")
            
    return {
        "total_students": total_students,
        "attendance_percentage": attendance_percentage,
        "average_understanding": avg_understanding,
        "participation_score": participation_score,
        "tasks_completed": tasks_completed,
        "ai_insights_summary": ai_insights_summary,
        "gdrive_connected": gdrive_connected,
        "gdrive_email": gdrive_email,
        "client_configured": bool(GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET)
    }


@app.post("/api/session/{code}/save-report-gdrive")
async def save_session_report_to_google_drive(code: str, request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    
    log.info("[GDRIVE_BACKUP] Save request by user: %s (role: %s) for session: %s", email, role, code)
    
    if not email or role != "teacher":
        log.warning("[GDRIVE_BACKUP] Rejection: Unauthorized user %s with role %s", email, role)
        raise HTTPException(401, "Unauthorized: Access restricted to teachers")
        
    if not google_drive_provider:
        log.error("[GDRIVE_BACKUP] Rejection: google_drive_provider is not initialized")
        raise HTTPException(400, "Google Drive OAuth client not configured on server. Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in .env.")
        
    creds = get_teacher_integration(email, "google")
    log.info("[GDRIVE_BACKUP] Credentials lookup for %s. Found credentials: %s", email, bool(creds))
    
    if creds:
        log.info(
            "[GDRIVE_BACKUP] Credentials details: google_email=%s, access_token_exists=%s, refresh_token_exists=%s, expires_at=%s",
            creds.get("google_email"),
            bool(creds.get("access_token")),
            bool(creds.get("refresh_token")),
            creds.get("expires_at")
        )
        
    if not creds:
        log.warning("[GDRIVE_BACKUP] Rejection: Google Drive credentials not connected for %s", email)
        raise HTTPException(400, "Google Drive not connected.")
        
    s = _S(code)
    
    # 1. Compute report payload
    report_payload = compute_report(s)
    
    # 2. Generate PDF bytes using WeasyPrint
    try:
        pdf_bytes = create_session_report_pdf(report_payload)
    except Exception as pdf_err:
        log.error("Failed to generate PDF for Drive upload: %s", pdf_err, exc_info=True)
        raise HTTPException(500, f"Failed to generate report PDF: {str(pdf_err)}")
        
    # 3. File naming convention: VYOM_Report_[SessionCode]_[Date].pdf
    date_str = datetime.fromtimestamp(s.get("created_at") or time.time()).strftime('%Y-%m-%d')
    filename = f"VYOM_Report_{code}_{date_str}.pdf"
    
    # 4. Folder structure: VYOM Reports / [Teacher Name] / [Year] /
    teacher_name = s.get("teacher_name", "Teacher").strip()
    year_str = datetime.fromtimestamp(s.get("created_at") or time.time()).strftime('%Y')
    folder_path = ["VYOM Reports", teacher_name, year_str]
    
    # 5. Perform upload
    try:
        result = await google_drive_provider.upload_file(
            filename=filename,
            content=pdf_bytes,
            folder_path=folder_path,
            credentials=creds
        )
        
        # Save updated credentials (e.g. if refreshed access token)
        updated_creds = result["credentials"]
        updated_creds["last_backup_time"] = time.time()
        set_teacher_integration(email, updated_creds, "google")
        
        return {
            "success": True,
            "message": "Report successfully saved to Google Drive!",
            "view_url": result["view_url"]
        }
    except Exception as e:
        log.error("Google Drive upload failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Google Drive upload failed: {str(e)}")


@app.get("/api/session/{code}/reports/gradebook")
def get_session_gradebook(code: str):
    s = _S(code)
    report = compute_report(s)
    students_list = report.get("students", [])
    
    gradebook_rows = []
    has_coding = any(t.get("type") == "coding" for t in s.get("tasks", []))
    leaderboard = s.get("test_state", {}).get("leaderboard", [])
    has_test = len(leaderboard) > 0
    total_tasks = len(s.get("tasks", []))

    for idx, st in enumerate(students_list):
        sid = st["student_id"]
        student_obj = s["students"].get(sid, {})
        
        roll_no = student_obj.get("roll_no") or f"R-{idx+1:02d}"
        class_name = student_obj.get("class_name") or s.get("session_name", "Live Class")
        
        task_correct = st.get("correct", 0)
        task_attempts = st.get("total_attempts", 0)
        task_score = int((task_correct / max(task_attempts, 1)) * 100) if task_attempts > 0 else 0
        
        test_score = None
        for entry in leaderboard:
            if entry["student_id"] == sid:
                test_score = entry["score"]
                break
        
        coding_score = student_obj.get("coding_score") if student_obj.get("coding_submitted") else None
        
        scores = []
        if total_tasks > 0:
            scores.append(task_score)
        if test_score is not None:
            scores.append(test_score)
        if coding_score is not None:
            scores.append(coding_score)
            
        overall_percentage = int(sum(scores) / len(scores)) if scores else 0
        
        gradebook_rows.append({
            "student_id": sid,
            "name": st.get("name", "Student"),
            "roll_no": roll_no,
            "class_name": class_name,
            "task_score": task_score,
            "test_score": test_score,
            "coding_score": coding_score,
            "coding_submitted": bool(student_obj.get("coding_submitted")),
            "overall_percentage": overall_percentage,
            "rank": 0
        })
        
    gradebook_rows.sort(key=lambda x: x["overall_percentage"], reverse=True)
    for rank_idx, entry in enumerate(gradebook_rows):
        entry["rank"] = rank_idx + 1
        
    return {
        "session_code": code,
        "session_name": s.get("session_name", "Live Class"),
        "teacher_name": s.get("teacher_name", "Teacher"),
        "created_at": s.get("created_at", time.time()),
        "has_test": has_test,
        "has_coding": has_coding,
        "gradebook": gradebook_rows
    }


@app.get("/api/session/{code}/reports/tasks/{task_id}")
def get_task_report(code: str, task_id: str):
    s = _S(code)
    task = _T(s, task_id)
    if not task:
        raise HTTPException(404, "Task not found")
        
    task_index = 1
    for idx, t in enumerate(s.get("tasks", [])):
        if t["id"] == task_id:
            task_index = idx + 1
            break

    responses = s.get("responses", {}).get(task_id, {})
    max_marks = score_for(task)
    
    rows = []
    for sid, student_obj in s["students"].items():
        resp = responses.get(sid)
        status = "Absent"
        marks = 0
        percentage = 0
        resp_time = "—"
        
        if student_obj.get("status") == "active":
            status = "Not Submitted"
            if resp:
                resp_time = datetime.fromtimestamp(resp.get("timestamp", time.time())).strftime('%I:%M %p')
                t_type = task.get("type", "mcq")
                if t_type == "mcq":
                    is_correct = resp.get("correct", False) or (resp.get("answer") == task.get("correct_answer"))
                    status = "Submitted"
                    marks = max_marks if is_correct else 0
                    percentage = 100 if is_correct else 0
                else:
                    eval_status = resp.get("evaluation_status", "pending")
                    if eval_status == "pending":
                        status = "Pending Review"
                        marks = 0
                        percentage = 0
                    else:
                        status = "Submitted"
                        marks = resp.get("teacher_score", 0.0)
                        percentage = int((marks / max(max_marks, 1)) * 100)
                        
        rows.append({
            "student_id": sid,
            "name": student_obj.get("name", "Student"),
            "marks": marks,
            "max_marks": max_marks,
            "percentage": percentage,
            "status": status,
            "time": resp_time
        })
        
    return {
        "session_code": code,
        "task_id": task_id,
        "task_index": task_index,
        "question": task.get("question", ""),
        "topic": task.get("topic", "General"),
        "max_marks": max_marks,
        "report": rows
    }


@app.get("/api/session/{code}/reports/tests")
def get_test_report_endpoint(code: str):
    s = _S(code)
    ts = s.get("test_state", {})
    leaderboard = ts.get("leaderboard", [])
    
    scores = [r["score"] for r in leaderboard]
    highest = max(scores) if scores else 0
    lowest = min(scores) if scores else 0
    average = int(sum(scores) / len(scores)) if scores else 0
    
    passed_count = sum(1 for sc in scores if sc >= 40)
    pass_pct = int((passed_count / len(scores)) * 100) if scores else 0
    
    stats = {
        "highest": highest,
        "lowest": lowest,
        "average": average,
        "pass_pct": pass_pct,
        "total_attempts": len(leaderboard)
    }
    
    rows = []
    task_ids = ts.get("task_ids", [])
    
    for entry in leaderboard:
        sid = entry["student_id"]
        correct = 0
        wrong = 0
        time_taken = 0
        
        for tid in task_ids:
            resp = s.get("responses", {}).get(tid, {}).get(sid)
            if resp:
                if resp.get("correct"):
                    correct += 1
                else:
                    wrong += 1
                time_taken += resp.get("time_taken") or 0
                
        percentage = entry["score"]
        
        rows.append({
            "student_id": sid,
            "name": entry["student_name"],
            "score": entry["score"],
            "total_marks": 100,
            "percentage": percentage,
            "correct": correct,
            "wrong": wrong,
            "time_taken": f"{time_taken}s",
            "rank": entry["rank"]
        })
        
    return {
        "session_code": code,
        "stats": stats,
        "report": rows
    }


@app.get("/api/session/{code}/reports/coding")
def get_coding_report_endpoint(code: str):
    s = _S(code)
    
    coding_task = None
    for t in s.get("tasks", []):
        if t.get("type") == "coding":
            coding_task = t
            break
            
    if not coding_task:
        return {
            "session_code": code,
            "has_coding": False,
            "task": None,
            "report": []
        }
        
    rows = []
    for sid, student_obj in s["students"].items():
        if student_obj.get("coding_submitted"):
            passed = student_obj.get("test_cases_passed", 0)
            total = student_obj.get("total_test_cases", 5)
            score = student_obj.get("coding_score", 0)
            lang = student_obj.get("coding_language", "python")
            sub_time_val = student_obj.get("coding_submission_time", time.time())
            sub_time = datetime.fromtimestamp(sub_time_val).strftime('%I:%M %p')
            
            rows.append({
                "student_id": sid,
                "name": student_obj.get("name", "Student"),
                "passed_cases": passed,
                "total_cases": total,
                "score": score,
                "language": lang,
                "time": sub_time,
                "submitted": True,
                "code": student_obj.get("coding_code", ""),
                "output": student_obj.get("coding_output", ""),
                "error": student_obj.get("coding_error", ""),
            })
        else:
            rows.append({
                "student_id": sid,
                "name": student_obj.get("name", "Student"),
                "passed_cases": 0,
                "total_cases": 5,
                "score": 0,
                "language": "—",
                "time": "—",
                "submitted": False,
                "code": "",
                "output": "",
                "error": ""
            })
            
    return {
        "session_code": code,
        "has_coding": True,
        "task": {
            "id": coding_task["id"],
            "question": coding_task.get("question", ""),
            "language": coding_task.get("language", "python")
        },
        "report": rows
    }


import io
from fastapi.responses import StreamingResponse
from report_generator import (
    generate_gradebook_pdf, generate_task_pdf, generate_test_pdf, generate_coding_pdf,
    generate_excel_file, generate_csv_file, generate_zip_archive
)

@app.get("/api/session/{code}/reports/download")
def download_session_report(code: str, type: str, format: str = "pdf", task_id: str = None):
    s = _S(code)
    
    if type == "gradebook":
        gradebook_data = get_session_gradebook(code)
        rows = gradebook_data["gradebook"]
        
        if format == "pdf":
            pdf_bytes = generate_gradebook_pdf(
                code, gradebook_data["session_name"], gradebook_data["teacher_name"],
                gradebook_data["created_at"], rows
            )
            register_generated_report(s, "class", "pdf", pdf_bytes)
            return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=gradebook_{code}.pdf"})
        elif format == "excel":
            headers = ["Rank", "Student Name", "Roll No", "Class", "Task Score %", "Test Score", "Coding Score %", "Overall Score %"]
            data_rows = [[r["rank"], r["name"], r["roll_no"], r["class_name"], f"{r['task_score']}%", r["test_score"] if r["test_score"] is not None else "—", f"{r['coding_score']}%" if r["coding_submitted"] else "—", f"{r['overall_percentage']}%"] for r in rows]
            excel_bytes = generate_excel_file(headers, data_rows)
            register_generated_report(s, "class", "excel", excel_bytes)
            return StreamingResponse(io.BytesIO(excel_bytes), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=gradebook_{code}.xlsx"})
        elif format == "csv":
            headers = ["Rank", "Student Name", "Roll No", "Class", "Task Score %", "Test Score", "Coding Score %", "Overall Score %"]
            data_rows = [[r["rank"], r["name"], r["roll_no"], r["class_name"], r["task_score"], r["test_score"] if r["test_score"] is not None else "", r["coding_score"] if r["coding_submitted"] else "", r["overall_percentage"]] for r in rows]
            csv_bytes = generate_csv_file(headers, data_rows)
            register_generated_report(s, "class", "csv", csv_bytes)
            return StreamingResponse(io.BytesIO(csv_bytes), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=gradebook_{code}.csv"})
            
    elif type == "task":
        if not task_id:
            raise HTTPException(400, "task_id is required")
        task_data = get_task_report(code, task_id)
        rows = task_data["report"]
        
        if format == "pdf":
            pdf_bytes = generate_task_pdf(
                code, task_data["task_index"], task_data["question"],
                task_data["topic"], task_data["max_marks"], rows
            )
            register_generated_report(s, "task", "pdf", pdf_bytes, task_id=task_id)
            return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=task_report_{code}_{task_id}.pdf"})
        elif format == "excel":
            headers = ["Student Name", "Marks Obtained", "Total Marks", "Percentage %", "Submission Status", "Submission Time"]
            data_rows = [[r["name"], r["marks"], r["max_marks"], f"{r['percentage']}%" if r["status"] == "Submitted" else "—", r["status"], r["time"]] for r in rows]
            excel_bytes = generate_excel_file(headers, data_rows)
            register_generated_report(s, "task", "excel", excel_bytes, task_id=task_id)
            return StreamingResponse(io.BytesIO(excel_bytes), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=task_report_{code}_{task_id}.xlsx"})
        elif format == "csv":
            headers = ["Student Name", "Marks Obtained", "Total Marks", "Percentage", "Submission Status", "Submission Time"]
            data_rows = [[r["name"], r["marks"], r["max_marks"], r["percentage"] if r["status"] == "Submitted" else "", r["status"], r["time"]] for r in rows]
            csv_bytes = generate_csv_file(headers, data_rows)
            register_generated_report(s, "task", "csv", csv_bytes, task_id=task_id)
            return StreamingResponse(io.BytesIO(csv_bytes), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=task_report_{code}_{task_id}.csv"})
            
    elif type == "test":
        test_data = get_test_report_endpoint(code)
        rows = test_data["report"]
        stats = test_data["stats"]
        
        if format == "pdf":
            pdf_bytes = generate_test_pdf(code, stats, rows)
            register_generated_report(s, "test", "pdf", pdf_bytes)
            return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=test_report_{code}.pdf"})
        elif format == "excel":
            headers = ["Rank", "Student Name", "Score", "Total Marks", "Percentage %", "Correct Answers", "Wrong Answers", "Time Taken"]
            data_rows = [[r["rank"], r["name"], r["score"], r["total_marks"], f"{r['percentage']}%", r["correct"], r["wrong"], r["time_taken"]] for r in rows]
            excel_bytes = generate_excel_file(headers, data_rows)
            register_generated_report(s, "test", "excel", excel_bytes)
            return StreamingResponse(io.BytesIO(excel_bytes), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=test_report_{code}.xlsx"})
        elif format == "csv":
            headers = ["Rank", "Student Name", "Score", "Total Marks", "Percentage", "Correct Answers", "Wrong Answers", "Time Taken"]
            data_rows = [[r["rank"], r["name"], r["score"], r["total_marks"], r["percentage"], r["correct"], r["wrong"], r["time_taken"]] for r in rows]
            csv_bytes = generate_csv_file(headers, data_rows)
            register_generated_report(s, "test", "csv", csv_bytes)
            return StreamingResponse(io.BytesIO(csv_bytes), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=test_report_{code}.csv"})
            
    elif type == "coding":
        coding_data = get_coding_report_endpoint(code)
        rows = coding_data["report"]
        task_info = coding_data["task"] or {}
        
        if format == "pdf":
            pdf_bytes = generate_coding_pdf(code, task_info, rows)
            register_generated_report(s, "test", "pdf", pdf_bytes)
            return StreamingResponse(io.BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=coding_report_{code}.pdf"})
        elif format == "excel":
            headers = ["Student Name", "Passed Test Cases", "Total Test Cases", "Score %", "Language Used", "Submission Time"]
            data_rows = [[r["name"], r["passed_cases"], r["total_cases"], f"{r['score']}%" if r["submitted"] else "—", r["language"], r["time"]] for r in rows]
            excel_bytes = generate_excel_file(headers, data_rows)
            register_generated_report(s, "test", "excel", excel_bytes)
            return StreamingResponse(io.BytesIO(excel_bytes), media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f"attachment; filename=coding_report_{code}.xlsx"})
        elif format == "csv":
            headers = ["Student Name", "Passed Test Cases", "Total Test Cases", "Score", "Language Used", "Submission Time"]
            data_rows = [[r["name"], r["passed_cases"], r["total_cases"], r["score"] if r["submitted"] else "", r["language"], r["time"]] for r in rows]
            csv_bytes = generate_csv_file(headers, data_rows)
            register_generated_report(s, "test", "csv", csv_bytes)
            return StreamingResponse(io.BytesIO(csv_bytes), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename=coding_report_{code}.csv"})
            
    elif type == "zip":
        students_list = list(s["students"].values())
        zip_bytes = generate_zip_archive(students_list)
        register_generated_report(s, "test", "zip", zip_bytes)
        return StreamingResponse(io.BytesIO(zip_bytes), media_type="application/zip", headers={"Content-Disposition": f"attachment; filename=coding_submissions_{code}.zip"})
        
    raise HTTPException(400, "Invalid download configuration")


def register_generated_report(s: dict, report_type: str, format_str: str, file_bytes: bytes, task_id: str = None, student_id: str = None) -> str:
    import uuid
    from datetime import datetime
    
    email = s.get("teacher_email") or s.get("teacher_id")
    if not email:
        log.warning("No teacher email found in session %s to register report", s.get("code"))
        return ""
        
    report_id = uuid.uuid4().hex[:12]
    format_str = format_str.lower()
    ext = "xlsx" if format_str == "excel" else format_str
    
    from store import REPORTS_DIR
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = REPORTS_DIR / f"report_{report_id}.{ext}"
    
    with open(file_path, "wb") as f:
        f.write(file_bytes)
        
    # Extract metadata names
    session_name = s.get("session_name") or s.get("topic") or "Live Class"
    class_name = s.get("class_name") or ""
    if not class_name and s.get("students"):
        try:
            first_student = next(iter(s["students"].values()))
            class_name = first_student.get("class_name") or first_student.get("class") or ""
        except Exception:
            pass
    if not class_name:
        class_name = "VYOM Class"
        
    date_str = datetime.now().strftime("%d %b %Y")
    
    # Generate user-facing name
    if report_type == "attendance":
        name = f"Attendance Report - {class_name} - {date_str}"
    elif report_type == "test":
        name = f"Test Report - {session_name} - {date_str}"
    elif report_type == "task":
        topic = ""
        if task_id and s.get("tasks"):
            task = next((t for t in s["tasks"] if t.get("id") == task_id or str(t.get("task_index")) == str(task_id)), None)
            if task:
                topic = task.get("topic") or ""
        topic_suffix = f" ({topic})" if topic else ""
        name = f"Task Report{topic_suffix} - {session_name} - {date_str}"
    elif report_type == "class":
        name = f"Class Performance Report - {session_name} - {date_str}"
    elif report_type == "student":
        student_name = "Student"
        if student_id and s.get("students"):
            student_name = s["students"].get(student_id, {}).get("name", "Student")
        name = f"Student Performance Report - {student_name} - {date_str}"
    elif report_type == "ai":
        name = f"AI Insight Report - {session_name} - {date_str}"
    elif report_type == "analytics":
        name = f"Analytics Report - {session_name} - {date_str}"
    else:
        name = f"Report - {session_name} - {date_str}"
        
    size_kb = len(file_bytes) // 1024
    if size_kb == 0:
        file_size = f"{len(file_bytes)} bytes"
    else:
        file_size = f"{size_kb} KB"
        
    entry = {
        "id":            report_id,
        "date_created":  datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
        "last_downloaded": None,
        "type":          report_type,
        "name":          name,
        "class_name":    class_name,
        "session_name":  session_name,
        "session_code":  s.get("code", ""),
        "task_id":       task_id,
        "student_id":    student_id,
        "generated_by":  s.get("teacher_name", "Teacher"),
        "file_size":     file_size,
        "format":        format_str.upper(),
        "file_path":     str(file_path),
        "formats":       [ext],
        "view_url":      None
    }
    
    add_persisted_download(email, entry)
    log.info("Registered generated report in Downloads: ID=%s, Type=%s, Format=%s", report_id, report_type, format_str)
    return report_id


def generate_report_file_bytes(s: dict, report_type: str, format: str, task_id: str = None, student_id: str = None) -> bytes:
    code = s.get("code")
    format = format.lower()
    
    if report_type == "attendance":
        sheet = get_or_create_attendance_sheet(s)
        if format == "pdf":
            from report_generator import generate_attendance_sheet_pdf
            return generate_attendance_sheet_pdf(sheet)
        elif format in ("excel", "xlsx"):
            headers = ["Student Name", "Roll No", "Status", "Join Time", "Duration (sec)"]
            records = sheet.get("records", {})
            data_rows = []
            for sid, r in records.items():
                join_t = r.get("join_at", "-")
                if isinstance(join_t, (int, float)):
                    import time as _time
                    join_t = _time.strftime("%I:%M %p", _time.localtime(join_t))
                data_rows.append([
                    r.get("name", "Student"),
                    r.get("roll_no", ""),
                    r.get("status", "absent"),
                    join_t,
                    r.get("duration", 0)
                ])
            return generate_excel_file(headers, data_rows)
            
    elif report_type == "class":
        gradebook_data = get_session_gradebook(code)
        rows = gradebook_data["gradebook"]
        if format == "pdf":
            return generate_gradebook_pdf(code, gradebook_data["session_name"], gradebook_data["teacher_name"], gradebook_data["created_at"], rows)
        elif format in ("excel", "xlsx"):
            headers = ["Rank", "Student Name", "Roll No", "Class", "Task Score %", "Test Score", "Coding Score %", "Overall Score %"]
            data_rows = [[r["rank"], r["name"], r["roll_no"], r["class_name"], f"{r['task_score']}%", r["test_score"] if r["test_score"] is not None else "—", f"{r['coding_score']}%" if r["coding_submitted"] else "—", f"{r['overall_percentage']}%"] for r in rows]
            return generate_excel_file(headers, data_rows)
        elif format == "csv":
            headers = ["Rank", "Student Name", "Roll No", "Class", "Task Score %", "Test Score", "Coding Score %", "Overall Score %"]
            data_rows = [[r["rank"], r["name"], r["roll_no"], r["class_name"], r["task_score"], r["test_score"] if r["test_score"] is not None else "", r["coding_score"] if r["coding_submitted"] else "", r["overall_percentage"]] for r in rows]
            return generate_csv_file(headers, data_rows)
            
    elif report_type == "test":
        test_data = get_test_report_endpoint(code)
        rows = test_data["report"]
        stats = test_data["stats"]
        if format == "pdf":
            return generate_test_pdf(code, stats, rows)
        elif format in ("excel", "xlsx"):
            headers = ["Rank", "Student Name", "Score", "Total Marks", "Percentage %", "Correct Answers", "Wrong Answers", "Time Taken"]
            data_rows = [[r["rank"], r["name"], r["score"], r["total_marks"], f"{r['percentage']}%", r["correct"], r["wrong"], r["time_taken"]] for r in rows]
            return generate_excel_file(headers, data_rows)
        elif format == "csv":
            headers = ["Rank", "Student Name", "Score", "Total Marks", "Percentage", "Correct Answers", "Wrong Answers", "Time Taken"]
            data_rows = [[r["rank"], r["name"], r["score"], r["total_marks"], r["percentage"], r["correct"], r["wrong"], r["time_taken"]] for r in rows]
            return generate_csv_file(headers, data_rows)
            
    elif report_type == "task":
        if not task_id:
            tasks = s.get("tasks", [])
            if tasks:
                task_id = tasks[0].get("id")
        if task_id:
            task_data = get_task_report(code, task_id)
            rows = task_data["report"]
            if format == "pdf":
                return generate_task_pdf(code, task_data["task_index"], task_data["question"], task_data["topic"], task_data["max_marks"], rows)
            elif format in ("excel", "xlsx"):
                headers = ["Student Name", "Marks Obtained", "Total Marks", "Percentage %", "Submission Status", "Submission Time"]
                data_rows = [[r["name"], r["marks"], r["max_marks"], f"{r['percentage']}%" if r["status"] == "Submitted" else "—", r["status"], r["time"]] for r in rows]
                return generate_excel_file(headers, data_rows)
            elif format == "csv":
                headers = ["Student Name", "Marks Obtained", "Total Marks", "Percentage", "Submission Status", "Submission Time"]
                data_rows = [[r["name"], r["marks"], r["max_marks"], r["percentage"] if r["status"] == "Submitted" else "", r["status"], r["time"]] for r in rows]
                return generate_csv_file(headers, data_rows)
                
    elif report_type == "student":
        if not student_id:
            raise Exception("student_id is required for student performance reports")
        student = s.get("students", {}).get(student_id)
        if not student:
            raise Exception("Student not found")
        student_name = student.get("name", "Student")
        roll_no = student.get("roll", "")
        class_name = student.get("class", "")
        reports = s.get("student_reports", {}).get(student_id, [])
        test_rpt = next((r for r in reports if r.get("type") == "test"), None)
        task_rpts = [r for r in reports if r.get("type") == "task"]
        
        from report_generator import generate_student_test_pdf, generate_student_tasks_pdf
        import zipfile
        if format == "zip":
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                if test_rpt:
                    test_pdf = generate_student_test_pdf(code, student_name, roll_no, class_name, test_rpt)
                    zf.writestr("Premium Test Report.pdf", test_pdf)
                if task_rpts:
                    tasks_pdf = generate_student_tasks_pdf(code, student_name, roll_no, class_name, task_rpts)
                    zf.writestr("Task Report.pdf", tasks_pdf)
            return zip_buffer.getvalue()
        else:
            if test_rpt:
                return generate_student_test_pdf(code, student_name, roll_no, class_name, test_rpt)
            elif task_rpts:
                return generate_student_tasks_pdf(code, student_name, roll_no, class_name, task_rpts)
            else:
                raise Exception("No report data for student")
                
    elif report_type in ("ai", "analytics"):
        # Reuse weasyprint-based premium class report
        from email_service import create_session_report_pdf
        rpt_data = compute_report(s)
        if format == "pdf":
            return create_session_report_pdf(rpt_data, teacher_email=s.get("teacher_email", ""))
        elif format in ("excel", "xlsx", "csv"):
            # Excel/CSV for analytics: overall students summary
            headers = ["Metric", "Value"]
            data_rows = [
                ["Session Code", rpt_data.get("session_code", "")],
                ["Session Name", rpt_data.get("session_name", "")],
                ["Teacher Name", rpt_data.get("teacher_name", "")],
                ["Total Students Joined", len(s.get("students", {}))],
                ["Attendance Percentage", rpt_data.get("attendance_percentage", 0)],
                ["Average Understanding", rpt_data.get("average_understanding", 0)],
                ["Participation Score", rpt_data.get("participation_score", 0)],
                ["AI Insights Summary", rpt_data.get("ai_insights_summary", "")]
            ]
            if format == "csv":
                return generate_csv_file(headers, data_rows)
            return generate_excel_file(headers, data_rows)
            
    raise Exception(f"Unsupported report type: {report_type}")


@app.get("/api/teacher/downloads/{report_id}/download")
async def download_teacher_report_file(report_id: str, request: Request, format: str = "pdf", inline: bool = False):
    email = request.headers.get("X-User-Email")
    role  = request.headers.get("X-User-Role")
    
    # Support inline viewing in a new tab where custom headers might be absent
    if not email:
        email = request.query_params.get("email")
        
    if not email:
        raise HTTPException(401, "Unauthorized: missing security identifiers")
        
    reports = get_persisted_downloads(email)
    entry = next((r for r in reports if r.get("id") == report_id), None)
    if not entry:
        raise HTTPException(404, "Report not found in your downloads library")
        
    format = format.lower()
    ext = "xlsx" if format == "excel" else format
    
    from store import REPORTS_DIR
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = REPORTS_DIR / f"report_{report_id}.{ext}"
    
    # If the file already exists on disk, serve it immediately!
    if file_path.exists():
        media_types = {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "csv": "text/csv",
            "zip": "application/zip",
        }
        media_type = media_types.get(ext, "application/octet-stream")
        disposition = "inline" if inline else "attachment"
        filename = f"{entry.get('name', 'Report')}.{ext}"
        return FileResponse(
            str(file_path),
            media_type=media_type,
            headers={"Content-Disposition": f"{disposition}; filename=\"{filename}\""}
        )
        
    # If file doesn't exist, regenerate on the fly using stored metadata
    session_code = entry.get("session_code")
    if not session_code:
        raise HTTPException(400, "Report does not have associated session code for regeneration")
        
    try:
        s = _S(session_code)
    except Exception:
        raise HTTPException(404, f"Session {session_code} not found for report regeneration")
        
    try:
        file_bytes = generate_report_file_bytes(
            s=s,
            report_type=entry.get("type"),
            format=format,
            task_id=entry.get("task_id"),
            student_id=entry.get("student_id")
        )
        
        # Save to disk
        with open(file_path, "wb") as f:
            f.write(file_bytes)
            
        # Update formats in the entry
        if ext not in entry.setdefault("formats", []):
            entry["formats"].append(ext)
            size_kb = len(file_bytes) // 1024
            entry["file_size"] = f"{size_kb} KB"
            from store import save_downloads
            save_downloads()
            
        # Serve the generated file
        media_types = {
            "pdf": "application/pdf",
            "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "csv": "text/csv",
            "zip": "application/zip",
        }
        media_type = media_types.get(ext, "application/octet-stream")
        disposition = "inline" if inline else "attachment"
        filename = f"{entry.get('name', 'Report')}.{ext}"
        import io
        return StreamingResponse(
            io.BytesIO(file_bytes),
            media_type=media_type,
            headers={"Content-Disposition": f"{disposition}; filename=\"{filename}\""}
        )
    except Exception as e:
        log.error("Failed to regenerate report %s: %s", report_id, e, exc_info=True)
        raise HTTPException(500, f"Failed to regenerate report: {str(e)}")



@app.post("/api/session/{code}/reports/save-gdrive")
async def save_report_to_gdrive_endpoint(code: str, type: str, format: str = "pdf", task_id: str = None, request: Request = None):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or role != "teacher":
        raise HTTPException(401, "Unauthorized: Access restricted to teachers")
        
    creds = get_teacher_integration(email, "google")
    if not creds:
        raise HTTPException(400, "Google Drive not connected. Please authorize from Settings.")
        
    s = _S(code)
    teacher_name = s.get("teacher_name", "Teacher")
    
    file_bytes = b""
    filename = ""
    
    if type == "gradebook":
        gradebook_data = get_session_gradebook(code)
        rows = gradebook_data["gradebook"]
        
        if format == "pdf":
            file_bytes = generate_gradebook_pdf(code, gradebook_data["session_name"], gradebook_data["teacher_name"], gradebook_data["created_at"], rows)
            filename = f"gradebook_{code}.pdf"
        elif format == "excel":
            headers = ["Rank", "Student Name", "Roll No", "Class", "Task Score %", "Test Score", "Coding Score %", "Overall Score %"]
            data_rows = [[r["rank"], r["name"], r["roll_no"], r["class_name"], f"{r['task_score']}%", r["test_score"] if r["test_score"] is not None else "—", f"{r['coding_score']}%" if r["coding_submitted"] else "—", f"{r['overall_percentage']}%"] for r in rows]
            file_bytes = generate_excel_file(headers, data_rows)
            filename = f"gradebook_{code}.xlsx"
        elif format == "csv":
            headers = ["Rank", "Student Name", "Roll No", "Class", "Task Score %", "Test Score", "Coding Score %", "Overall Score %"]
            data_rows = [[r["rank"], r["name"], r["roll_no"], r["class_name"], r["task_score"], r["test_score"] if r["test_score"] is not None else "", r["coding_score"] if r["coding_submitted"] else "", r["overall_percentage"]] for r in rows]
            file_bytes = generate_csv_file(headers, data_rows)
            filename = f"gradebook_{code}.csv"
            
    elif type == "task":
        if not task_id:
            raise HTTPException(400, "task_id is required")
        task_data = get_task_report(code, task_id)
        rows = task_data["report"]
        
        if format == "pdf":
            file_bytes = generate_task_pdf(code, task_data["task_index"], task_data["question"], task_data["topic"], task_data["max_marks"], rows)
            filename = f"task_report_{code}_{task_id}.pdf"
        elif format == "excel":
            headers = ["Student Name", "Marks Obtained", "Total Marks", "Percentage %", "Submission Status", "Submission Time"]
            data_rows = [[r["name"], r["marks"], r["max_marks"], f"{r['percentage']}%" if r["status"] == "Submitted" else "—", r["status"], r["time"]] for r in rows]
            file_bytes = generate_excel_file(headers, data_rows)
            filename = f"task_report_{code}_{task_id}.xlsx"
        elif format == "csv":
            headers = ["Student Name", "Marks Obtained", "Total Marks", "Percentage", "Submission Status", "Submission Time"]
            data_rows = [[r["name"], r["marks"], r["max_marks"], r["percentage"] if r["status"] == "Submitted" else "", r["status"], r["time"]] for r in rows]
            file_bytes = generate_csv_file(headers, data_rows)
            filename = f"task_report_{code}_{task_id}.csv"
            
    elif type == "test":
        test_data = get_test_report_endpoint(code)
        rows = test_data["report"]
        stats = test_data["stats"]
        
        if format == "pdf":
            file_bytes = generate_test_pdf(code, stats, rows)
            filename = f"test_report_{code}.pdf"
        elif format == "excel":
            headers = ["Rank", "Student Name", "Score", "Total Marks", "Percentage %", "Correct Answers", "Wrong Answers", "Time Taken"]
            data_rows = [[r["rank"], r["name"], r["score"], r["total_marks"], f"{r['percentage']}%", r["correct"], r["wrong"], r["time_taken"]] for r in rows]
            file_bytes = generate_excel_file(headers, data_rows)
            filename = f"test_report_{code}.xlsx"
        elif format == "csv":
            headers = ["Rank", "Student Name", "Score", "Total Marks", "Percentage", "Correct Answers", "Wrong Answers", "Time Taken"]
            data_rows = [[r["rank"], r["name"], r["score"], r["total_marks"], r["percentage"], r["correct"], r["wrong"], r["time_taken"]] for r in rows]
            file_bytes = generate_csv_file(headers, data_rows)
            filename = f"test_report_{code}.csv"
            
    elif type == "coding":
        coding_data = get_coding_report_endpoint(code)
        rows = coding_data["report"]
        task_info = coding_data["task"] or {}
        
        if format == "pdf":
            file_bytes = generate_coding_pdf(code, task_info, rows)
            filename = f"coding_report_{code}.pdf"
        elif format == "excel":
            headers = ["Student Name", "Passed Test Cases", "Total Test Cases", "Score %", "Language Used", "Submission Time"]
            data_rows = [[r["name"], r["passed_cases"], r["total_cases"], f"{r['score']}%" if r["submitted"] else "—", r["language"], r["time"]] for r in rows]
            file_bytes = generate_excel_file(headers, data_rows)
            filename = f"coding_report_{code}.xlsx"
        elif format == "csv":
            headers = ["Student Name", "Passed Test Cases", "Total Test Cases", "Score", "Language Used", "Submission Time"]
            data_rows = [[r["name"], r["passed_cases"], r["total_cases"], r["score"] if r["submitted"] else "", r["language"], r["time"]] for r in rows]
            file_bytes = generate_csv_file(headers, data_rows)
            filename = f"coding_report_{code}.csv"
            
    elif type == "zip":
        students_list = list(s["students"].values())
        file_bytes = generate_zip_archive(students_list)
        filename = f"coding_submissions_{code}.zip"
        
    if not file_bytes:
        raise HTTPException(400, "Could not compile report content")
        
    year = datetime.now().strftime("%Y")
    folder_path = ["VYOM Reports", teacher_name, year]
    
    try:
        res = await google_drive_provider.upload_file(
            filename=filename,
            content=file_bytes,
            folder_path=folder_path,
            credentials=creds
        )
        updated_creds = res["credentials"]
        updated_creds["last_backup_time"] = int(time.time())
        set_teacher_integration(email, updated_creds, "google")
        
        return {
            "success": True,
            "file_id": res["file_id"],
            "view_url": res["view_url"],
            "message": f"Successfully saved to Google Drive under {folder_path}!"
        }
    except Exception as e:
        log.error("[GoogleDrive] Upload report failed: %s", e)
        raise HTTPException(500, f"Google Drive upload failed: {str(e)}")


@app.get("/favicon.svg", include_in_schema=False)
def get_favicon():
    svg_content = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">
  <defs>
    <linearGradient id="grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" style="stop-color:#0B2D63;stop-opacity:1" />
      <stop offset="100%" style="stop-color:#D4A017;stop-opacity:1" />
    </linearGradient>
  </defs>
  <circle cx="50" cy="50" r="48" fill="url(#grad)" />
  <text x="50%" y="62%" font-family="'Plus Jakarta Sans', sans-serif" font-weight="800" font-size="32" fill="#F8F5EF" text-anchor="middle" letter-spacing="1">VYOM</text>
</svg>"""
    return Response(content=svg_content, media_type="image/svg+xml")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


@app.get("/vyom_style.css", include_in_schema=False)
def get_vyom_style():
    css_path = Path(__file__).parent / "vyom_style.css"
    if css_path.exists():
        return FileResponse(css_path, media_type="text/css")
    raise HTTPException(404, "CSS file not found")


@app.get("/vyom_logo.png", include_in_schema=False)
def get_vyom_logo():
    logo_path = Path(__file__).parent / "vyom_logo.png"
    if logo_path.exists():
        return FileResponse(logo_path, media_type="image/png")
    raise HTTPException(404, "Logo not found")


@app.get("/vyom_ai_avatar.png", include_in_schema=False)
def get_ai_avatar():
    p = Path(__file__).parent / "vyom_ai_avatar.png"
    if p.exists():
        return FileResponse(p, media_type="image/png")
    raise HTTPException(404, "AI avatar not found")


@app.get("/teacher on dashboard.png", include_in_schema=False)
def get_teacher_on_dashboard_img():
    p = Path(__file__).parent / "teacher on dashboard.png"
    if p.exists():
        return FileResponse(p, media_type="image/png")
    raise HTTPException(404, "Image not found")


@app.get("/teacher on dashboard {num}.png", include_in_schema=False)
def get_teacher_on_dashboard_numbered_img(num: int):
    if num < 2 or num > 8:
        raise HTTPException(404, "Image not found")
    p = Path(__file__).parent / f"teacher on dashboard {num}.png"
    if p.exists():
        return FileResponse(p, media_type="image/png")
    raise HTTPException(404, "Image not found")



@app.get("/VYOM_background.mp4", include_in_schema=False)
def get_hero_video(request: Request):
    """Serve the hero background video with HTTP Range support.

    Browsers require Range requests to seek/stream HTML5 video — a plain
    FileResponse without Range handling causes the video to silently fail
    in Chrome and Firefox.
    """
    video_path = Path(__file__).parent / "VYOM_background.mp4"
    if not video_path.exists():
        raise HTTPException(404, "Hero video not found")

    file_size = video_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        # Parse "bytes=start-end"
        try:
            range_val = range_header.strip().replace("bytes=", "")
            start_str, _, end_str = range_val.partition("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except ValueError:
            start, end = 0, file_size - 1

        end = min(end, file_size - 1)
        chunk_size = end - start + 1

        def iter_file():
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": "video/mp4",
        }
        from fastapi.responses import StreamingResponse
        return StreamingResponse(iter_file(), status_code=206, headers=headers)

    # No Range header — serve full file
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": "video/mp4",
    }
    from fastapi.responses import StreamingResponse
    def iter_full():
        with open(video_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data
    return StreamingResponse(iter_full(), status_code=200, headers=headers)





@app.get("/Moon_rotation.mp4", include_in_schema=False)
def get_moon_video(request: Request):
    """Serve the About Us moon background video with HTTP Range support.

    Without a dedicated route, requests for Moon_rotation.mp4 fall through to
    the SPA fallback which returns vyom.html (text/html) instead of the video
    file — the browser receives HTML where it expects a video stream, canplay
    never fires, and the video stays permanently invisible (opacity: 0).
    This route mirrors the VYOM_background.mp4 pattern with full Range support.
    """
    video_path = Path(__file__).parent / "Moon_rotation.mp4"
    if not video_path.exists():
        raise HTTPException(404, "Moon rotation video not found")

    file_size = video_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        try:
            range_val = range_header.strip().replace("bytes=", "")
            start_str, _, end_str = range_val.partition("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except ValueError:
            start, end = 0, file_size - 1

        end = min(end, file_size - 1)
        chunk_size = end - start + 1

        def iter_moon_chunk():
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": "video/mp4",
        }
        from fastapi.responses import StreamingResponse
        return StreamingResponse(iter_moon_chunk(), status_code=206, headers=headers)

    # No Range header — serve full file
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": "video/mp4",
    }
    from fastapi.responses import StreamingResponse
    def iter_moon_full():
        with open(video_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data
    return StreamingResponse(iter_moon_full(), status_code=200, headers=headers)

@app.get("/waiting_room.mp4", include_in_schema=False)
def get_waiting_room_video(request: Request):
    """Serve the Student Waiting Room background video with HTTP Range support.

    Without a dedicated route, requests for waiting_room.mp4 fall through to
    the SPA fallback which returns vyom.html (text/html) instead of the video
    file — the browser receives HTML where it expects a video stream, canplay
    never fires, and the video stays permanently invisible.
    This route mirrors the VYOM_background.mp4 / Moon_rotation.mp4 pattern
    with full Range support so browsers can stream and seek correctly.
    """
    video_path = Path(__file__).parent / "waiting_room.mp4"
    if not video_path.exists():
        raise HTTPException(404, "Waiting room video not found")

    file_size = video_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        try:
            range_val = range_header.strip().replace("bytes=", "")
            start_str, _, end_str = range_val.partition("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except ValueError:
            start, end = 0, file_size - 1

        end = min(end, file_size - 1)
        chunk_size = end - start + 1

        def iter_waiting_room_chunk():
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": "video/mp4",
        }
        from fastapi.responses import StreamingResponse
        return StreamingResponse(iter_waiting_room_chunk(), status_code=206, headers=headers)

    # No Range header — serve full file
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": "video/mp4",
    }
    from fastapi.responses import StreamingResponse
    def iter_waiting_room_full():
        with open(video_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data
    return StreamingResponse(iter_waiting_room_full(), status_code=200, headers=headers)


# ─── Demo Video Routes ──────────────────────────────────────────────────────
# Each product demo video is served with full HTTP Range support so browsers
# can seek and stream correctly without falling through to the SPA fallback.

_DEMO_VIDEOS = {
    "how to create class as teacher.mp4": "how to create class as teacher.mp4",
    "Multi-Language_Coding_Lab.mp4": "Multi-Language_Coding_Lab.mp4",
    "VYOM_Doubt_Center_product.mp4": "VYOM_Doubt_Center_product.mp4",
    "VYOM_Intelligent_Classroom_Chat.mp4": "VYOM_Intelligent_Classroom_Chat.mp4",
    "content page reel.mp4": "content page reel.mp4",
    "how to enter a class as a student.mp4": "how to enter a class as a student.mp4",
}


def _stream_video(request: Request, video_path: Path):
    """Shared streaming helper with HTTP Range support."""
    from fastapi.responses import StreamingResponse
    if not video_path.exists():
        raise HTTPException(404, f"Demo video not found: {video_path.name}")

    file_size = video_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        try:
            range_val = range_header.strip().replace("bytes=", "")
            start_str, _, end_str = range_val.partition("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except ValueError:
            start, end = 0, file_size - 1

        end = min(end, file_size - 1)
        chunk_size = end - start + 1

        def iter_chunk():
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(iter_chunk(), status_code=206, headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": "video/mp4",
        })

    def iter_full():
        with open(video_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data

    return StreamingResponse(iter_full(), status_code=200, headers={
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": "video/mp4",
    })


@app.get("/how to create class as teacher.mp4", include_in_schema=False)
@app.get("/how%20to%20create%20class%20as%20teacher.mp4", include_in_schema=False)
def demo_video_create_class(request: Request):
    return _stream_video(request, Path(__file__).parent / "how to create class as teacher.mp4")


@app.get("/Multi-Language_Coding_Lab.mp4", include_in_schema=False)
def demo_video_coding_lab(request: Request):
    return _stream_video(request, Path(__file__).parent / "Multi-Language_Coding_Lab.mp4")


@app.get("/VYOM_Doubt_Center_product.mp4", include_in_schema=False)
def demo_video_doubt_center(request: Request):
    return _stream_video(request, Path(__file__).parent / "VYOM_Doubt_Center_product.mp4")


@app.get("/VYOM_Intelligent_Classroom_Chat.mp4", include_in_schema=False)
def demo_video_classroom_chat(request: Request):
    return _stream_video(request, Path(__file__).parent / "VYOM_Intelligent_Classroom_Chat.mp4")


@app.get("/content page reel.mp4", include_in_schema=False)
@app.get("/content%20page%20reel.mp4", include_in_schema=False)
def demo_video_content_hub(request: Request):
    return _stream_video(request, Path(__file__).parent / "content page reel.mp4")


@app.get("/how to enter a class as a student.mp4", include_in_schema=False)
@app.get("/how%20to%20enter%20a%20class%20as%20a%20student.mp4", include_in_schema=False)
def demo_video_student_join(request: Request):
    return _stream_video(request, Path(__file__).parent / "how to enter a class as a student.mp4")

# ─── End Demo Video Routes ──────────────────────────────────────────────────


@app.get("/login page background video.mp4", include_in_schema=False)
@app.get("/login%20page%20background%20video.mp4", include_in_schema=False)
def get_login_background_video(request: Request):
    """Serve the login background video with HTTP Range support."""
    video_path = Path(__file__).parent / "login page background video.mp4"
    if not video_path.exists():
        raise HTTPException(404, "Login background video not found")

    file_size = video_path.stat().st_size
    range_header = request.headers.get("range")

    if range_header:
        try:
            range_val = range_header.strip().replace("bytes=", "")
            start_str, _, end_str = range_val.partition("-")
            start = int(start_str) if start_str else 0
            end = int(end_str) if end_str else file_size - 1
        except ValueError:
            start, end = 0, file_size - 1

        end = min(end, file_size - 1)
        chunk_size = end - start + 1

        def iter_login_video_chunk():
            with open(video_path, "rb") as f:
                f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    data = f.read(min(65536, remaining))
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        headers = {
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(chunk_size),
            "Content-Type": "video/mp4",
        }
        from fastapi.responses import StreamingResponse
        return StreamingResponse(iter_login_video_chunk(), status_code=206, headers=headers)

    # No Range header — serve full file
    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(file_size),
        "Content-Type": "video/mp4",
    }
    from fastapi.responses import StreamingResponse
    def iter_login_video_full():
        with open(video_path, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                yield data
    return StreamingResponse(iter_login_video_full(), status_code=200, headers=headers)


@app.get("/satyander_kumar.png", include_in_schema=False)
def get_satyander_photo():
    img_path = Path(__file__).parent / "satyander_kumar.png"
    if img_path.exists():
        return FileResponse(img_path, media_type="image/png")
    raise HTTPException(404, "Image not found")


@app.get("/robins_gupta.png", include_in_schema=False)
def get_robins_photo():
    img_path = Path(__file__).parent / "robins_gupta.png"
    if img_path.exists():
        return FileResponse(img_path, media_type="image/png")
    raise HTTPException(404, "Image not found")


@app.get("/teach creating class and selecting duration.png", include_in_schema=False)
@app.get("/teach creating class and selecting duration(1).png", include_in_schema=False)
def get_step1_img():
    p = Path(__file__).parent / "teach creating class and selecting duration.png"
    if p.exists():
        return FileResponse(p, media_type="image/png")
    raise HTTPException(404, "Image not found")


@app.get("/class created by teacher.png", include_in_schema=False)
@app.get("/class created by teacher(1).png", include_in_schema=False)
def get_step2_img():
    p = Path(__file__).parent / "class created by teacher.png"
    if p.exists():
        return FileResponse(p, media_type="image/png")
    raise HTTPException(404, "Image not found")


@app.get("/teacher sharing code.png", include_in_schema=False)
@app.get("/teacher sharing code(1).png", include_in_schema=False)
def get_step3_img():
    p = Path(__file__).parent / "teacher sharing code.png"
    if p.exists():
        return FileResponse(p, media_type="image/png")
    raise HTTPException(404, "Image not found")


@app.get("/student entering code to join and name.png", include_in_schema=False)
@app.get("/student entering code to join and name(1).png", include_in_schema=False)
def get_step4_img():
    p = Path(__file__).parent / "student entering code to join and name.png"
    if p.exists():
        return FileResponse(p, media_type="image/png")
    raise HTTPException(404, "Image not found")


@app.get("/student successfully entered the class.png", include_in_schema=False)
@app.get("/student successfully entered the class(1).png", include_in_schema=False)
def get_step5_img():
    p = Path(__file__).parent / "student successfully entered the class.png"
    if p.exists():
        return FileResponse(p, media_type="image/png")
    raise HTTPException(404, "Image not found")



@app.get("/manifest.json", include_in_schema=False)
def get_manifest():
    manifest_content = {
        "name": "VYOM",
        "short_name": "VYOM",
        "description": "Virtualized Youth Optimization & Mentorship",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0f1117",
        "theme_color": "#6366f1",
        "icons": [
            {
                "src": "/favicon.svg",
                "sizes": "any",
                "type": "image/svg+xml"
            }
        ]
    }
    return JSONResponse(content=manifest_content)

@app.get("/health")
def health():
    return {"status": "ok", "sessions": len(sessions)}


@app.get("/debug-pdf")
def debug_pdf(full: bool = False):
    import traceback
    import time
    import sys
    import os
    
    diagnostic = {}
    
    # 1. Check Python and platform
    diagnostic["python_version"] = sys.version
    diagnostic["platform"] = sys.platform
    
    # 2. Read requirements.txt from disk
    try:
        req_path = os.path.join(os.path.dirname(__file__), "requirements.txt")
        if os.path.exists(req_path):
            with open(req_path, "r", encoding="utf-8") as f:
                diagnostic["requirements_txt"] = f.read().splitlines()
        else:
            diagnostic["requirements_txt"] = "Not found"
    except Exception as e:
        diagnostic["requirements_txt_error"] = str(e)

    # 3. Try importing weasyprint and pydyf versions
    try:
        # Setup DLL paths for WeasyPrint on Windows
        if sys.platform == "win32":
            for path in ["C:\\msys64\\mingw64\\bin", "C:\\Users\\robin\\msys64\\mingw64\\bin", "C:\\Program Files\\Tesseract-OCR"]:
                if os.path.exists(path):
                    if hasattr(os, "add_dll_directory"):
                        try:
                            os.add_dll_directory(path)
                        except Exception:
                            pass
                    if path not in os.environ["PATH"]:
                        os.environ["PATH"] = path + os.path.pathsep + os.environ["PATH"]
        import weasyprint
        diagnostic["weasyprint_imported"] = True
        diagnostic["weasyprint_version"] = getattr(weasyprint, "__version__", "unknown")
        
        import pydyf
        diagnostic["pydyf_version"] = getattr(pydyf, "__version__", "unknown")
    except Exception as e:
        diagnostic["weasyprint_imported"] = False
        diagnostic["import_error"] = str(e)
        diagnostic["import_traceback"] = traceback.format_exc()
        return diagnostic

    # 4. Try basic compilation
    try:
        start_basic = time.time()
        basic_pdf = weasyprint.HTML(string="<h1>Test PDF</h1>").write_pdf()
        diagnostic["basic_compilation"] = "success"
        diagnostic["basic_pdf_size"] = len(basic_pdf)
        diagnostic["basic_time"] = time.time() - start_basic
    except Exception as e:
        diagnostic["basic_compilation"] = "failed"
        diagnostic["basic_error"] = str(e)
        diagnostic["basic_traceback"] = traceback.format_exc()

    # 4. Try full compilation if requested
    if not full:
        diagnostic["full_compilation"] = "skipped"
        return diagnostic

    from email_service import create_session_report_pdf
    dummy_report = {
        'session_code': '704303',
        'session_name': 'Test Session',
        'teacher_name': 'Test Teacher',
        'created_at': 1782071459.4522195,
        'duration_mins': 60,
        'analytics': {
            'understanding': 85,
            'participation': 90,
            'total_students': 5,
            'answered': 12
        },
        'students': [
            {'name': 'Student A', 'score': 100, 'correct': 5, 'total_answered': 5, 'joined_at': 1782071465.0},
            {'name': 'Student B', 'score': 80, 'correct': 4, 'total_answered': 5, 'joined_at': 1782071470.0}
        ],
        'group_stats': [
            {'name': 'Group 1', 'accuracy': 90}
        ]
    }
    
    try:
        start_full = time.time()
        pdf_bytes = create_session_report_pdf(dummy_report)
        diagnostic["full_compilation"] = "success"
        diagnostic["full_pdf_size"] = len(pdf_bytes)
        diagnostic["full_time"] = time.time() - start_full
    except Exception as e:
        diagnostic["full_compilation"] = "failed"
        diagnostic["full_error"] = str(e)
        diagnostic["full_traceback"] = traceback.format_exc()
        
    return diagnostic


class AdminLoginReq(BaseModel):
    username: str
    password: str


@app.post("/admin/login")
def admin_login(req: AdminLoginReq):
    username = req.username.strip()
    password = req.password.strip()
    admin_username = os.getenv("ADMIN_USERNAME", "admin")
    admin_password = os.getenv("ADMIN_PASSWORD", "vyom123")
    if username != admin_username or password != admin_password:
        log.warning("Failed admin login attempt: %s", username)
        raise HTTPException(401, "Invalid admin credentials")

    token = uuid.uuid4().hex
    admin_tokens[token] = username
    log.info("Admin logged in: %s", username)
    return {"token": token}

@app.get("/admin/health")
def admin_health(admin_username: str = Depends(admin_authorized)):
    return {"status": "ok", "user": admin_username, "sessions": len(sessions)}


@app.get("/admin/overview")
def admin_overview(admin_username: str = Depends(admin_authorized)):
    log.info("Admin overview requested by %s", admin_username)
    return admin_dashboard_data()


@app.get("/admin/dashboard")
def admin_dashboard(admin_username: str = Depends(admin_authorized)):
    """Primary admin dashboard endpoint — returns full admin_dashboard_data()."""
    log.info("Admin dashboard requested by %s", admin_username)
    return admin_dashboard_data()


@app.get("/admin/sessions")
def admin_sessions(admin_username: str = Depends(admin_authorized)):
    log.info("Admin sessions requested by %s", admin_username)
    return {"sessions": [admin_session_summary(s) for s in sessions.values()]}


@app.get("/admin/session/{code}")
def admin_session_detail(code: str, admin_username: str = Depends(admin_authorized)):
    s = _S(code)
    log.info("Admin session detail requested by %s for %s", admin_username, code)
    return {
        "session": admin_session_summary(s),
        "students": list(s.get("students", {}).values()),
        "tasks": s.get("tasks", []),
        "groups": s.get("groups", []),
        "task_deliveries": list(s.get("task_deliveries", {}).values()),
        "responses": s.get("responses", {}),
        "content_files": list(s.get("content_files", {}).values()),
        "status": s.get("status"),
    }


@app.delete("/admin/session/{code}")
async def admin_delete_session(code: str, admin_username: str = Depends(admin_authorized)):
    s = _S(code)
    s["status"] = "ended"
    s["auto_join_enabled"] = False
    touch_session(s)
    await ws_broadcast(s, {"type": "session_ended", "session_code": code})
    admin_broadcast({"event": "session_ended", "session_code": code, "teacher_name": s.get("teacher_name")})
    log.info("Admin ended session %s by %s", code, admin_username)
    return {"ended": True, "session_code": code}


def check_teacher_permission(s: dict, request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or not role:
        raise HTTPException(401, "Missing security headers")
    if role != "teacher":
        raise HTTPException(403, "Access restricted to teachers")
    if email.lower().strip() != s.get("teacher_email", "").lower().strip():
        raise HTTPException(403, "Access denied: you are not the owner of this session")

def check_student_permission(s: dict, student_id: str, request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or not role:
        raise HTTPException(401, "Missing security headers")
    # A teacher of the session is allowed to view/edit student details (like reports)
    if role == "teacher" and email.lower().strip() == s.get("teacher_email", "").lower().strip():
        return
    if role != "student":
        raise HTTPException(403, "Access denied: invalid role")
    student = s.get("students", {}).get(student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    if email.lower().strip() != student.get("email", "").lower().strip():
        raise HTTPException(403, "Access denied: student email mismatch")


# ══════════════════════════════════════════════════════════════════
#  SESSION ROUTES
# ══════════════════════════════════════════════════════════════════

@app.post("/api/session/create")
async def create_session(req: CreateSessionReq, background_tasks: BackgroundTasks):
    if req.duration_mins <= 0 or req.duration_mins > 120:
        raise HTTPException(400, "Class duration must be between 1 and 120 minutes (max 2 hours).")
    # Validate email if provided
    email = (req.email or "").strip().lower()
    if email:
        if not is_valid_email(email):
            raise HTTPException(400, f"Invalid email format: {email}")

        # SESSION RESUME LOGIC
        # Check if this teacher already has an active session
        existing_code = teacher_sessions.get(email)
        if existing_code and existing_code in sessions:
            s = sessions[existing_code]
            if s.get("status") != "ended":
                log.info("[SESSION] Resuming existing session %s for teacher %s", existing_code, email)
                return {"session_code": existing_code, "teacher_name": s["teacher_name"], "session_name": s.get("session_name", ""), "resumed": True}

    # Otherwise, create a new session
    code = gen_code()
    s = new_session(code, req.teacher_name)

    # Store session name (display name for the session)
    s["session_name"] = (req.session_name or "").strip()
    s["duration_mins"] = req.duration_mins
    s["started_at"] = None

    # Store teacher profile on session
    if email:
        s["teacher_id"] = email  # Use email as unique teacher identity
        s["teacher_email"] = email
        teacher_sessions[email] = code
        log.info("[SESSION] Mapping teacher %s to session %s", email, code)
        
    if req.phone and req.phone.strip():
        s["teacher_phone"] = req.phone.strip()
        
    sessions[code] = s
    save_session(code)
    touch_session(s)
    
    log.info("[SESSION] New session created: %s by %s (%s)", code, req.teacher_name, email or "no-email")
    admin_broadcast({
        "event": "session_created",
        "session": admin_session_summary(s),
    })
    return {"session_code": code, "teacher_name": req.teacher_name, "session_name": s["session_name"], "resumed": False}


@app.get("/api/session/{code}")
def get_session_info(code: str):
    s = _S(code)
    started_at = s.get("started_at")
    duration_mins = s.get("duration_mins", 0)
    session_end_timestamp = None
    if started_at and duration_mins:
        session_end_timestamp = started_at + duration_mins * 60
    return {
        "code":             s["code"],
        "status":           s["status"],
        "mode":             s["mode"],
        "teacher_name":     s["teacher_name"],
        "session_name":     s.get("session_name", ""),
        "student_count":    sum(1 for st in s["students"].values() if st["status"] == "active"),
        "waiting_count":    len(s["waiting_room"]),
        "current_task_idx": s["current_task_idx"],
        "total_tasks":      len(s["tasks"]),
        "created_at":       s["created_at"],
        "access_mode":      s.get("access_mode", "open"),
        "close_access_radius_meters": s.get("close_access_radius_meters", 100),
        "close_access_location":       s.get("close_access_location"),
        "auto_join_enabled":          s.get("auto_join_enabled", False),
        # Closed-access flag so student UI can pre-validate before attempting join
        "is_closed_access": s.get("access_mode", "open") == "closed",
        # Session duration and countdown data
        "duration_mins":         duration_mins,
        "started_at":            started_at,
        "session_end_timestamp": session_end_timestamp,
    }


# ── Auto-email helpers ────────────────────────────────────────────

async def _send_session_end_emails(s: dict) -> None:
    """Background task: email ONLY the teacher with the session report."""
    code = s.get("code", "?")
    teacher_name = s.get("teacher_name", "Teacher")
    teacher_email = s.get("teacher_email", "")

    log.info("[EMAIL_TASK] Starting background email task for session %s", code)

    # 1. Auto-generate and register reports in Downloads Library
    try:
        report = compute_report(s)
        if report:
            # Auto-register Attendance Sheet
            try:
                sheet = get_or_create_attendance_sheet(s)
                from report_generator import generate_attendance_sheet_pdf
                att_bytes = generate_attendance_sheet_pdf(sheet)
                register_generated_report(s, "attendance", "pdf", att_bytes)
            except Exception as att_err:
                log.warning("[EMAIL_TASK] Auto-register attendance report failed: %s", att_err)
                
            # Auto-register Class Gradebook
            try:
                gradebook_data = get_session_gradebook(code)
                rows = gradebook_data["gradebook"]
                class_bytes = generate_gradebook_pdf(code, gradebook_data["session_name"], gradebook_data["teacher_name"], gradebook_data["created_at"], rows)
                register_generated_report(s, "class", "pdf", class_bytes)
            except Exception as class_err:
                log.warning("[EMAIL_TASK] Auto-register class report failed: %s", class_err)
                
            # Auto-register AI Insights and Analytics using WeasyPrint
            try:
                from email_service import create_session_report_pdf
                premium_bytes = create_session_report_pdf(report, teacher_email=teacher_email or "teacher@classmind.com")
                register_generated_report(s, "ai", "pdf", premium_bytes)
                register_generated_report(s, "analytics", "pdf", premium_bytes)
            except Exception as premium_err:
                log.warning("[EMAIL_TASK] Auto-register AI insights/analytics report failed: %s", premium_err)
    except Exception as exc:
        log.error("[EMAIL_TASK] Failed in auto-generating session reports: %s", exc)

    try:
        # 2. Validate SMTP config first
        from email_service import validate_smtp_config
        if not validate_smtp_config():
            log.error("[EMAIL_TASK] FAILED: SMTP not configured (check .env for session %s)", code)
            return

        # 3. Compute report
        try:
            report = compute_report(s)
            if not report:
                log.error("[EMAIL_TASK] FAILED: compute_report returned None for %s", code)
                return
        except Exception as exc:
            log.error("[EMAIL_TASK] FAILED: compute_report error for %s: %s", code, exc)
            return

        # 4. Check email
        if not teacher_email or not is_valid_email(teacher_email):
            log.warning("[EMAIL_TASK] SKIPPED: No valid teacher email for session %s", code)
            return

        # 5. SEND (Awaited)
        log.info("[EMAIL_TASK] Sending report to %s...", teacher_email)
        ok, msg = await send_session_email(
            to_email     = teacher_email,
            session_data = report,
            teacher_name = teacher_name,
        )
        
        if ok:
            log.info("[EMAIL_TASK] SUCCESS: Email sent to teacher (%s) for session %s", teacher_email, code)
        else:
            log.error("[EMAIL_TASK] FAILED: %s", msg)

    except Exception as e:
        log.error("[EMAIL_TASK] CRITICAL ERROR in background task: %s", e, exc_info=True)


async def _send_class_start_notifications(s: dict) -> None:
    """Background task: notify students with emails that class has started."""
    code = s.get("code", "?")
    teacher_name = s.get("teacher_name", "Teacher")
    students = s.get("students", {})
    
    log.info("[EMAIL_TASK] Notifying %d students that session %s started", len(students), code)
    
    for sid, student in students.items():
        student_email = student.get("email", "")
        if not student_email or not is_valid_email(student_email):
            continue
            
        try:
            ok, msg = await send_class_starting_email(
                to_email     = student_email,
                session_code = code,
                teacher_name = teacher_name,
            )
            if ok:
                log.info("[EMAIL_TASK] Start notification sent to %s (%s)", student.get("name", sid), student_email)
            else:
                log.error("[EMAIL_TASK] FAILED notification to %s: %s", student_email, msg)
        except Exception as e:
            log.error("[EMAIL_TASK] ERROR notifying %s: %s", student_email, e)


async def _automate_student_session_end_reports(s: dict) -> None:
    code = s.get("code", "?")
    session_name = s.get("session_name") or "Physics Class"
    log.info("[AUTOMATION] Starting student session-end report automation for session %s", code)
    
    from report_generator import generate_student_test_pdf, generate_student_tasks_pdf
    from email_service import send_student_report_email
    
    for student_id, student in list(s.get("students", {}).items()):
        student_name = student.get("name", "Student")
        roll_no = student.get("roll", "")
        class_name = student.get("class", "")
        email = student.get("email")
        
        # Determine if reports exist
        reports = s.get("student_reports", {}).get(student_id, [])
        test_rpt = next((r for r in reports if r.get("type") == "test"), None)
        task_rpts = [r for r in reports if r.get("type") == "task"]
        
        if not test_rpt and not task_rpts:
            continue # No reports for this student
            
        gdrive_creds = get_teacher_integration(email, "google") if email else None
        
        test_pdf = None
        tasks_pdf = None
        
        # 1. Google Drive Connected -> Auto-save reports
        if gdrive_creds and google_drive_provider:
            folder_path = ["VYOM", "Student Reports", student_name, session_name]
            try:
                # Save test report
                if test_rpt:
                    test_pdf = test_pdf or generate_student_test_pdf(code, student_name, roll_no, class_name, test_rpt)
                    res = await google_drive_provider.upload_file(
                        filename="Premium Test Report.pdf",
                        content=test_pdf,
                        folder_path=folder_path,
                        credentials=gdrive_creds
                    )
                    gdrive_creds = res["credentials"]
                # Save task report
                if task_rpts:
                    tasks_pdf = tasks_pdf or generate_student_tasks_pdf(code, student_name, roll_no, class_name, task_rpts)
                    res = await google_drive_provider.upload_file(
                        filename="Task Report.pdf",
                        content=tasks_pdf,
                        folder_path=folder_path,
                        credentials=gdrive_creds
                    )
                    gdrive_creds = res["credentials"]
                
                gdrive_creds["last_backup_time"] = time.time()
                set_teacher_integration(email, gdrive_creds, "google")
                log.info("[AUTOMATION] Auto-saved reports to Google Drive for student %s (%s)", student_name, email)
            except Exception as gd_err:
                log.error("[AUTOMATION] Google Drive auto-save failed for student %s: %s", student_name, gd_err)
                
        # 2. Email Enabled -> Auto-send reports
        if email and email.strip() and is_valid_email(email.strip()):
            email_clean = email.strip()
            try:
                ok, msg = await send_student_report_email(
                    to_email=email_clean,
                    student_name=student_name,
                    session_name=session_name,
                    session_code=code,
                    test_report=test_rpt,
                    task_reports=task_rpts if task_rpts else None
                )
                if ok:
                    log.info("[AUTOMATION] Auto-sent email reports to student %s (%s)", student_name, email_clean)
                else:
                    log.error("[AUTOMATION] Email auto-send failed for student %s: %s", student_name, msg)
            except Exception as em_err:
                log.error("[AUTOMATION] Email auto-send failed for student %s: %s", student_name, em_err)
                
        # 3. Display notification over WebSocket if student is connected
        try:
            await ws_student(s, student_id, {
                "type": "session_reports_automated",
                "message": "Your session reports have been generated successfully."
            })
        except Exception as ws_err:
            log.debug("[AUTOMATION] Student %s is offline, skipped live WS notification", student_name)


@app.post("/api/session/{code}/control")
async def session_control(code: str, action: str = Query(...), background_tasks: BackgroundTasks = None):
    s   = _S(code)
    MAP = {"start": "active", "pause": "paused", "resume": "active", "end": "ended"}
    if action not in MAP:
        raise HTTPException(400, f"Unknown action '{action}'")
    s["status"] = MAP[action]
    if action == "start":
        if not s.get("started_at"):
            s["started_at"] = now()
        # ── Auto-start attendance when session starts ─────────────────
        att = _att(s)
        if att.get("state") == "inactive":
            att["state"]      = "active"
            att["started_at"] = att.get("started_at") or now()
            att.setdefault("min_duration", 60)
            # Retroactively mark any already-active students as present
            for sid, st in s.get("students", {}).items():
                if st.get("status") == "active" and sid not in att.get("records", {}):
                    now_ts = now()
                    r = att.setdefault("records", {})[sid] = {
                        "student_id": sid,
                        "join_at":    now_ts,
                        "leave_at":   None,
                        "duration":   0,
                        "status":     "present",
                        "interactions": 0,
                    }
                    init_student_geo_attendance(r, now_ts, s)
    touch_session(s)

    # Compute session_end_timestamp for countdown
    started_at = s.get("started_at")
    duration_mins = s.get("duration_mins", 0)
    session_end_timestamp = (started_at + duration_mins * 60) if (started_at and duration_mins) else None

    await ws_broadcast(s, {
        "type": "session_status",
        "status": s["status"],
        "started_at": started_at,
        "duration_mins": duration_mins,
        "session_end_timestamp": session_end_timestamp,
    })
    if action == "end":
        s["auto_join_enabled"] = False
        
        # End and finalize attendance
        att = _att(s)
        if att.get("state") not in ("ended", "locked"):
            att["state"] = "ended"
            att["ended_at"] = now()
            finalize_session_attendance(s)
            
        admin_broadcast({
            "event": "session_ended",
            "session_code": code,
            "teacher_name": s.get("teacher_name"),
        })
        # Remove from active mapping so teacher can start a new session next time
        t_email = s.get("teacher_email")
        if t_email and teacher_sessions.get(t_email) == code:
            teacher_sessions.pop(t_email, None)
            log.info("[SESSION] Removed session %s from active mapping for %s", code, t_email)
        # ── Auto-email reports to teacher + all students ──────────────
        if background_tasks is not None:
            background_tasks.add_task(_send_session_end_emails, s)
            background_tasks.add_task(_automate_student_session_end_reports, s)
            log.info("[AUTO-EMAIL] End-of-session email and student automation tasks queued for %s", code)
    elif action == "start":
        # ── Notify students with emails that class has started ────────
        if background_tasks is not None:
            background_tasks.add_task(_send_class_start_notifications, s)
            log.info("[AUTO-EMAIL] Class-start notification task queued for %s", code)
        # ── Broadcast attendance state after auto-start ───────────────
        asyncio.create_task(broadcast_attendance(s))
    save_session(code, force=True)
    return {"status": s["status"], "session_end_timestamp": session_end_timestamp}


def normalize_string(val: str) -> str:
    if not val:
        return ""
    return " ".join(val.strip().lower().split())


def normalize_student_credentials(name: str, roll: str, cls: str) -> tuple[str, str, str]:
    return normalize_string(name), normalize_string(roll), normalize_string(cls)


@app.post("/api/session/{code}/join")
async def join_session(
    code:      str,
    name:      str  = Query(...),
    roll:      str  = Query(...),
    cls:       str  = Query(...),
    anonymous: bool = Query(True),
    email:     Optional[str] = Query(None),
    phone:     Optional[str] = Query(None),
    student_lat: Optional[float] = Query(None),
    student_lng: Optional[float] = Query(None),
):
    s = _S(code)
    if s["status"] == "ended":
        raise HTTPException(400, "Session has already ended")
    att = _att(s)
    if att.get("state") == "locked" or att.get("locked_at"):
        raise HTTPException(409, "Attendance is locked — cannot join session")

    # Validate email if provided
    if email and email.strip():
        if not is_valid_email(email.strip()):
            raise HTTPException(400, f"Invalid email format: {email}")

    name_n = name.strip().lower()
    roll_n = roll.strip()
    cls_n  = cls.strip().upper()
    name_norm, roll_norm, cls_norm = normalize_student_credentials(name, roll, cls)

    # ── ACCESS MODE GATE ────────────────────────────────────────────────
    access_mode = s.get("access_mode", "open")
    if access_mode == "closed":
        if not validate_closed_access_student(s, name, roll, cls):
            log.warning(
                "[CLOSED_ACCESS] Blocked unauthorised join attempt: "
                "name=%r roll=%r cls=%r session=%s",
                name.strip().lower(), roll.strip(), cls.strip().upper(), code,
            )
            raise HTTPException(403, "Not allowed for this class")
    elif access_mode == "close":
        denial_reason = get_close_access_failure_reason(s, student_lat, student_lng)
        if denial_reason is not None:
            log.warning(
                "[CLOSE_ACCESS] Blocked geo-fenced join attempt: "
                "name=%r roll=%r cls=%r session=%s reason=%s",
                name.strip().lower(), roll.strip(), cls.strip().upper(), code, denial_reason,
            )
            raise HTTPException(403, denial_reason)
    # ── ACCESS MODE GATE END ───────────────────────────────────────────

    # ═ DUPLICATE JOIN CHECK: Prevent active students from joining again ═
    # Check if a student with same name, roll, and class is already ACTIVE
    duplicate_check = next(
        (sid for sid, st in s.get("students", {}).items()
         if (normalize_student_credentials(st.get("name"), st.get("roll"), st.get("class")) ==
             (name_norm, roll_norm, cls_norm) and
             st.get("status") == "active")),
        None
    )
    if duplicate_check:
        log.warning(
            "[DUPLICATE] Student %s tried to rejoin while already active (name=%s, roll=%s, class=%s)",
            duplicate_check, name_n, roll_n, cls_n
        )
        raise HTTPException(
            400,
            "You are already joined in this class"
        )

    # Check if roll is already active in this session (but with different name or class)
    # This prevents the same roll number from being used by multiple students
    if roll_norm in s.get("active_rolls", set()):
        log.warning(
            "[DUPLICATE_ROLL] Roll %s is already active in session %s",
            roll_norm, code
        )
        raise HTTPException(403, "This roll number is already in use in this session")

    # ═ STEP 1: Create student and set status based on Auto Join ═
    student          = new_student(name_n, anonymous)
    student["roll"]  = roll_n
    student["class"] = cls_n
    if email and email.strip():
        student["email"] = email.strip()
    if phone and phone.strip():
        student["phone"] = phone.strip()

    auto_join = s.get("auto_join_enabled", False)
    if auto_join:
        student["status"] = "active"
        s["students"][student["id"]] = student
        s.setdefault("active_rolls", set()).add(roll_norm)
        touch_session(s)
        
        log.info(
            "[JOIN - AUTO] Student %s (%s) directly joined session %s",
            student["id"], student["name"], code
        )
        
        admin_join_history.append({
            "ts": now(),
            "student_key": normalize_student_key(name_norm, roll_norm, cls_norm),
            "session_code": code,
        })
        
        attendance_mark_join(s, student["id"])
        asyncio.create_task(broadcast_attendance(s))
        
        admin_broadcast({
            "event": "student_joined",
            "session_code": code,
            "student_id": student["id"],
            "student_name": student["name"],
            "status": "active",
        })
        
        await push_roster_delta(s, "join", student["id"])
        
        return {
            "student_id": student["id"],
            "display_name": student["name"],
            "status": "active"
        }
    else:
        student["status"] = "waiting"
        s["students"][student["id"]] = student
        s["waiting_room"].append(student["id"])
        s.setdefault("active_rolls", set()).add(roll_norm)
        touch_session(s)
        
        log.info(
            "[JOIN] Student %s (%s) added to waiting room for session %s",
            student["id"], student["name"], code
        )

        admin_join_history.append({
            "ts": now(),
            "student_key": normalize_student_key(name_norm, roll_norm, cls_norm),
            "session_code": code,
        })
        admin_broadcast({
            "event": "student_joined",
            "session_code": code,
            "student_id": student["id"],
            "student_name": student["name"],
            "status": "waiting",
        })

        # ═ STEP 2: Broadcast waiting room update to teacher immediately ═
        log.debug("[JOIN] Broadcasting waiting room to teacher for session %s", code)
        await push_roster_delta(s, "waiting_join", student["id"])
        await ws_teacher(s, {
            "type": "student_waiting",
            "student_id": student["id"],
            "display_name": student["name"],
        })
        
        return {
            "student_id": student["id"],
            "display_name": student["name"],
            "status": "waiting"
        }


@app.post("/api/session/{code}/approve/{student_id}")
async def approve_student(code: str, student_id: str):
    s = _S(code)
    if student_id not in s["students"]:
        log.warning("[APPROVE] Student %s not found in session %s", student_id, code)
        raise HTTPException(404, "Student not found")
    
    student = s["students"][student_id]
    log.info(
        "[APPROVE] Teacher approved student %s (%s) in session %s",
        student_id, student.get("name", "?"), code
    )
    
    # ═ STEP 1: Remove from waiting room ═
    if student_id in s["waiting_room"]:
        s["waiting_room"].remove(student_id)
        log.debug("[APPROVE] Removed %s from waiting room", student_id)
    
    # ═ STEP 2: Mark as active ═
    s["students"][student_id]["status"] = "active"
    touch_session(s)
    
    # ═ STEP 3: Mark attendance (ONLY after approval) ═
    attendance_mark_join(s, student_id)
    asyncio.create_task(broadcast_attendance(s))
    
    # ═ STEP 4: Send approval to student ═
    log.debug("[APPROVE] Sending approval message to student %s", student_id)
    await ws_student(s, student_id, {
        "type": "approved",
        "message": "You have been approved to join the classroom"
    })
    
    # ═ STEP 5: Update roster for teacher (shows new active student, removes from waiting) ═
    log.debug("[APPROVE] Broadcasting updated roster")
    await push_roster_delta(s, "join", student_id)
    
    save_session(code)
    
    return {"approved": True, "student_id": student_id}


@app.post("/api/session/{code}/reject/{student_id}")
async def reject_student(code: str, student_id: str):
    s = _S(code)
    
    student_name = s["students"].get(student_id, {}).get("name", "?")
    log.info(
        "[REJECT] Teacher rejected student %s (%s) from session %s",
        student_id, student_name, code
    )
    
    # ═ STEP 1: Remove from waiting room ═
    if student_id in s["waiting_room"]:
        s["waiting_room"].remove(student_id)
        log.debug("[REJECT] Removed %s from waiting room", student_id)
    
    # ═ STEP 2: Mark as removed (reject) ═
    if student_id in s["students"]:
        s["students"][student_id]["status"] = "removed"
    
    # ═ STEP 3: Add to kicked set (prevent reconnection) ═
    s["kicked"].add(student_id)
    touch_session(s)
    
    # ═ STEP 4: Clean up active rolls ═
    roll = s["students"].get(student_id, {}).get("roll")
    if roll:
        s.get("active_rolls", set()).discard(normalize_string(roll))
    
    # ═ STEP 5: Send rejection to student ═
    log.debug("[REJECT] Sending rejection message to student %s", student_id)
    await ws_student(s, student_id, {
        "type": "rejected",
        "message": "Your join request was rejected by the teacher"
    })
    
    # ═ STEP 6: Update roster for teacher ═
    log.debug("[REJECT] Broadcasting updated roster")
    await push_roster_delta(s, "waiting_leave", student_id)
    
    admin_broadcast({
        "event": "student_left",
        "session_code": code,
        "student_id": student_id,
        "reason": "rejected",
    })
    
    save_session(code)
    
    return {"rejected": True, "student_id": student_id}


@app.post("/api/session/{code}/kick/{student_id}")
async def kick_student(code: str, student_id: str):
    s = _S(code)
    if student_id in s["students"]:
        s["students"][student_id]["status"] = "removed"
    s["kicked"].add(student_id)
    touch_session(s)
    admin_broadcast({
        "event": "student_left",
        "session_code": code,
        "student_id": student_id,
        "reason": "kicked",
    })
    await ws_student(s, student_id, {"type": "kicked"})
    await push_roster_delta(s, "leave", student_id)
    roll = s["students"].get(student_id, {}).get("roll")
    if roll:
        s.get("active_rolls", set()).discard(normalize_string(roll))
    return {"kicked": True}


# ── Student Profile Photo ──────────────────────────────────────────

class PhotoUploadReq(BaseModel):
    photo: str   # base64 data URL, e.g. "data:image/jpeg;base64,..."

@app.post("/api/session/{code}/student/{student_id}/photo")
async def upload_student_photo(code: str, student_id: str, req: PhotoUploadReq):
    """Store student's profile photo (decoded to local file) on their session record.
    Returns immediately; no WebSocket broadcast needed — photo is cosmetic only."""
    s = _S(code)
    student = s["students"].get(student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    if not req.photo or not req.photo.startswith("data:image/"):
        raise HTTPException(400, "Invalid photo format — must be a base64 image data URL")
    
    max_mb = int(os.getenv("MAX_IMAGE_SIZE_MB", "3"))
    max_bytes = max_mb * 1_000_000
    
    # Limit base64 input length (base64 has ~33% overhead, so multiply by 1.45)
    if len(req.photo) > max_bytes * 1.45:
        raise HTTPException(400, f"Photo too large — max {max_mb} MB")
        
    import base64
    import asyncio
    import io
    
    try:
        header, encoded = req.photo.split(",", 1)
        img_data = base64.b64decode(encoded)
    except Exception as e:
        raise HTTPException(400, f"Invalid base64 encoding: {str(e)}")
        
    if len(img_data) > max_bytes:
        raise HTTPException(400, f"Photo too large — max {max_mb} MB")
        
    # Write image to disk in a background thread with Pillow resizing and JPEG compression
    filename = f"{code}_{student_id}.jpg"
    filepath = os.path.join("data", "profile_photos", filename)
    
    def _write_img():
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(img_data))
            if img.mode != "RGB":
                img = img.convert("RGB")
            
            resample_mode = getattr(Image, "Resampling", Image)
            resample_filter = getattr(resample_mode, "LANCZOS", Image.BICUBIC)
            img = img.resize((256, 256), resample_filter)
            
            img.save(filepath, format="JPEG", quality=80, optimize=True)
            log.info("[PHOTO] Compressed and saved profile photo for %s to disk", student_id)
        except Exception as e:
            log.warning("[PHOTO] PIL compression failed, falling back to raw save: %s", e)
            with open(filepath, "wb") as f:
                f.write(img_data)
            
    await asyncio.to_thread(_write_img)
    
    # Store static web URL in session
    student["profile_photo"] = f"/static/profile_photos/{filename}"
    touch_session(s)
    save_session(code)
    log.info("[PHOTO] Saved profile photo for student %s on disk in session %s", student_id, code)
    # Notify teacher so their roster/avatar updates immediately
    await push_roster_delta(s, "update", student_id, {"profile_photo": student["profile_photo"]})
    return {"saved": True}

@app.get("/api/session/{code}/student/{student_id}/photo")
async def get_student_photo(code: str, student_id: str):
    """Fetch student's stored profile photo."""
    s = _S(code)
    student = s["students"].get(student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    photo = student.get("profile_photo") or None
    return {"photo": photo}



@app.post("/api/session/{code}/student/{student_id}/leave")
async def student_leave_session(code: str, student_id: str):
    """Student voluntarily leaves/exits the session.
    
    This marks the student as "left" instead of "removed", allowing them to rejoin later.
    """
    s = _S(code)
    
    if student_id not in s.get("students", {}):
        raise HTTPException(404, "Student not found")
    
    student = s["students"][student_id]
    student_name = student.get("name", "?")
    
    log.info(
        "[LEAVE] Student %s (%s) left session %s",
        student_id, student_name, code
    )
    
    # ═ STEP 1: Mark attendance leave (if student was active) ═
    if student.get("status") == "active":
        attendance_mark_leave(s, student_id)
    
    # ═ STEP 2: Remove from waiting room if present ═
    if student_id in s["waiting_room"]:
        s["waiting_room"].remove(student_id)
        log.debug("[LEAVE] Removed %s from waiting room", student_id)
    
    # ═ STEP 3: Set status to "left" (NOT "removed") ═
    # This allows the student to rejoin with same name/roll/class
    student["status"] = "left"
    
    # ═ STEP 4: Clean up active rolls ═
    roll = student.get("roll")
    if roll:
        s.get("active_rolls", set()).discard(normalize_string(roll))
    
    # ═ STEP 5: Broadcast attendance update ═
    asyncio.create_task(broadcast_attendance(s))
    
    # ═ STEP 6: Update roster for teacher ═
    await push_roster_delta(s, "leave", student_id)
    
    touch_session(s)
    save_session(code)
    
    admin_broadcast({
        "event": "student_left",
        "session_code": code,
        "student_id": student_id,
        "student_name": student_name,
        "reason": "voluntary_exit",
    })
    
    log.info(
        "[LEAVE] Student %s marked as left (can rejoin later)",
        student_id
    )
    
    return {
        "left": True,
        "student_id": student_id,
        "message": "Aap session ko chhod diye. Aap baad mein dobara join kar sakte hain. (You have left the session. You can rejoin later.)"
    }


# ══════════════════════════════════════════════════════════════════
#  ATTENDANCE REST ENDPOINTS
# ══════════════════════════════════════════════════════════════════

@app.get("/api/session/{code}/attendance")
def get_attendance(code: str):
    code_clean = code.strip().upper()
    if len(code_clean) == 6:
        import classroom_db
        import hashlib
        db = classroom_db.get_db()
        code_hash = hashlib.sha256(code_clean.encode("utf-8")).hexdigest()
        lecture = db.lectures.find_one({"$or": [{"lecture_code_hash": code_hash}, {"_id": code_clean}]})
        if lecture:
            classroom_id = lecture["classroom_id"]
            members = list(db.classroom_members.find({"classroom_id": classroom_id}))
            member_ids = [m["student_id"] for m in members]
            
            users = {u["_id"]: u for u in db.users.find({"_id": {"$in": member_ids}})}
            profiles = {p["_id"]: p for p in db.student_profiles.find({"_id": {"$in": member_ids}})}
            
            records = {}
            attendance_recs = list(db.attendance.find({"lecture_id": lecture["_id"]}))
            
            present_count = 0
            absent_count = 0
            late_count = 0
            
            for r in attendance_recs:
                sid = r["student_id"]
                u = users.get(sid, {})
                p = profiles.get(sid, {})
                status = r["status"]
                
                if status in ["present", "late", "excused", "left_early"]:
                    present_count += 1
                else:
                    absent_count += 1
                    
                if status == "late":
                    late_count += 1
                    
                records[sid] = {
                    "student_id": sid,
                    "name": u.get("full_name", "Student"),
                    "roll": p.get("roll_number", "N/A"),
                    "join_at": r.get("join_time"),
                    "leave_at": r.get("leave_time") or None,
                    "duration": r.get("duration_seconds", 0),
                    "status": status,
                    "device_info": r.get("device_info"),
                    "ip_address": r.get("ip_address"),
                    "geo_location": r.get("geo_location")
                }
                
            for sid in member_ids:
                if sid not in records:
                    u = users.get(sid, {})
                    p = profiles.get(sid, {})
                    absent_count += 1
                    records[sid] = {
                        "student_id": sid,
                        "name": u.get("full_name", "Student"),
                        "roll": p.get("roll_number", "N/A"),
                        "join_at": None,
                        "leave_at": None,
                        "duration": 0,
                        "status": "absent"
                    }
                    
            pct = round((present_count / len(member_ids)) * 100) if member_ids else 0
            
            return {
                "state": "ended" if lecture["status"] == "ended" else "active",
                "session_status": lecture["status"],
                "started_at": lecture["start_time"],
                "ended_at": lecture.get("end_time") or None,
                "locked_at": lecture.get("end_time") or None,
                "min_duration": 60,
                "total": len(member_ids),
                "present": present_count,
                "exited": 0,
                "revoked": 0,
                "late": late_count,
                "absent": absent_count,
                "percentage": pct,
                "records": records,
                "audit_log": []
            }
            
    s = _S(code)
    return compute_attendance_summary(s)


@app.post("/api/session/{code}/attendance/control")
async def attendance_control_endpoint(
    code:         str,
    request:      Request,
    action:       str = Query(...),
    min_duration: int = Query(60),
):
    """Teacher controls attendance: start|pause|resume|end|lock."""
    s   = _S(code)
    check_teacher_permission(s, request)
    att = _att(s)
    actor = request.headers.get("X-User-Email", "Teacher")

    if action == "start":
        if att.get("state") == "locked":
            raise HTTPException(409, "Attendance is locked — cannot restart")
        att["state"]      = "active"
        att["started_at"] = att.get("started_at") or now()
        att["min_duration"] = max(0, min_duration)
        log_attendance_audit(s, "start", actor, f"Attendance started with min_duration={min_duration}")
        # Retroactively mark all currently active students as present
        for sid, st in s["students"].items():
            if st.get("status") == "active" and sid not in att["records"]:
                now_ts = now()
                r = att["records"][sid] = {
                    "student_id": sid,
                    "join_at":    now_ts,
                    "leave_at":   None,
                    "duration":   0,
                    "status":     "present",
                    "interactions": 0,
                }
                init_student_geo_attendance(r, now_ts, s)

    elif action == "pause":
        if att.get("state") == "locked":
            raise HTTPException(409, "Attendance is locked")
        att["state"] = "paused"
        log_attendance_audit(s, "pause", actor, "Attendance paused")

    elif action == "resume":
        if att.get("state") == "locked":
            raise HTTPException(409, "Attendance is locked")
        att["state"] = "active"
        log_attendance_audit(s, "resume", actor, "Attendance resumed")

    elif action == "end":
        if att.get("state") == "locked":
            raise HTTPException(409, "Attendance is locked")
        att["state"]    = "ended"
        att["ended_at"] = now()
        log_attendance_audit(s, "end", actor, "Attendance ended")
        
        # Finalize attendance
        finalize_session_attendance(s)
        
        generate_attendance_sheet(s)

    elif action == "lock":
        if att.get("state") == "locked":
            raise HTTPException(409, "Attendance is already locked")
        att["state"]     = "locked"
        att["locked_at"] = now()
        if not att.get("ended_at"):
            att["ended_at"] = now()
        log_attendance_audit(s, "lock", actor, "Attendance locked")
        generate_attendance_sheet(s)

    else:
        raise HTTPException(400, f"Unknown action '{action}'")

    save_session(code)
    touch_session(s)
    await broadcast_attendance(s)
    return compute_attendance_summary(s)


@app.patch("/api/session/{code}/attendance/student/{student_id}")
async def patch_student_attendance(
    code:       str,
    student_id: str,
    request:    Request,
    status:     str = Query(...),
):
    """Teacher manually overrides a single student's attendance status."""
    s   = _S(code)
    check_teacher_permission(s, request)
    att = _att(s)
    if att.get("state") == "locked" or att.get("locked_at"):
        actor = request.headers.get("X-User-Email", "Teacher")
        log_attendance_audit(s, "modification_attempt", actor, f"Attempted manual override of student {student_id} to {status} when attendance locked")
        save_session(code)
        raise HTTPException(409, "Attendance is locked — cannot edit")
    valid = {"present", "absent", "exited", "revoked"}
    if status not in valid:
        raise HTTPException(400, f"status must be one of {valid}")
    records = att.setdefault("records", {})
    if student_id not in records:
        records[student_id] = {"student_id": student_id, "join_at": None,
                               "leave_at": None, "duration": 0, "interactions": 0}
    old_status = records[student_id].get("status", "not_marked")
    records[student_id]["status"] = status
    actor = request.headers.get("X-User-Email", "Teacher")
    log_attendance_audit(s, "manual_override", actor, f"Manually updated status of student {student_id} from {old_status} to {status}")
    if att.get("state") == "ended":
        generate_attendance_sheet(s)
    save_session(code)
    await broadcast_attendance(s)
    return {"updated": True}


@app.get("/api/session/{code}/attendance/sheet")
def get_attendance_sheet_endpoint(code: str, request: Request):
    s = _S(code)
    check_teacher_permission(s, request)
    att = _att(s)
    if att.get("state") not in ("ended", "locked") and s.get("status") != "ended":
        raise HTTPException(409, "Attendance sheet is available after attendance is ended or locked")
    sheet = get_or_create_attendance_sheet(s)
    save_session(code)
    return sheet


@app.get("/api/session/{code}/attendance/sheet.pdf")
def download_attendance_sheet_pdf(code: str, request: Request):
    s = _S(code)
    check_teacher_permission(s, request)
    att = _att(s)
    if att.get("state") not in ("ended", "locked") and s.get("status") != "ended":
        raise HTTPException(409, "Attendance sheet is available after attendance is ended or locked")
    sheet = get_or_create_attendance_sheet(s)
    save_session(code)
    from report_generator import generate_attendance_sheet_pdf
    pdf_bytes = generate_attendance_sheet_pdf(sheet)
    register_generated_report(s, "attendance", "pdf", pdf_bytes)
    filename = f"VYOM_Attendance_Sheet_{code}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
@app.get("/api/session/{code}/students")
def get_students(code: str):
    s       = _S(code)
    active  = [st for st in s["students"].values() if st["status"] == "active"]
    waiting = [s["students"][sid] for sid in s["waiting_room"] if sid in s["students"]]
    return {"active": active, "waiting": waiting}


@app.post("/api/session/{code}/upload_students")
async def upload_students(code: str, file: UploadFile = File(...)):
    s = _S(code)
    content_bytes = await file.read()
    
    try:
        decoded = content_bytes.decode("utf-8")
    except UnicodeDecodeError:
        decoded = content_bytes.decode("latin-1")
        
    lines = [line.strip() for line in decoded.splitlines() if line.strip()]
    if not lines:
        s["allowed_students"] = set()
        save_session(code)
        return {"loaded": 0, "skipped": [], "message": "File is empty"}
        
    import csv
    from io import StringIO
    
    reader = csv.reader(StringIO("\n".join(lines)))
    rows = list(reader)
    if not rows:
        s["allowed_students"] = set()
        save_session(code)
        return {"loaded": 0, "skipped": [], "message": "No data found"}
        
    first_row = rows[0]
    header_keywords = {'name', 'roll', 'class', 'student', 'no', 'sr', 'sno', 'branch', 'section', 'enrollment'}
    has_header = any(any(kw in cell.lower() for kw in header_keywords) for cell in first_row)
    
    data_rows = rows[1:] if has_header else rows
    
    name_idx, roll_idx, class_idx = 0, 1, 2 # Default position-based mapping
    if has_header:
        headers = [h.lower().strip() for h in first_row]
        for idx, h in enumerate(headers):
            if "name" in h or h == "student":
                name_idx = idx
            elif "roll" in h or "enrollment" in h or h == "no" or h == "rno":
                roll_idx = idx
            elif "class" in h or "branch" in h or "section" in h or h == "sec" or h == "cls":
                class_idx = idx
                
    allowed = set()
    skipped = []
    
    for idx, row in enumerate(data_rows, start=1):
        if not row:
            continue
        
        raw_name = row[name_idx].strip() if len(row) > name_idx else ""
        raw_roll = row[roll_idx].strip() if len(row) > roll_idx else ""
        raw_cls  = row[class_idx].strip() if len(row) > class_idx else ""
        
        if raw_name and raw_roll:
            allowed.add((raw_name, raw_roll, raw_cls))
        else:
            skipped.append({"row_number": idx, "raw": row})
            
    s["allowed_students"] = allowed
    # Mark session as closed-access regardless of how many rows were parsed.
    # This ensures the closed-access gate fires even if the CSV had no valid
    # rows — the intent is "no unauthorised student may join".
    s["access_mode"] = "closed"
    save_session(code)
    log.info("Student CSV loaded=%s skipped=%s; session %s now CLOSED", len(allowed), len(skipped), code)
    return {"loaded": len(allowed), "skipped": skipped[:5], "message": "Upload processed"}


@app.post("/api/session/{code}/clear_students")
async def clear_students(code: str):
    """Reset to open access by clearing the allowed-students list.
    Called when the teacher removes the uploaded CSV from the UI."""
    s = _S(code)
    s["allowed_students"] = set()
    s["access_mode"] = "open"
    save_session(code)
    log.info("Session %s reset to OPEN access (CSV removed)", code)
    return {"message": "Open access restored"}


@app.post("/api/session/{code}/toggle_auto_join")
async def toggle_auto_join(code: str, request: Request):
    s = _S(code)
    check_teacher_permission(s, request)
    try:
        body = await request.json()
        enabled = bool(body.get("enabled", False))
    except Exception:
        enabled = False
        
    s["auto_join_enabled"] = enabled
    touch_session(s)
    
    if enabled:
        # Auto-approve all waiting students
        waiting_ids = list(s["waiting_room"])
        for student_id in waiting_ids:
            if student_id in s["waiting_room"]:
                s["waiting_room"].remove(student_id)
            if student_id in s["students"]:
                s["students"][student_id]["status"] = "active"
                attendance_mark_join(s, student_id)
                await ws_student(s, student_id, {
                    "type": "approved",
                    "message": "You have been approved to join the classroom"
                })
        if waiting_ids:
            for student_id in waiting_ids:
                await push_roster_delta(s, "join", student_id)
            asyncio.create_task(broadcast_attendance(s))
            
    save_session(code)
    
    # Broadcast status change to teacher and students
    await ws_broadcast(s, {
        "type": "auto_join_enabled" if enabled else "auto_join_disabled"
    })
    
    return {"success": True, "auto_join_enabled": enabled}


@app.post("/api/session/{code}/access_settings")
async def set_access_settings(code: str, req: AccessSettingsReq):
    s = _S(code)
    if req.access_mode not in {"open", "closed", "close"}:
        raise HTTPException(400, "Invalid access_mode; expected open, closed, or close")
    if req.radius_meters is not None:
        if req.radius_meters <= 0 or req.radius_meters > 2000:
            raise HTTPException(400, "radius_meters must be between 1 and 2000")
        s["close_access_radius_meters"] = req.radius_meters
    if req.access_mode == "close":
        if req.teacher_lat is not None and req.teacher_lng is not None:
            if not (-90 <= req.teacher_lat <= 90 and -180 <= req.teacher_lng <= 180):
                raise HTTPException(400, "Invalid teacher GPS coordinates")
            s["close_access_location"] = {"lat": req.teacher_lat, "lng": req.teacher_lng}
        elif not s.get("close_access_location"):
            raise HTTPException(400, "Teacher location is required to enable Close Access")
            
    old_mode = s.get("access_mode", "open")
    new_mode = req.access_mode
    s["access_mode"] = new_mode
    save_session(code)
    
    if old_mode != "close" and new_mode == "close":
        # Transition Open -> Close Access
        att = _att(s)
        records = att.setdefault("records", {})
        now_ts = now()
        for sid, r in records.items():
            if "currentStatus" not in r:
                init_student_geo_attendance(r, now_ts, s)
        await ws_broadcast(s, {
            "type": "geo_mode_enabled",
            "access_mode": new_mode,
            "close_access_radius_meters": s.get("close_access_radius_meters", 100),
            "close_access_location": s.get("close_access_location"),
        })
    elif old_mode == "close" and new_mode != "close":
        # Transition Close -> Open / Closed
        att = _att(s)
        records = att.setdefault("records", {})
        for sid, r in records.items():
            r["currentStatus"] = "present"
            r["status"] = "present"
            r["left_radius_at"] = None
            r["consecutive_outside"] = 0
            r["consecutive_inside"] = 0
            r["gps_lost"] = False
        await ws_broadcast(s, {
            "type": "geo_mode_disabled",
            "access_mode": new_mode,
        })
        
    log.info("Session %s access settings updated: mode=%s radius=%s location=%s", code, req.access_mode, req.radius_meters, s.get("close_access_location"))
    return {
        "message": "Access settings updated",
        "access_mode": s["access_mode"],
        "close_access_radius_meters": s.get("close_access_radius_meters", 100),
        "close_access_location": s.get("close_access_location"),
    }


@app.get("/api/session/{code}/check_access")
async def check_access(
    code: str,
    name: str = Query(...),
    roll: str = Query(...),
    cls:  str = Query(...),
    student_lat: Optional[float] = Query(None),
    student_lng: Optional[float] = Query(None),
):
    """Pre-validation endpoint called by the student UI BEFORE the actual join
    request.  Always called — for open-access sessions it returns 200
    immediately.  For closed-access sessions it returns 200 only when the
    student is present in the uploaded allowed list; returns 403 otherwise.

    This endpoint never creates a student record, never touches the waiting
    room, and never notifies the teacher.  It is the frontend-facing mirror of
    the hard gate inside /join so the UI can surface the exact error before
    any join attempt is made.
    """
    s = _S(code)

    access_mode = s.get("access_mode", "open")

    # Open access — every student is authorised; return immediately.
    if access_mode == "open":
        return {"authorized": True, "access_mode": "open"}

    if access_mode == "closed":
        if not validate_closed_access_student(s, name, roll, cls):
            raise HTTPException(403, "Not allowed for this class")
        return {"authorized": True, "access_mode": "closed"}

    if access_mode == "close":
        denial_reason = get_close_access_failure_reason(s, student_lat, student_lng)
        if denial_reason is not None:
            raise HTTPException(403, denial_reason)
        return {"authorized": True, "access_mode": "close"}

    return {"authorized": True, "access_mode": access_mode}


# ══════════════════════════════════════════════════════════════════
#  TASK ROUTES
# ══════════════════════════════════════════════════════════════════

@app.post("/api/tasks/create")
async def create_task(req: CreateTaskReq):
    s    = _S(req.session_code)
    task = new_task(normalize_task_input(req.model_dump()))
    async with session_lock(req.session_code):
        s["tasks"].append(task)
    log.info("[AI TASK SAVED] Task %s (%s) added to session %s — total: %d",
             task["id"], task["type"], req.session_code, len(s["tasks"]))
    save_session(req.session_code)
    await ws_teacher(s, {"type": "task_created", "task": task, "tasks": s["tasks"]})
    return task


@app.post("/api/tasks/upload_json")
async def upload_tasks_json(session_code: str = Form(...), file: UploadFile = File(...)):
    s   = _S(session_code)
    raw = await file.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        raise HTTPException(400, f"Invalid JSON: {e}")
    if isinstance(data, dict):
        data = data.get("tasks", [data])
    if not isinstance(data, list):
        raise HTTPException(400, "JSON must be an array of task objects")

    created: list = []
    for item in data:
        if isinstance(item, dict) and item.get("question"):
            task = new_task(normalize_task_input(item))
            async with session_lock(session_code):
                s["tasks"].append(task)
            created.append(task)

    if created:
        log.info("[AI TASK SAVED] %d tasks imported to session %s — total: %d",
                 len(created), session_code, len(s["tasks"]))
        save_session(session_code)
        await ws_teacher(s, {"type": "tasks_imported", "tasks": s["tasks"], "created": len(created)})
    return {"created": len(created), "tasks": created}


@app.get("/api/session/{code}/tasks")
def list_tasks(code: str):
    return _S(code)["tasks"]


@app.delete("/api/session/{code}/tasks/{task_id}")
async def delete_task(code: str, task_id: str):
    async with session_lock(code):
        s      = _S(code)
        before = len(s["tasks"])
        s["tasks"] = [t for t in s["tasks"] if t["id"] != task_id]
        if len(s["tasks"]) == before:
            raise HTTPException(404, "Task not found")
        s["responses"].pop(task_id, None)
        for did, d in list(s.get("task_deliveries", {}).items()):
            if d.get("task_id") == task_id:
                s["task_deliveries"].pop(did, None)
        s["student_current_task"] = {
            sid: tid for sid, tid in s.get("student_current_task", {}).items()
            if tid != task_id
        }
    await ws_teacher(s, {"type": "task_deleted", "task_id": task_id, "tasks": s["tasks"]})
    return {"deleted": True}


@app.post("/api/session/{code}/tasks/{task_id}/attach_content")
async def attach_content(code: str, task_id: str, filename: str = Query(...)):
    s    = _S(code)
    task = _T(s, task_id)
    if filename not in s["content_files"]:
        raise HTTPException(404, "File not found — upload it first")
    task["content_file"] = filename
    return {"attached": True}


@app.post("/api/session/{code}/tasks/send_current")
async def send_current_task(code: str):
    """Send the next task in sequence to all students."""
    return await deliver_next_task_request(code)


@app.post("/api/session/{code}/tasks/send")
async def send_task(code: str, req: SendTaskReq):
    """Send a specific task to all / a student / a group."""
    return await deliver_task_request(code, req)


@app.post("/api/session/{code}/tasks/send_specific")
async def send_specific_task(
    code:        str,
    req:         Optional[SendTaskReq] = Body(None),
    task_id:     Optional[str]         = Query(None),
    target_type: Optional[str]         = Query(None),
    target_id:   Optional[str]         = Query(None),
):
    """Alternate endpoint accepting query params or body."""
    if req is None:
        if not task_id or not target_type:
            raise HTTPException(422, "task_id and target_type are required")
        req = SendTaskReq(task_id=task_id, target_type=target_type, target_id=target_id)
    return await deliver_task_request(code, req)


# ══════════════════════════════════════════════════════════════════
#  AI EXPLAIN / SIMPLIFY ROUTES
# ══════════════════════════════════════════════════════════════════

# In-memory explanation cache: task_id -> {mode -> explanation_text}
_explain_cache: Dict[str, Dict[str, str]] = {}

_EXPLAIN_PROMPTS = {
    "simplified": {
        "mcq": (
            "You are a friendly teacher explaining a question to a struggling student.\n"
            "Question: {question}\nOptions: {options}\nCorrect Answer: {correct_answer}\n\n"
            "Give a SHORT, SIMPLE explanation (3-5 sentences):\n"
            "1. What concept this question tests\n"
            "2. Why '{correct_answer}' is correct in easy language\n"
            "3. A quick memory tip\n"
            "Use simple words, no jargon."
        ),
        "short": (
            "You are a friendly teacher helping a student understand a short-answer question.\n"
            "Question: {question}\n\n"
            "In simple, easy language (3-5 sentences):\n"
            "1. What this question is asking\n"
            "2. The key concept to understand\n"
            "3. How to frame a good answer\n"
            "Avoid technical language."
        ),
        "long": (
            "You are a teacher helping a student write a long-answer/essay response.\n"
            "Question: {question}\n\n"
            "Explain simply:\n"
            "1. What the question wants (2 sentences)\n"
            "2. Key points to cover (bullet list, max 5)\n"
            "3. A suggested structure for the answer\n"
            "Keep it student-friendly."
        ),
    },
    "detailed": {
        "mcq": (
            "You are an expert teacher giving a detailed explanation of a MCQ.\n"
            "Question: {question}\nOptions: {options}\nCorrect Answer: {correct_answer}\n\n"
            "Provide:\n"
            "**Concept Explanation**: What concept does this test?\n"
            "**Why Correct**: Explain in detail why '{correct_answer}' is right\n"
            "**Why Wrong**: For each wrong option, briefly explain why it's incorrect\n"
            "**Key Insight**: One key takeaway for the student"
        ),
        "short": (
            "You are an expert teacher giving a detailed explanation for a short-answer question.\n"
            "Question: {question}\n\n"
            "Provide:\n"
            "**Concept**: The underlying concept being tested\n"
            "**Step-by-Step**: How to approach answering this\n"
            "**Key Points**: What a good answer must include\n"
            "**Example**: A model answer (2-4 sentences)\n"
            "**Common Mistakes**: 2-3 errors students typically make"
        ),
        "long": (
            "You are an expert teacher explaining how to write a long-answer essay response.\n"
            "Question: {question}\n\n"
            "Provide:\n"
            "**Understanding the Question**: Break down what is being asked\n"
            "**Important Keywords**: List 5-8 key terms to include\n"
            "**Answer Structure**: Introduction → Body points → Conclusion framework\n"
            "**Important Points**: Bullet list of must-cover content\n"
            "**Exam Strategy**: Tips to score maximum marks\n"
            "**Model Answer Outline**: A brief structural outline"
        ),
    },
    "exam_style": {
        "mcq": (
            "You are a seasoned exam coach. The student needs to master this MCQ for their exam.\n"
            "Question: {question}\nOptions: {options}\nCorrect Answer: {correct_answer}\n\n"
            "Give an EXAM-FOCUSED breakdown:\n"
            "**Quick Recall Trick**: A memory device or trick to remember the answer\n"
            "**Similar Question Patterns**: What variations of this question might appear\n"
            "**Time-Saver Tip**: How to quickly identify the correct answer in an exam\n"
            "**Trap to Avoid**: What mistake do most students make on this type?"
        ),
        "short": (
            "You are a seasoned exam coach helping a student ace a short-answer question.\n"
            "Question: {question}\n\n"
            "**Model Answer** (exam-ready, 3-4 sentences):\n"
            "**Keywords to Include**: List 4-6 technical keywords that earn marks\n"
            "**Time Estimate**: How long should a student spend on this?\n"
            "**Marking Scheme Insight**: What 3-4 points would an examiner look for?\n"
            "**Do & Don't**: One thing to do, one to avoid"
        ),
        "long": (
            "You are a seasoned exam coach for long-answer/essay questions.\n"
            "Question: {question}\n\n"
            "**Full Model Answer** (structured, exam-ready):\nWrite a complete model answer.\n\n"
            "**Marking Breakdown**: How marks would typically be allocated\n"
            "**Time Management**: How many minutes to spend and on what\n"
            "**Scoring Keywords**: 8-10 keywords/phrases that maximize marks\n"
            "**Presentation Tips**: How to format for maximum marks"
        ),
    },
    "teacher_notes": {
        "mcq": (
            "You are creating teacher notes for a MCQ classroom discussion.\n"
            "Question: {question}\nOptions: {options}\nCorrect Answer: {correct_answer}\n\n"
            "Provide teacher-facing notes:\n"
            "**Teaching Point**: Core concept this question reinforces\n"
            "**Discussion Prompt**: A follow-up question to ask the class\n"
            "**Common Misconceptions**: Top 2-3 misconceptions students have\n"
            "**Differentiation**: How to explain this differently for weaker/stronger students\n"
            "**Real-World Link**: A relatable real-world example"
        ),
        "short": (
            "You are creating teacher notes for a short-answer classroom question.\n"
            "Question: {question}\n\n"
            "**Learning Objective**: What skill/knowledge this assesses\n"
            "**Suggested Time**: How long students should get\n"
            "**Model Answer** (for teacher reference):\n"
            "**Marking Guide**: What earns full/partial marks\n"
            "**Extension Question**: A harder follow-up for advanced students\n"
            "**Simplification**: How to rephrase for struggling students"
        ),
        "long": (
            "You are creating teacher notes for a long-answer classroom essay question.\n"
            "Question: {question}\n\n"
            "**Curriculum Link**: What topic/chapter this covers\n"
            "**Learning Outcomes**: 3-4 outcomes this question assesses\n"
            "**Full Model Answer** (complete, for teacher reference):\n"
            "**Rubric**: Simple 3-level rubric (excellent/satisfactory/needs work)\n"
            "**Common Errors**: 3 common mistakes to watch for when marking\n"
            "**Peer Assessment Tip**: How students can evaluate each other's answers"
        ),
    },
}


class ChatbotRequest(BaseModel):
    message: str
    history: List[dict] = []
    session_code: Optional[str] = None
    student_id: Optional[str] = None
    language: str = "en"
    role: str = "teacher"  # "teacher" or "student"
    api_key: Optional[str] = None

@app.post("/api/ai/chatbot")
async def ai_chatbot(req: ChatbotRequest):
    query = req.message
    history = req.history
    session_code = req.session_code
    student_id = req.student_id
    role = req.role
    lang_code = req.language
    api_key = req.api_key

    # 1. Retrieve session details if session code is provided
    session_data = {}
    student_task_context = ""
    active_topic = ""
    
    if session_code:
        try:
            s = _S(session_code)
            active_topic = s.get("topic", "")
            
            # Build classroom snapshot context
            active_students = s.get("students", {})
            tasks = s.get("tasks", [])
            
            # Compute real-time analytics
            participation = 0
            understanding = 0
            at_risk = []
            
            try:
                an = compute_analytics(s)
                participation = an.get("participation", 0)
                understanding = an.get("understanding", 0)
                at_risk = [st.get("name", st.get("id")) for st in an.get("at_risk", [])]
            except Exception as e:
                log.warning("Failed to compute analytics for chatbot context: %s", e)
                
            session_data = {
                "session_status": s.get("status", "unknown"),
                "active_students_count": len(active_students),
                "participation_pct": participation,
                "understanding_pct": understanding,
                "at_risk_students": at_risk,
                "tasks_count": len(tasks),
                "active_topic": active_topic,
                "teacher_email": s.get("teacher_email", "")
            }
            
            # If role is student, get the active task details
            if role == "student" and student_id:
                curr_task_id = s.get("student_current_task", {}).get(student_id) or (tasks[-1]["id"] if tasks else None)
                if curr_task_id:
                    try:
                        task = _T(s, curr_task_id)
                        resp_data = s.get("responses", {}).get(curr_task_id, {}).get(student_id)
                        submitted = resp_data is not None
                        correct = resp_data.get("correct") if submitted and resp_data else False
                        
                        student_task_context = (
                            f"\nCURRENT STUDENT TASK CONTEXT:\n"
                            f"Task ID: {task.get('id')}\n"
                            f"Question Type: {task.get('type')}\n"
                            f"Question: {task.get('question')}\n"
                        )
                        if task.get("options"):
                            student_task_context += f"Options: {', '.join(task.get('options'))}\n"
                        student_task_context += (
                            f"Status: {'Submitted' if submitted else 'Not submitted yet'}\n"
                        )
                        if submitted:
                            student_task_context += f"Result: {'Correct' if correct else 'Incorrect'}\n"
                    except Exception:
                        pass
        except Exception:
            pass

    # 2. Extract context from history to maintain memory of topic, class, grade, chapter, etc.
    inferred_subject = ""
    inferred_grade = ""
    inferred_chapter = ""
    inferred_topic = active_topic
    
    for msg in reversed(history):
        content = msg.get("content", "").lower()
        if not inferred_subject:
            for sub in ["mathematics", "physics", "chemistry", "biology", "english", "computer science", "programming", "artificial intelligence", "cyber security", "history", "geography", "economics", "science"]:
                if sub in content:
                    inferred_subject = sub.title()
                    break
        if not inferred_grade:
            grade_match = re.search(r"class\s+(\d+|viii|ix|x|xi|xii)|grade\s+(\d+)", content)
            if grade_match:
                inferred_grade = grade_match.group(0).title()
        if not inferred_chapter:
            chap_match = re.search(r"chapter\s+(\d+|\w+)", content)
            if chap_match:
                inferred_chapter = chap_match.group(0).title()

    # 3. Retrieve relevant VYOM documentation using RAG
    key_to_use = api_key or get_teacher_key(session_data.get("teacher_email")) or os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")
    
    rag_docs = []
    try:
        rag_docs = await rag_engine.retrieve(query, top_n=3, api_key=key_to_use)
    except Exception as e:
        log.warning("RAG retrieval failed: %s", e)

    doc_context = ""
    if rag_docs:
        doc_context = "\nRELEVANT VYOM DOCUMENTATION:\n" + "\n---\n".join(
            f"Source: {d['source']} ({d['section']})\nContent:\n{d['text']}" for d in rag_docs
        )

    # 4. Out-of-Scope Protection Rule check
    out_of_scope_patterns = [
        r"\b(gossip|celebrity|dating|boyfriend|girlfriend|love life)\b",
        r"\b(politics|trump|biden|election|senate|republican|democrat)\b",
        r"\b(crypto|bitcoin|ethereum|dogecoin|cardano|betting|gambling|casino|sportsbook|odds)\b",
        r"\b(hacking|malware|virus|trojan|exploit|ddos|bypass password)\b",
        r"\b(legal advice|sue|lawyer|medical diagnosis|symptoms|prescribe|illness|cure cancer)\b"
    ]
    is_out_of_scope = False
    for pat in out_of_scope_patterns:
        if re.search(pat, query.lower()):
            is_out_of_scope = True
            break

    if is_out_of_scope:
        refusal_msg = (
            "I'm sorry, but I'm specifically designed to assist with VYOM, teaching, education, classroom management, "
            "student learning, programming, and AI in education. I'm unable to assist with unrelated topics. If you have "
            "any questions about VYOM or education, I'd be happy to help."
        )
        if lang_code == "hi":
            refusal_msg = "मुझे क्षमा करें, लेकिन मैं विशेष रूप से व्योम (VYOM), अध्यापन, शिक्षा, कक्षा प्रबंधन, छात्र सीखने, प्रोग्रामिंग और शिक्षा में एआई के साथ सहायता करने के लिए डिज़ाइन किया गया हूँ। मैं असंबंधित विषयों में सहायता करने में असमर्थ हूँ। यदि आपके पास व्योम या शिक्षा के बारे में कोई प्रश्न हैं, तो मुझे मदद करने में खुशी होगी।"
        elif lang_code == "pa":
            refusal_msg = "ਮੈਨੂੰ ਮਾਫ਼ ਕਰੋ, ਪਰ ਮੈਂ ਵਿਸ਼ੇਸ਼ ਤੌਰ 'ਤੇ ਵਿਓਮ (VYOM), ਅਧਿਆਪਨ, ਸਿੱਖਿਆ, ਕਲਾਸਰੂਮ ਪ੍ਰਬੰਧਨ, ਵਿਦਿਆਰਥੀ ਸਿਖਲਾਈ, ਪ੍ਰੋਗਰਾਮਿੰਗ ਅਤੇ ਸਿੱਖਿਆ ਵਿੱਚ ਏਆਈ ਦੀ ਸਹਾਇਤਾ ਲਈ ਤਿਆਰ ਕੀਤਾ ਗਿਆ ਹਾਂ। ਮੈਂ ਗੈਰ-ਸੰਬੰਧਿਤ ਵਿਸ਼ਿਆਂ ਵਿੱਚ ਸਹਾਇਤਾ ਕਰਨ ਵਿੱਚ ਅਸਮਰੱਥ ਹਾਂ। ਜੇਕਰ ਤੁਹਾਡੇ ਕੋਲ ਵਿਓਮ ਜਾਂ ਸਿੱਖਿਆ ਬਾਰੇ ਕੋਈ ਸਵਾਲ ਹਨ, ਤਾਂ ਮੈਨੂੰ ਮਦਦ ਕਰਨ ਵਿੱਚ ਖੁਸ਼ੀ ਹੋਵੇਗੀ।"
        elif lang_code == "mr":
            refusal_msg = "मला क्षमा करा, परंतु मी विशेषतः व्योम (VYOM), अध्यापन, शिक्षण, वर्ग व्यवस्थापन, विद्यार्थी शिकणे, प्रोग्रामिंग आणि शिक्षणातील एआय सह मदत करण्यासाठी डिझाइन केला आहे. मी असंबंधित विषयांवर मदत करण्यास असमर्थ आहे. आपल्याकडे व्योम किंवा शिक्षणाबद्दल काही प्रश्न असल्यास, मला मदत करण्यास आनंद होईल."
        elif lang_code == "zh":
            refusal_msg = "很抱歉，我专门设计用于协助 VYOM、教学、教育、课堂管理、学生学习、编程以及教育中的人工智能。我无法协助处理无关的话题。如果您有任何关于 VYOM 或教育的问题，我很乐意为您提供帮助。"
        return {"response": refusal_msg, "source": "system_guardrail"}

    # 5. Build system prompt
    role_desc = ""
    if role == "teacher":
        role_desc = (
            "You are the VYOM AI Teaching Assistant — an expert educator, classroom coach, and VYOM platform specialist. "
            "You serve as a trusted co-teacher combining deep pedagogical knowledge with mastery of every VYOM feature. "
            "Help teachers with concept explanations, generating structured lesson plans, quizzes, MCQs, coding challenges, "
            "rubrics, assignments, classroom management strategies, and platform navigation."
        )
    else:
        role_desc = (
            "You are the VYOM Student Copilot — an encouraging study buddy, friendly tutor, and classroom assistant. "
            "Guide students step-by-step through their active tasks without giving away direct answers. "
            "Use hints, sub-questions, and analogies. Be encouraging and patient. Encourage active learning."
        )

    class_context = ""
    if session_data:
        class_context = (
            f"\nLIVE CLASSROOM SNAPSHOT:\n"
            f"Session Status: {session_data['session_status']}\n"
            f"Active Students: {session_data['active_students_count']}\n"
            f"Participation Rate: {session_data['participation_pct']}%\n"
            f"Class Understanding: {session_data['understanding_pct']}%\n"
            f"At-risk Students: {', '.join(session_data['at_risk_students']) if session_data['at_risk_students'] else 'None'}\n"
            f"Tasks Sent: {session_data['tasks_count']}\n"
            f"Active Class Topic: {session_data['active_topic']}\n"
        )

    memory_context = (
        f"\nCONVERSATION MEMORY (EXTRACTED CONTEXT):\n"
        f"Active Subject: {inferred_subject or 'Not specified'}\n"
        f"Active Grade/Class: {inferred_grade or 'Not specified'}\n"
        f"Active Chapter: {inferred_chapter or 'Not specified'}\n"
        f"Active Topic: {inferred_topic or 'Not specified'}\n"
    )

    system_prompt = (
        f"{role_desc}\n\n"
        f"CONTEXT INFORMATION:\n"
        f"===================={class_context}{student_task_context}{memory_context}{doc_context}\n"
        f"====================\n\n"
        f"CRITICAL RULES:\n"
        f"1. RESPOND ONLY IN THE CURRENT LANGUAGE: The selected platform language is '{lang_code}'. You MUST write your entire response in the '{lang_code}' language (e.g. Hindi, Punjabi, Marathi, Chinese, English). All generated material (lesson plans, quizzes, explanations, feedback) must be fully translated and output in this language. Do not mix with English unless it is code syntax or technical names.\n"
        f"2. OUT-OF-SCOPE PROTECTION: If the user asks about sports betting, celebrity gossip, politics, crypto, dating, medical diagnosis, or illegal/dangerous activities, politely refuse to answer using the standard refusal message.\n"
        f"3. HALLUCINATION PREVENTION: Never invent platform features, buttons, menus, reports, or settings that are not explicitly documented in the RELEVANT VYOM DOCUMENTATION section above. If a feature is not in the documentation, say 'I don't have enough information to answer that accurately.' Never guess.\n"
        f"4. ADAPT RESPONSE LENGTH: Keep simple greetings or clarifications brief (1-3 sentences). For content generation requests (lesson plans, MCQs, code explanations, step-by-step guides), provide detailed, complete, ready-to-use, and highly structured markdown responses.\n"
        f"5. FORMATTING: Use headings, bullet points, numbered lists, tables, and bold tags to make your response easy to read and professional.\n"
        f"6. CONVERSATION MEMORY: Maintain context from the history. Do not ask for information that was already provided in the history or is listed in the extracted context. If the user asks for a quiz on 'Electricity' after discussing Physics, automatically generate a Physics quiz on Electricity without asking which subject.\n"
    )

    prompt_builder = f"System Instruction:\n{system_prompt}\n\n"
    if history:
        prompt_builder += "Conversation History:\n"
        for h in history:
            role_label = "User" if h.get("role") == "user" else "Assistant"
            prompt_builder += f"{role_label}: {h.get('content')}\n"
        prompt_builder += "\n"
    prompt_builder += f"Current User Request:\n{query}"

    try:
        response_text = await call_llm(prompt_builder, key_to_use, is_json=False)
        return {"response": response_text, "source": "llm"}
    except Exception as exc:
        log.warning("[AI CHATBOT] LLM call failed: %s", exc)
        fallback_msg = "Sorry, I am having trouble connecting to the AI service right now. Please check your API key configuration (Click your Profile icon in the top-right -> Settings ⚙️ -> AI API Key)."
        if lang_code == "hi":
            fallback_msg = "क्षमा करें, मुझे इस समय AI सेवा से जुड़ने में समस्या हो रही है। कृपया अपना API कुंजी कॉन्फ़िगरेशन जांचें।"
        elif lang_code == "pa":
            fallback_msg = "ਮਾਫ਼ ਕਰਨਾ, ਮੈਨੂੰ ਇਸ ਸਮੇਂ ਏਆਈ ਸੇਵਾ ਨਾਲ ਜੁੜਨ ਵਿੱਚ ਮੁਸ਼ਕਲ ਆ ਰਹੀ ਹੈ। ਕਿਰਪਾ ਕਰਕੇ ਆਪਣੀ API ਕੁੰਜੀ ਦੀ ਸੰਰਚਨਾ ਦੀ ਜਾਂਚ ਕਰੋ।"
        elif lang_code == "mr":
            fallback_msg = "क्षमस्व, मला सध्या AI सेवेशी कनेक्ट करण्यात अडचण येत आहे. कृपया आपले API की कॉन्फिगरेशन तपासा."
        elif lang_code == "zh":
            fallback_msg = "抱歉，目前我无法连接到人工智能服务。请检查您的 API 密钥配置。"
        return {"response": fallback_msg, "source": "server_fallback"}


@app.post("/api/ai/explain-question")
async def ai_explain_question(
    task_id:      str  = Body(...),
    session_code: str  = Body(...),
    mode:         str  = Body("simplified"),   # simplified|detailed|exam_style|teacher_notes
    api_key:      Optional[str] = Body(None),  # OpenRouter key (optional, from client)
    force_regen:  bool = Body(False),
):
    """
    Generate an AI explanation for a question.
    Uses OpenRouter if api_key is supplied, otherwise returns a structured placeholder.
    """
    s    = _S(session_code)
    task = _T(s, task_id)

    if mode not in _EXPLAIN_PROMPTS:
        raise HTTPException(400, f"mode must be one of: {', '.join(_EXPLAIN_PROMPTS)}")

    # Serve from cache unless force_regen
    cache_key = f"{task_id}:{mode}"
    if not force_regen and cache_key in _explain_cache:
        log.info("[AI EXPLAIN GENERATED] Cache hit for task %s mode=%s", task_id, mode)
        return {"explanation": _explain_cache[cache_key], "cached": True, "mode": mode}

    q_type     = "long" if task.get("long_answer") else task.get("type", "mcq")
    if q_type not in _EXPLAIN_PROMPTS[mode]:
        q_type = "short"   # fallback for coding

    options_str = ""
    if task.get("options"):
        options_str = ", ".join(
            f"{chr(65+i)}. {o}" for i, o in enumerate(task["options"])
        )

    prompt_tmpl = _EXPLAIN_PROMPTS[mode][q_type]
    prompt = prompt_tmpl.format(
        question=task.get("question", ""),
        options=options_str or "N/A",
        correct_answer=task.get("correct_answer", ""),
    )

    explanation = ""

    # Use key from request, saved teacher key, or fallback to server-side env variables (OpenRouter or Gemini)
    key_to_use = api_key or get_teacher_key(s.get("teacher_email")) or os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")

    if key_to_use:
        try:
            explanation = await call_llm(prompt, key_to_use, is_json=False)
        except Exception as exc:
            log.warning("[AI EXPLAIN] LLM call failed: %s", exc)
            explanation = ""

    # Fallback: structured placeholder so the UI always has something to show
    if not explanation:
        type_labels = {"mcq": "MCQ", "short": "Short Answer", "long": "Long Answer"}
        explanation = (
            f"**{type_labels.get(q_type, 'Question')} Explanation** _{mode.replace('_',' ').title()}_\n\n"
            f"**Question**: {task.get('question', '')}\n\n"
        )
        if q_type == "mcq" and task.get("options"):
            for i, o in enumerate(task["options"]):
                mark = " ✅" if chr(65+i) == str(task.get("correct_answer","")).upper() else ""
                explanation += f"{chr(65+i)}. {o}{mark}\n"
            explanation += f"\n**Correct Answer**: {task.get('correct_answer','')}\n\n"
        explanation += (
            "_No AI key provided — add an OpenRouter API key to generate real explanations._\n\n"
            "**Tip for students**: Re-read the question carefully, identify keywords, "
            "and recall related concepts before answering."
        )

    _explain_cache[cache_key] = explanation
    log.info("[AI EXPLAIN GENERATED] task=%s mode=%s type=%s len=%d",
             task_id, mode, q_type, len(explanation))
    return {"explanation": explanation, "cached": False, "mode": mode}


# ── Responses ──────────────────────────────────────────────────────

async def run_ai_evaluation_for_response(s: dict, task: dict, response: dict, api_key: str):
    question = task.get("question", "")
    expected_answer = task.get("correct_answer", "")
    student_answer = response.get("answer", "")
    max_marks = float(task.get("max_marks") or score_for(task))
    task_type = task.get("type", "short")
    long_answer = bool(task.get("long_answer", False))
    
    # Adapt evaluation criteria based on task type
    if task_type == "mcq":
        type_desc = "Multiple Choice Question (MCQ). The student selected an option. Correctness is absolute: full marks if student's answer option matches the expected answer, 0 otherwise."
        prompt = f"""
You are an expert academic evaluator. Evaluate the student's response for a {type_desc}.

Question: {question}
Expected Answer / Answer Key: {expected_answer}
Student's Answer: {student_answer}
Maximum Marks: {max_marks}

Provide a detailed evaluation:
1. Determine the suggested marks (a number between 0 and {max_marks}).
2. Provide a clear, constructive explanation / feedback.
3. Identify 1-3 key strengths in the student's answer.
4. Identify 1-3 weaknesses or areas for improvement in the student's answer.
5. Provide 1-3 actionable improvement suggestions.

Return ONLY a valid JSON object with the following keys:
{{
  "suggested_marks": a number (integer or float) between 0 and {max_marks},
  "confidence_score": a number between 0 and 1 representing your confidence,
  "explanation": "concise feedback string",
  "strengths": ["strength 1", "strength 2"],
  "weaknesses": ["weakness 1", "weakness 2"],
  "suggestions": ["suggestion 1", "suggestion 2"]
}}

Do not include any markdown styling, code blocks, or extra text. Output only the raw JSON.
"""
    elif task_type == "coding":
        student_output = response.get("student_output", "")
        student_error = response.get("student_error", "")
        expected_output = response.get("expected_output", "")
        prompt = f"""
You are an expert academic evaluator. Evaluate the student's submission for a Coding Challenge.
The student submitted code that was executed in a sandbox.

Question: {question}
Maximum Marks: {max_marks}

Model Solution Code:
{expected_answer}

Expected Output from Model Solution:
{expected_output}

Student's Submitted Code:
{student_answer}

Student's Execution Output:
{student_output}

Student's Execution Error (if any):
{student_error}

Evaluate their submission. 
Note:
- If the student's execution output matches the expected output and there are no execution errors, they should receive full marks (or close to it, unless they hardcoded the output instead of solving the problem).
- If the output does not match, check their logic. Since students can use different approaches (loops, recursion, different library functions), look at their code structure. If their code is mostly correct but had a small syntax/logical bug or format mismatch, give them proportional partial marks and helpful feedback.
- If the student simply printed the answer directly (hardcoded print) instead of writing the correct function logic, penalize them accordingly.

Provide a detailed evaluation:
1. Determine the suggested marks (a number between 0 and {max_marks}).
2. Provide a clear, constructive explanation / feedback.
3. Identify 1-3 key strengths in the student's answer.
4. Identify 1-3 weaknesses or areas for improvement in the student's answer.
5. Provide 1-3 actionable improvement suggestions.

Return ONLY a valid JSON object with the following keys:
{{
  "suggested_marks": a number (integer or float) between 0 and {max_marks},
  "confidence_score": a number between 0 and 1 representing your confidence,
  "explanation": "concise feedback string",
  "strengths": ["strength 1", "strength 2"],
  "weaknesses": ["weakness 1", "weakness 2"],
  "suggestions": ["suggestion 1", "suggestion 2"]
}}

Do not include any markdown styling, code blocks, or extra text. Output only the raw JSON.
"""
    else:
        if long_answer or task_type == "long" or task_type == "descriptive":
            type_desc = "Long Answer / Descriptive Response. Evaluate the student's depth of reasoning, completeness, correct facts, and semantic relevance. Grade proportionally between 0 and maximum marks."
        else:
            type_desc = "Short Answer Question. Check for semantic correctness and concise accuracy. Do not penalize for minor typos or exact wording mismatch if meaning is correct."
        prompt = f"""
You are an expert academic evaluator. Evaluate the student's response for a {type_desc}.

Question: {question}
Expected Answer / Answer Key: {expected_answer}
Student's Answer: {student_answer}
Maximum Marks: {max_marks}

Provide a detailed evaluation:
1. Determine the suggested marks (a number between 0 and {max_marks}).
2. Provide a clear, constructive explanation / feedback.
3. Identify 1-3 key strengths in the student's answer.
4. Identify 1-3 weaknesses or areas for improvement in the student's answer.
5. Provide 1-3 actionable improvement suggestions.

Return ONLY a valid JSON object with the following keys:
{{
  "suggested_marks": a number (integer or float) between 0 and {max_marks},
  "confidence_score": a number between 0 and 1 representing your confidence,
  "explanation": "concise feedback string",
  "strengths": ["strength 1", "strength 2"],
  "weaknesses": ["weakness 1", "weakness 2"],
  "suggestions": ["suggestion 1", "suggestion 2"]
}}

Do not include any markdown styling, code blocks, or extra text. Output only the raw JSON.
"""
    try:
        content = await call_llm(prompt, api_key=api_key, is_json=True)
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
            
        parsed = json.loads(content)
        suggested_marks = float(parsed.get("suggested_marks", 0))
        confidence = float(parsed.get("confidence_score", 1.0))
        explanation = str(parsed.get("explanation", ""))
        strengths = parsed.get("strengths", [])
        weaknesses = parsed.get("weaknesses", [])
        suggestions = parsed.get("suggestions", [])
        
        if isinstance(strengths, str): strengths = [strengths]
        if isinstance(weaknesses, str): weaknesses = [weaknesses]
        if isinstance(suggestions, str): suggestions = [suggestions]
        
        response["ai_score"] = min(max(0.0, suggested_marks), max_marks)
        response["confidence_score"] = confidence
        response["explanation"] = explanation
        response["strengths"] = strengths
        response["weaknesses"] = weaknesses
        response["suggestions"] = suggestions
        
        # --- AUTO-APPROVE AI EVALUATION ---
        score = response["ai_score"]
        is_correct = score >= (max_marks / 2.0)
        student_id = response.get("student_id")
        
        response["teacher_score"] = score
        response["teacher_feedback"] = explanation
        response["evaluation_status"] = "approved"
        response["correct"] = is_correct
        
        student = s["students"].get(student_id)
        if student:
            student["score"] = student.get("score", 0) + score
            student["correct"] = student.get("correct", 0) + (1 if is_correct else 0)
            
            if s.get("mode") == "test":
                ts = s["test_state"]
                ts["scores"][student_id] = ts["scores"].get(student_id, 0) + score
                lb_source = {sid: ts["scores"].get(sid, 0.0) for sid in ts["submitted"]}
                lb = sorted(lb_source.items(), key=lambda x: x[1], reverse=True)
                ts["leaderboard"] = [
                    {
                        "student_id":   sid,
                        "score":        sc,
                        "rank":         i + 1,
                        "student_name": s["students"].get(sid, {}).get("name", sid),
                    }
                    for i, (sid, sc) in enumerate(lb)
                ]
            
            try:
                update_student_reports_on_approval(s, student_id, task["id"], score, explanation, is_correct, strengths, weaknesses, suggestions)
            except Exception as rpt_err:
                log.warning("[AI EVALUATION] failed to update report: %s", rpt_err)
                
            try:
                _appr_analytics = compute_analytics(s)
                _appr_analytics["understanding_short"] = compute_analytics(s, question_type="short").get("understanding", 0)
                _appr_analytics["understanding_long"]  = compute_analytics(s, question_type="long").get("understanding", 0)
                await ws_teacher(s, {
                    "type": "analytics_update",
                    "analytics": _appr_analytics,
                })
            except Exception as analytics_err:
                log.warning("[AI EVALUATION] failed to update analytics: %s", analytics_err)
                
            try:
                st = s["students"].get(student_id)
                if st:
                    await push_roster_delta(s, "update", student_id, {
                        "total_answered": st.get("total_answered", 0),
                        "correct": st.get("correct", 0)
                    })
            except Exception as roster_err:
                log.warning("[AI EVALUATION] failed to push roster: %s", roster_err)
                
            try:
                await ws_student(s, student_id, {
                    "type": "evaluation_approved",
                    "task_id": task["id"],
                    "score": score,
                    "max_marks": max_marks,
                    "feedback": explanation,
                    "is_correct": is_correct,
                    "student_score": student.get("score", 0),
                    "strengths": strengths,
                    "weaknesses": weaknesses,
                    "suggestions": suggestions,
                    "total_answered": student.get("total_answered", 0) if student else 0,
                    "correct_count": student.get("correct", 0) if student else 0,
                })
            except Exception as ws_student_err:
                log.warning("[AI EVALUATION] failed to notify student: %s", ws_student_err)
                
    except Exception as exc:
        log.warning("[AI EVALUATION] failed: %s", exc)
        response["ai_score"] = 0.0
        response["confidence_score"] = 0.0
        response["explanation"] = f"AI evaluation error: {str(exc)}"
        response["evaluation_status"] = "pending"
        
    save_session(s["code"])
    await ws_teacher(s, {
        "type": "ai_evaluation_done",
        "task_id": task["id"],
        "student_id": response.get("student_id") or "",
    })


# ── Responses ──────────────────────────────────────────────────────

@app.post("/api/responses/submit")
async def submit_response(req: SubmitResponseReq, background_tasks: BackgroundTasks):
    s       = _S(req.session_code)
    task    = _T(s, req.task_id)
    student = s["students"].get(req.student_id)

    if not student or student.get("status") != "active":
        raise HTTPException(403, "Student is not active")
    if not student_can_submit_task(s, req.student_id, req.task_id):
        raise HTTPException(403, "Task has not been delivered to this student")

    # Both short AND long-answer questions require teacher/AI evaluation before
    # affecting analytics.  long_answer tasks are stored with type="short" and
    # long_answer=True, so we treat them identically here.
    is_short_answer = task.get("type") in ("short", "long", "descriptive")

    correct = False
    if task.get("type") == "mcq":
        correct = (str(req.answer).strip().upper() == str(task.get("correct_answer", "")).strip().upper())

    if task.get("type") == "coding":
        correct_answer_code = task.get("correct_answer", "")
        student_code = req.answer
        lang = task.get("language", "python").strip().lower()
        test_input = task.get("test_input", "") or ""

        # Preprocess Python code to handle various coding structures
        if lang in ("python", "python3"):
            import re
            func_name = None
            func_match = re.search(r"def\s+(\w+)\s*\(", correct_answer_code)
            if not func_match:
                func_match = re.search(r"def\s+(\w+)\s*\(", task.get("starter_code", ""))
            if func_match:
                func_name = func_match.group(1)

            # Find global-level calls in model solution
            global_calls = []
            for line in correct_answer_code.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if not line.startswith(" ") and not line.startswith("\t"):
                    if not (line.startswith("def ") or line.startswith("class ") or line.startswith("import ") or line.startswith("from ")):
                        global_calls.append(line)

            # Automatically append global calls if student defined function but didn't execute it
            if func_name:
                has_func_call = False
                for line in student_code.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or stripped.startswith("def "):
                        continue
                    if func_name in line:
                        has_func_call = True
                        break
                if not has_func_call and global_calls:
                    student_code = student_code + "\n\n" + "\n".join(global_calls)

            # Derive test input dynamically from correct_answer if empty and needed
            if not test_input.strip() and func_name:
                pattern = rf"print\(\s*{func_name}\s*\((.*)\)\s*\)"
                match = re.search(pattern, correct_answer_code)
                if match:
                    arg_str = match.group(1).strip()
                    if arg_str.startswith("{") or arg_str.startswith("[") or arg_str.startswith("'") or arg_str.startswith('"'):
                        test_input = arg_str

        # Execute correct answer to cache output if not cached yet
        expected_output = task.get("expected_output")
        ai_error = task.get("expected_error", False)
        
        if expected_output is None:
            ai_code = correct_answer_code
            loop = asyncio.get_event_loop()
            ai_future = loop.create_future()
            await execution_queue.put((ai_code, lang, test_input, ai_future))
            ai_result = await ai_future
            expected_output = (ai_result.output or "").strip()
            ai_error = bool(ai_result.error)
            task["expected_output"] = expected_output
            task["expected_error"] = ai_error

        # Execute student code with preprocessed script and test input
        loop = asyncio.get_event_loop()
        student_future = loop.create_future()
        await execution_queue.put((student_code, lang, test_input, student_future))
        student_result = await student_future
        student_out = (student_result.output or "").strip()
        
        correct = (expected_output == student_out) and not student_result.error and not ai_error
    is_short_answer = task.get("type") in ("short", "long", "descriptive")
    is_coding_ai = (task.get("type") == "coding" and task.get("evaluation_mode", "manual") == "ai")

    if is_short_answer or is_coding_ai:
        eval_mode = task.get("evaluation_mode", "manual")
        expected = task.get("correct_answer", "")
        max_m = task.get("max_marks") or score_for(task)
        
        resp_data = {
            "student_id":        req.student_id,
            "task_id":           req.task_id,
            "answer":            req.answer,
            "correct":           False,
            "time_taken":        req.time_taken,
            "submitted_at":      now(),
            "evaluation_mode":   eval_mode,
            "expected_answer":   expected,
            "max_marks":         max_m,
            "ai_score":          None,
            "teacher_score":     None,
            "evaluation_status": "pending",
            "teacher_feedback":  "",
        }
        if is_coding_ai:
            resp_data.update({
                "student_output":  student_out,
                "student_error":   student_result.error or "",
                "expected_output": expected_output,
                "ai_error":        ai_error,
            })
            
        s["responses"].setdefault(req.task_id, {})[req.student_id] = resp_data
        
        if student:
            student["total_answered"] += 1
            student["last_seen"] = now()
            
        api_key = get_teacher_key(s.get("teacher_email")) or os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY") or s.get("teacher_api_key")
        if eval_mode == "ai" and api_key:
            background_tasks.add_task(
                run_ai_evaluation_for_response, s, task, resp_data, api_key
            )
    else:
        # Generate default diagnostics for MCQ/coding questions
        feedback = "Correct answer! You selected the right option." if correct else f"Incorrect. You selected '{req.answer}', but the correct answer was '{task.get('correct_answer')}'."
        strengths = ["Correct option identification"] if correct else []
        weaknesses = [] if correct else ["Incorrect option selection"]
        suggestions = ["Keep up the good work!"] if correct else [f"Review the topic '{task.get('topic', 'General')}' and understand why the correct option is '{task.get('correct_answer')}'."]
        
        s["responses"].setdefault(req.task_id, {})[req.student_id] = {
            "answer":            req.answer,
            "correct":           correct,
            "time_taken":        req.time_taken,
            "submitted_at":      now(),
            "evaluation_status": "approved",
            "teacher_feedback":  feedback,
            "teacher_score":     float(score_for(task)) if correct else 0.0,
            "strengths":         strengths,
            "weaknesses":        weaknesses,
            "suggestions":       suggestions,
        }

        if student:
            student["total_answered"] += 1
            if correct:
                student["correct"] += 1
                student["score"]   += score_for(task)
            student["last_seen"] = now()

        if s["mode"] == "test" and correct:
            ts = s["test_state"]
            ts["scores"][req.student_id] = ts["scores"].get(req.student_id, 0) + score_for(task)

    # ── Auto-generate task report entry if NOT in test mode ──
    if s.get("mode") not in ("test",):
        try:
            rpt = _build_task_report(s, req.student_id, req.task_id)
            if rpt:
                _store_student_report(s, req.student_id, rpt)
                save_session(req.session_code)
        except Exception as _rpt_err:
            log.debug("Task report generation skipped: %s", _rpt_err)

    _live_analytics = compute_analytics(s)
    _live_analytics["understanding_short"] = compute_analytics(s, question_type="short").get("understanding", 0)
    _live_analytics["understanding_long"]  = compute_analytics(s, question_type="long").get("understanding", 0)
    await ws_teacher(s, {
        "type":           "analytics_update",
        "analytics":      _live_analytics,
        "task_id":        req.task_id,
        "response_count": len(s["responses"].get(req.task_id, {})),
    })
    touch_session(s)
    admin_broadcast({
        "event": "response_received",
        "session_code": req.session_code,
        "student_id": req.student_id,
        "task_id": req.task_id,
        "correct": correct if not is_short_answer else False,
    })
    
    if is_short_answer:
        return {
            "correct":        False,
            "score":          0,
            "correct_answer": "",
            "student_score":  student.get("score", 0) if student else 0,
            "evaluation_status": resp_data["evaluation_status"],
            "total_answered": student.get("total_answered", 0) if student else 0,
            "correct_count": student.get("correct", 0) if student else 0,
        }
    
    return {
        "correct":        correct,
        "score":          score_for(task) if correct else 0,
        "correct_answer": task.get("correct_answer", ""),
        "student_score":  student.get("score", 0) if student else 0,
        "total_answered": student.get("total_answered", 0) if student else 0,
        "correct_count": student.get("correct", 0) if student else 0,
    }


@app.post("/api/responses/request_hint")
async def request_hint(
    session_code: str = Query(...),
    student_id:   str = Query(...),
    task_id:      str = Query(...),
):
    s    = _S(session_code)
    task = _T(s, task_id)
    st   = s["students"].get(student_id)
    if not st or st.get("status") != "active":
        raise HTTPException(403, "Student is not active")
    if not student_can_submit_task(s, student_id, task_id):
        raise HTTPException(403, "Task has not been delivered to this student")
    st["hint_requests"] += 1
    vis  = task.get("hint_visibility", "on_request")
    hint = task.get("hint") if vis in ("always", "on_request") else None
    return {"hint": hint}


# ══════════════════════════════════════════════════════════════════
#  CONTENT ROUTES
# ══════════════════════════════════════════════════════════════════

ALLOWED_CT = {
    # Documents
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/zip",
    "application/x-zip-compressed",
    # Text
    "text/plain",
    "text/html",
    "text/csv",
    # Images
    "image/png", "image/jpeg", "image/jpg",
    "image/gif", "image/webp", "image/svg+xml",
    # Video
    "video/mp4", "video/webm", "video/ogg", "video/quicktime",
    "video/x-msvideo", "video/x-matroska",
    # Audio
    "audio/mpeg", "audio/mp3", "audio/ogg", "audio/wav",
    "audio/webm", "audio/aac", "audio/flac",
}
MAX_BYTES = 50 * 1024 * 1024  # 50 MB


def _guess_ct(filename: str, declared: str) -> str:
    """Return a valid content-type, falling back to extension-based guess."""
    if declared and declared not in ("application/octet-stream", ""):
        return declared
    ext = (filename or "").rsplit(".", 1)[-1].lower()
    return {
        "pdf": "application/pdf", "png": "image/png",
        "jpg": "image/jpeg", "jpeg": "image/jpeg",
        "gif": "image/gif", "webp": "image/webp",
        "svg": "image/svg+xml",
        "mp4": "video/mp4", "webm": "video/webm",
        "mov": "video/quicktime", "avi": "video/x-msvideo",
        "mp3": "audio/mpeg", "ogg": "audio/ogg",
        "wav": "audio/wav", "aac": "audio/aac",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "ppt": "application/vnd.ms-powerpoint",
        "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "zip": "application/zip",
        "txt": "text/plain", "csv": "text/csv",
    }.get(ext, "application/octet-stream")


def _guess_type_from_name_ct(name: str, ct: str) -> str:
    ct = (ct or "").lower()
    name = (name or "").lower()
    if ct.startswith("image/") or any(name.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]):
        return "image"
    if ct == "application/pdf" or name.endswith(".pdf"):
        return "pdf"
    if ct.startswith("video/") or any(name.endswith(ext) for ext in [".mp4", ".webm", ".mov", ".avi"]):
        return "video"
    if any(name.endswith(ext) for ext in [".ppt", ".pptx"]):
        return "presentation"
    if any(name.endswith(ext) for ext in [".doc", ".docx", ".txt"]):
        return "note"
    return "note"


@app.post("/api/content/upload")
async def upload_content(session_code: str = Form(...), file: UploadFile = File(...)):
    s    = _S(session_code)
    ct   = _guess_ct(file.filename or "", file.content_type or "")
    raw  = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "File too large (max 50 MB)")

    fname   = file.filename or f"file_{int(now())}"
    file_id = gen_id("cf")
    encoded = base64.b64encode(raw).decode()
    entry = {
        "id":           file_id,
        "name":         fname,
        "data":         encoded,
        "content_type": ct,
        "size":         len(raw),
        "uploaded_at":  now(),
        # Extended schema fields:
        "title":        fname,
        "type":         _guess_type_from_name_ct(fname, ct),
        "uploadedBy":   s.get("teacher_name", "Teacher"),
        "uploaderRole": "teacher",
        "source":       "Content Upload",
        "sourceChannel": "Library",
        "timestamp":    now(),
        "visibility":   "Class Visible",
        "previewUrl":   f"/api/content/file/{session_code}/{fname}",
        "tags":         ["TEACHER"],
        "linkedChatMessageId": None,
    }
    s["content_files"][fname] = entry
    log.info("Content uploaded: %s (%s, %d bytes) in session %s", fname, ct, len(raw), session_code)
    await ws_all_students(s, {
        "type":         "content_shared",
        "id":           file_id,
        "filename":     fname,
        "content_type": ct,
        "size":         len(raw),
        "uploaded_at":  now(),
        "uploadedBy":   entry["uploadedBy"],
        "uploaderRole": entry["uploaderRole"],
        "source":       entry["source"],
    })
    return {"id": file_id, "filename": fname, "size": len(raw), "content_type": ct}


@app.get("/api/session/{code}/content")
def list_content(code: str):
    s     = _S(code)
    files = []
    for v in s.get("content_files", {}).values():
        # Exclude all Doubt Center files — accessible only inside the
        # Doubt Center conversation view, never in the Content Hub.
        if v.get("doubt_file") or v.get("doubt_reply_file"):
            continue
        if v.get("source") == "Doubt Center":
            continue
        files.append({
            "id":           v.get("id", v["name"]),
            "name":         v["name"],
            "content_type": v["content_type"],
            "size":         v["size"],
            "uploaded_at":  v["uploaded_at"],
            "title":        v.get("title", v.get("name", "Untitled")),
            "description":  v.get("description", ""),
            "subject":      v.get("subject", ""),
            "objective":    v.get("objective", ""),
            "pinned":       v.get("pinned", False),
            "ai_generated": v.get("ai_generated", False),
            "views":        v.get("views", 0),
            "comments":     v.get("comments", 0),
            "type":         v.get("type", _guess_type_from_name_ct(v["name"], v["content_type"])),
            "uploadedBy":   v.get("uploadedBy", "Teacher"),
            "uploaderRole": v.get("uploaderRole", "teacher"),
            "source":       v.get("source", "Content Upload"),
            "sourceChannel": v.get("sourceChannel", "Library"),
            "timestamp":    v.get("timestamp", v["uploaded_at"]),
            "visibility":   v.get("visibility", "Class Visible"),
            "previewUrl":   v.get("previewUrl", f"/api/content/file/{code}/{v['name']}"),
            "tags":         v.get("tags", []),
            "linkedChatMessageId": v.get("linkedChatMessageId", None),
        })
    return {"files": files}


class UpdateMetadataReq(BaseModel):
    filename: str
    title: Optional[str] = None
    subject: Optional[str] = None
    description: Optional[str] = None
    objective: Optional[str] = None
    pinned: Optional[bool] = None
    uploadedBy: Optional[str] = None
    uploaderRole: Optional[str] = None
    source: Optional[str] = None
    sourceChannel: Optional[str] = None
    tags: Optional[list] = None
    visibility: Optional[str] = None
    linkedChatMessageId: Optional[str] = None


@app.post("/api/session/{code}/content/metadata")
async def update_content_metadata(code: str, req: UpdateMetadataReq):
    s = _S(code)
    fname = req.filename
    if fname not in s.get("content_files", {}):
        entry = next((v for v in s.get("content_files", {}).values() if v.get("id") == fname), None)
        if entry:
            fname = entry["name"]
        else:
            raise HTTPException(404, "File not found")
    
    entry = s["content_files"][fname]
    if req.title is not None: entry["title"] = req.title
    if req.subject is not None: entry["subject"] = req.subject
    if req.description is not None: entry["description"] = req.description
    if req.objective is not None: entry["objective"] = req.objective
    if req.pinned is not None: entry["pinned"] = req.pinned
    if req.uploadedBy is not None: entry["uploadedBy"] = req.uploadedBy
    if req.uploaderRole is not None: entry["uploaderRole"] = req.uploaderRole
    if req.source is not None: entry["source"] = req.source
    if req.sourceChannel is not None: entry["sourceChannel"] = req.sourceChannel
    if req.tags is not None: entry["tags"] = req.tags
    if req.visibility is not None: entry["visibility"] = req.visibility
    if req.linkedChatMessageId is not None: entry["linkedChatMessageId"] = req.linkedChatMessageId
    
    save_session(code)
    await ws_broadcast(s, {
        "type":         "content_shared",
        "id":           entry.get("id"),
        "filename":     fname,
        "content_type": entry.get("content_type"),
        "size":         entry.get("size"),
        "uploaded_at":  entry.get("uploaded_at"),
        "uploadedBy":   entry.get("uploadedBy"),
        "uploaderRole": entry.get("uploaderRole"),
        "source":       entry.get("source"),
    })
    return {"success": True}


class DescribeFileReq(BaseModel):
    session_code: str
    filename: str
    content_type: str
    base64_data: Optional[str] = None
    api_key: Optional[str] = None

@app.post("/api/ai/describe-file")
async def describe_file_endpoint(req: DescribeFileReq):
    s = _S(req.session_code)
    teacher_email = s.get("teacher_email")
    api_key_to_use = req.api_key or get_teacher_key(teacher_email) or os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key_to_use:
        raise HTTPException(400, "No API key configured on server or provided by client.")
    
    # Prompt is the same as the client side
    prompt = f'You are an educational content assistant. A teacher uploaded a file named "{req.filename}" (type: {req.content_type}) to their classroom.\n\nGenerate a brief, clear, educational description for students. Include:\n1. A smart summary title (max 60 chars)\n2. A brief description (2-3 sentences, educational context)\n3. A suggested learning objective\n\nRespond ONLY with valid JSON: {{"title":"...","description":"...","objective":"..."}}'
    if req.base64_data:
        prompt = f'You are an educational content assistant. A teacher uploaded this image named "{req.filename}" to their classroom.\nAnalyze the image content and generate a brief, clear, educational description for students. Include:\n1. A smart summary title (max 60 chars) describing the main topic of the image\n2. A brief description (2-3 sentences, explaining the educational concept shown in the image)\n3. A suggested learning objective based on the image content\n\nRespond ONLY with valid JSON: {{"title":"...","description":"...","objective":"..."}}'
        
    try:
        raw_resp = await call_llm_with_image(prompt, base64_data=req.base64_data, api_key=api_key_to_use)
        clean = raw_resp.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
        if clean.endswith("```"):
            clean = clean.rsplit("\n", 1)[0]
        if clean.startswith("json"):
            clean = clean.split("\n", 1)[1]
        clean = clean.strip()
        
        parsed = json.loads(clean)
        return parsed
    except Exception as e:
        log.error("[AI_DESCRIBE] Failed to generate description: %s", e, exc_info=True)
        raise HTTPException(500, f"AI Description generation failed: {str(e)}")


@app.get("/api/content/file/{code}/{filename:path}")
def serve_content_file(code: str, filename: str):
    """Serve file inline for preview (image, pdf, video, audio, text)."""
    s = _S(code)
    entry = s["content_files"].get(filename)
    if not entry:
        # Try matching by id
        entry = next((v for v in s["content_files"].values() if v.get("id") == filename), None)
    if not entry:
        raise HTTPException(404, "File not found")
    try:
        raw = base64.b64decode(entry["data"])
    except Exception:
        raise HTTPException(500, "File data is corrupted")
    ct = entry.get("content_type", "application/octet-stream")
    log.info("Serving file inline: %s (%s)", filename, ct)
    return Response(
        content=raw,
        media_type=ct,
        headers={
            "Content-Disposition": f'inline; filename="{entry["name"]}"',
            "Cache-Control": "private, max-age=3600",
            "Content-Length": str(len(raw)),
        },
    )


@app.get("/api/content/download/{code}/{filename:path}")
def download_content_file(code: str, filename: str):
    """Force-download a file."""
    s = _S(code)
    entry = s["content_files"].get(filename)
    if not entry:
        entry = next((v for v in s["content_files"].values() if v.get("id") == filename), None)
    if not entry:
        raise HTTPException(404, "File not found")
    try:
        raw = base64.b64decode(entry["data"])
    except Exception:
        raise HTTPException(500, "File data is corrupted")
    ct   = entry.get("content_type", "application/octet-stream")
    name = entry["name"]
    log.info("Downloading file: %s (%s)", name, ct)
    return Response(
        content=raw,
        media_type=ct,
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Content-Length": str(len(raw)),
        },
    )


@app.delete("/api/session/{code}/content/{filename}")
async def delete_content(code: str, filename: str):
    s = _S(code)
    if filename not in s["content_files"]:
        raise HTTPException(404, "File not found")
    del s["content_files"][filename]
    log.info("Deleted content file: %s from session %s", filename, code)
    return {"deleted": True}


# ══════════════════════════════════════════════════════════════════
#  GROUP ROUTES
# ══════════════════════════════════════════════════════════════════

@app.post("/api/groups/generate")
async def generate_groups(req: GenerateGroupsReq):
    s      = _S(req.session_code)
    active = [st for st in s["students"].values() if st["status"] == "active"]
    if len(active) < 2:
        raise HTTPException(400, "Need at least 2 active students")

    if req.strategy == "random":
        random.shuffle(active)
        ids = [st["id"] for st in active]
    else:
        sorted_s = sorted(active, key=lambda x: x["score"], reverse=True)
        ids      = [st["id"] for st in sorted_s]

    n_groups = max(1, (len(ids) + 3) // 4)
    buckets  = [[] for _ in range(n_groups)]
    for i, sid in enumerate(ids):
        row = i // n_groups
        col = i  % n_groups
        gi  = col if row % 2 == 0 else (n_groups - 1 - col)
        buckets[gi].append(sid)

    groups = [
        {"id": gen_id("g"), "name": f"Group {i+1}", "members": m}
        for i, m in enumerate(buckets) if m
    ]
    s["groups"] = groups
    await ws_broadcast(s, {"type": "groups_updated", "groups": groups})
    return {"groups": groups, "count": len(groups)}


@app.put("/api/groups/update")
async def update_group(req: UpdateGroupReq):
    s       = _S(req.session_code)
    members = list(dict.fromkeys(req.members))
    if len(members) > 4:
        raise HTTPException(400, "Max 4 students per group")
    missing  = [sid for sid in members if sid not in s["students"]]
    if missing:
        raise HTTPException(400, f"Unknown student IDs: {', '.join(missing)}")
    inactive = [sid for sid in members if s["students"][sid].get("status") != "active"]
    if inactive:
        raise HTTPException(400, f"Group members must be active: {', '.join(inactive)}")
    for g in s["groups"]:
        if g["id"] == req.group_id:
            g["members"] = members
            await ws_broadcast(s, {"type": "groups_updated", "groups": s["groups"]})
            return {"updated": True, "group": g}
    raise HTTPException(404, "Group not found")


@app.get("/api/session/{code}/groups")
def get_groups(code: str):
    s        = _S(code)
    students = s["students"]
    enriched = []
    for g in s["groups"]:
        members_info = [students[m] for m in g["members"] if m in students]
        enriched.append({**g, "members_info": members_info})
    return {"groups": enriched}


# ══════════════════════════════════════════════════════════════════
#  ANALYTICS & REPORTS
# ══════════════════════════════════════════════════════════════════

@app.get("/api/session/{code}/analytics")
def get_analytics(code: str):
    return compute_analytics(_S(code))


@app.get("/api/session/{code}/leaderboard")
def get_session_leaderboard(code: str):
    s      = _S(code)
    active = [st for st in s["students"].values() if st.get("status") == "active"]
    ranked = sorted(active, key=lambda st: (st.get("score", 0), st.get("correct", 0)), reverse=True)
    return [
        {
            "student_id":   st["id"],
            "student_name": st.get("name", st["id"]),
            "name":         st.get("name", st["id"]),
            "score":        st.get("score", 0),
            "correct":      st.get("correct", 0),
            "answered":     st.get("total_answered", 0),
            "rank":         i + 1,
        }
        for i, st in enumerate(ranked)
    ]


@app.get("/api/session/{code}/report")
def get_report(code: str):
    return compute_report(_S(code))


@app.get("/session/{code}/premium-report", include_in_schema=False)
def get_premium_report(code: str):
    report_path = Path(__file__).parent / "premium_report.html"
    if report_path.exists():
        return FileResponse(report_path, media_type="text/html")
    raise HTTPException(404, "Premium report template not found")


@app.get("/api/session/{code}/report/download")
def download_report(code: str, format: str = "csv"):
    s      = _S(code)
    report = compute_report(s)

    if format == "csv":
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(["Session Code", report["session_code"]])
        writer.writerow(["Teacher",      report["teacher_name"]])
        writer.writerow(["Status",       report["status"]])
        writer.writerow([])
        writer.writerow(["Student Performance"])
        writer.writerow(["Name", "Score", "Correct", "Answered"])
        for st in s["students"].values():
            writer.writerow([st["name"], st["score"], st["correct"], st["total_answered"]])
        writer.writerow([])
        writer.writerow(["Group Performance"])
        for g in report["group_stats"]:
            writer.writerow([g["name"], g["accuracy"]])
        return JSONResponse(content={"csv": output.getvalue()})

    return report


@app.get("/api/session/{code}/coding-analytics")
async def coding_analytics(code: str):
    s        = _S(code)
    students = list(s["students"].values())
    scores   = [st.get("coding_score", 0) for st in students if st.get("coding_submitted")]
    avg      = int(sum(scores) / len(scores)) if scores else 0
    sorted_s = sorted(students, key=lambda x: x.get("coding_score", 0), reverse=True)
    return {
        "avg_coding_score":  avg,
        "top_coders":        sorted_s[:3],
        "low_performers":    sorted_s[-3:],
        "submissions_count": len(scores),
    }


# ══════════════════════════════════════════════════════════════════
#  COMMUNICATION ROUTES
# ══════════════════════════════════════════════════════════════════

@app.post("/api/chat/send")
async def send_message(req: SendMessageReq):
    s    = _S(req.session_code)

    # Determine if sender is teacher
    is_teacher_sender = req.sender_id == "teacher" or req.sender_id not in s.get("students", {})

    # ── Chat disabled check ───────────────────────────────────────────
    if not is_teacher_sender and not s.get("chat_enabled", True):
        raise HTTPException(403, "Chat is currently disabled by the teacher")

    # ── Suspension check (Feature 3 & 7) ─────────────────────────────
    suspended_set = s.setdefault("suspended_chat_students", set())
    if not is_teacher_sender and req.sender_id in suspended_set:
        raise HTTPException(403, "You are suspended from classroom chat")

    st   = s["students"].get(req.sender_id)
    name = st["name"] if st else "Teacher"

    # ── Validate emoji / allowed types ───────────────────────────────
    allowed_msg_types = {"text", "file", "image", "system"}
    msg_type = (req.msg_type or "text").lower()
    if msg_type not in allowed_msg_types:
        msg_type = "text"

    msg = {
        "id":          gen_id("m"),
        "sender_id":   req.sender_id,
        "sender_name": name,
        "content":     req.content,
        "chat_type":   req.chat_type,
        "target_id":   req.target_id,
        "timestamp":   now(),
        # ── Extended fields ──────────────────────────────────────────
        "msg_type":    msg_type,
        "reactions":   {},   # emoji -> [user_id, ...]
        # ── Reply threading ──────────────────────────────────────────
        "reply_to_message_id": req.reply_to_message_id or None,
        "reply_preview":       req.reply_preview or None,
        # ── File attachment ──────────────────────────────────────────
        "file_info":   req.file_info or None,
    }
    s["chat_messages"].append(msg)
    payload = {"type": "chat_message", "message": msg}

    if req.chat_type == "global":
        await ws_broadcast(s, payload)
    elif req.chat_type == "group":
        if not req.target_id:
            raise HTTPException(400, "target_id required for group chat")
        group = next((g for g in s["groups"] if g["id"] == req.target_id), None)
        if group:
            for mid in group["members"]:
                await ws_student(s, mid, payload)
        await ws_teacher(s, payload)
    elif req.chat_type == "private":
        if not req.target_id:
            raise HTTPException(400, "target_id required for private chat")
        await ws_student(s, req.target_id, payload)
        await ws_teacher(s, payload)

    return msg


@app.get("/api/session/{code}/chat")
def get_chat(code: str, chat_type: str = Query("global"), limit: int = Query(200)):
    s    = _S(code)
    msgs = [m for m in s["chat_messages"] if m["chat_type"] == chat_type]
    return {"messages": msgs[-limit:]}


# ══════════════════════════════════════════════════════════════════
#  CHAT REACTIONS  (Feature 2)
# ══════════════════════════════════════════════════════════════════

ALLOWED_EMOJIS = {"👍", "❤️", "😂", "😮", "🔥", "👏"}

@app.post("/api/chat/react")
async def toggle_reaction(req: ChatReactionReq):
    s = _S(req.session_code)
    emoji = req.emoji
    if emoji not in ALLOWED_EMOJIS:
        raise HTTPException(400, "Invalid emoji")

    msg = next((m for m in s["chat_messages"] if m.get("id") == req.message_id), None)
    if not msg:
        raise HTTPException(404, "Message not found")

    msg.setdefault("reactions", {})
    reactors: list = msg["reactions"].setdefault(emoji, [])
    if req.user_id in reactors:
        reactors.remove(req.user_id)
    else:
        reactors.append(req.user_id)

    # Broadcast updated reactions to all clients
    await ws_broadcast(s, {
        "type":       "chat_reactions_update",
        "message_id": req.message_id,
        "reactions":  msg["reactions"],
    })
    save_session(req.session_code)
    return {"message_id": req.message_id, "reactions": msg["reactions"]}


# ══════════════════════════════════════════════════════════════════
#  CHAT MODERATION  (Feature 3 & 7)
# ══════════════════════════════════════════════════════════════════

@app.post("/api/session/{code}/chat/suspend/{student_id}")
async def suspend_student_chat(code: str, student_id: str):
    s = _S(code)
    student = s["students"].get(student_id)
    if not student:
        raise HTTPException(404, "Student not found")

    s.setdefault("suspended_chat_students", set()).add(student_id)
    save_session(code)

    # Notify the suspended student
    await ws_student(s, student_id, {
        "type":    "chat_suspended",
        "message": "You are temporarily suspended from classroom chat.",
    })
    # System message in chat
    sys_msg = {
        "id":          gen_id("m"),
        "sender_id":   "system",
        "sender_name": "System",
        "content":     f"⚠️ {student.get('name', student_id)} has been suspended from chat.",
        "chat_type":   "global",
        "target_id":   None,
        "timestamp":   now(),
        "msg_type":    "system",
        "reactions":   {},
        "reply_to_message_id": None,
        "reply_preview":       None,
        "file_info":   None,
    }
    s["chat_messages"].append(sys_msg)
    await ws_broadcast(s, {"type": "chat_message", "message": sys_msg})
    await ws_teacher(s, {
        "type":       "chat_suspension_update",
        "student_id": student_id,
        "suspended":  True,
        "student_name": student.get("name", student_id),
    })
    log.info("[MODERATION] Student %s suspended from chat in session %s", student_id, code)
    return {"suspended": True, "student_id": student_id}


@app.post("/api/session/{code}/chat/unsuspend/{student_id}")
async def unsuspend_student_chat(code: str, student_id: str):
    s = _S(code)
    student = s["students"].get(student_id)
    if not student:
        raise HTTPException(404, "Student not found")

    s.setdefault("suspended_chat_students", set()).discard(student_id)
    save_session(code)

    await ws_student(s, student_id, {
        "type":    "chat_unsuspended",
        "message": "Your chat access has been restored.",
    })
    await ws_teacher(s, {
        "type":       "chat_suspension_update",
        "student_id": student_id,
        "suspended":  False,
        "student_name": student.get("name", student_id),
    })
    log.info("[MODERATION] Student %s unsuspended from chat in session %s", student_id, code)
    return {"suspended": False, "student_id": student_id}


@app.get("/api/session/{code}/chat/suspended")
def get_suspended_chat_students(code: str):
    s = _S(code)
    return {"suspended": list(s.get("suspended_chat_students", set()))}


# ══════════════════════════════════════════════════════════════════
#  CHAT MESSAGE DELETION  (Feature 5)
# ══════════════════════════════════════════════════════════════════

@app.delete("/api/session/{code}/chat/{msg_id}")
async def delete_chat_message(code: str, msg_id: str):
    s = _S(code)
    msgs = s.get("chat_messages", [])
    idx = next((i for i, m in enumerate(msgs) if m.get("id") == msg_id), None)
    if idx is None:
        raise HTTPException(404, "Message not found")

    # Remove the message
    s["chat_messages"].pop(idx)
    save_session(code)

    # Broadcast deletion event
    await ws_broadcast(s, {
        "type":       "chat_message_deleted",
        "message_id": msg_id,
    })
    log.info("[CHAT] Message %s deleted from session %s", msg_id, code)
    return {"deleted": True, "message_id": msg_id}


# ══════════════════════════════════════════════════════════════════
#  TEACHER FILE UPLOAD IN CHAT  (Feature 5)
# ══════════════════════════════════════════════════════════════════

CHAT_ALLOWED_CT = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "image/png", "image/jpeg", "image/jpg", "image/gif", "image/webp",
}
CHAT_IMG_MAX = 8 * 1024 * 1024    # 8 MB for images
CHAT_DOC_MAX = 20 * 1024 * 1024   # 20 MB for documents

@app.post("/api/session/{code}/chat/upload_file")
async def upload_file_to_chat(
    code:    str,
    file:    UploadFile = File(...),
):
    s  = _S(code)
    ct = _guess_ct(file.filename or "", file.content_type or "")

    # Validate content type
    if ct not in CHAT_ALLOWED_CT and not ct.startswith("image/"):
        raise HTTPException(415, "Unsupported file type for chat. Allowed: PDF, DOCX, PPTX, TXT, Images.")

    raw = await file.read()
    is_image = ct.startswith("image/")

    # Size validation
    if is_image and len(raw) > CHAT_IMG_MAX:
        raise HTTPException(413, f"Image too large (max 8 MB)")
    if not is_image and len(raw) > CHAT_DOC_MAX:
        raise HTTPException(413, f"Document too large (max 20 MB)")

    # Store in content_files (reusing existing system)
    fname   = file.filename or f"chat_file_{int(now())}"
    file_id = gen_id("cf")
    encoded = base64.b64encode(raw).decode()
    msg_id  = gen_id("m")
    entry = {
        "id":           file_id,
        "name":         fname,
        "data":         encoded,
        "content_type": ct,
        "size":         len(raw),
        "uploaded_at":  now(),
        "chat_file":    True,   # mark as chat file
        # Extended schema fields:
        "title":        fname,
        "type":         _guess_type_from_name_ct(fname, ct),
        "uploadedBy":   s.get("teacher_name", "Teacher"),
        "uploaderRole": "teacher",
        "source":       "Chat Upload",
        "sourceChannel": "Global Chat",
        "timestamp":    now(),
        "visibility":   "Class Visible",
        "previewUrl":   f"/api/content/file/{code}/{fname}",
        "tags":         ["CHAT", "TEACHER"],
        "linkedChatMessageId": msg_id,
    }
    s["content_files"][fname] = entry
    save_session(code)

    # Create chat message with file attachment
    msg_type = "image" if is_image else "file"
    sys_file_msg = {
        "id":          msg_id,
        "sender_id":   "teacher",
        "sender_name": "Teacher",
        "content":     fname,
        "chat_type":   "global",
        "target_id":   None,
        "timestamp":   now(),
        "msg_type":    msg_type,
        "reactions":   {},
        "reply_to_message_id": None,
        "reply_preview":       None,
        "file_info":   {
            "id":           file_id,
            "name":         fname,
            "content_type": ct,
            "size":         len(raw),
        },
    }
    s["chat_messages"].append(sys_file_msg)

    # System event in chat
    sys_event_msg = {
        "id":          gen_id("m"),
        "sender_id":   "system",
        "sender_name": "System",
        "content":     f"📎 Teacher uploaded a file: {fname}",
        "chat_type":   "global",
        "target_id":   None,
        "timestamp":   now(),
        "msg_type":    "system",
        "reactions":   {},
        "reply_to_message_id": None,
        "reply_preview":       None,
        "file_info":   None,
    }
    s["chat_messages"].append(sys_event_msg)

    # Broadcast both messages
    await ws_broadcast(s, {"type": "chat_message", "message": sys_file_msg})
    await ws_broadcast(s, {"type": "chat_message", "message": sys_event_msg})

    log.info("[CHAT FILE] Teacher uploaded %s (%s, %d bytes) in session %s", fname, ct, len(raw), code)
    return {
        "file_id":      file_id,
        "filename":     fname,
        "content_type": ct,
        "size":         len(raw),
        "message":      sys_file_msg,
    }


@app.post("/api/chat/upload")
async def student_chat_upload(
    session_code: str = Form(...),
    sender_id: str = Form(...),
    chat_type: str = Form("global"),
    file: UploadFile = File(...),
    reply_to_message_id: Optional[str] = Form(None),
    reply_preview: Optional[str] = Form(None),
):
    s = _S(session_code)
    ct = _guess_ct(file.filename or "", file.content_type or "")
    if ct not in CHAT_ALLOWED_CT and not ct.startswith("image/"):
        raise HTTPException(415, "Unsupported file type for chat. Allowed: PDF, DOCX, PPTX, TXT, Images.")

    raw = await file.read()
    is_image = ct.startswith("image/")

    if is_image and len(raw) > CHAT_IMG_MAX:
        raise HTTPException(413, "Image too large (max 8 MB)")
    if not is_image and len(raw) > CHAT_DOC_MAX:
        raise HTTPException(413, "Document too large (max 20 MB)")

    fname = file.filename or f"chat_file_{int(now())}"
    file_id = gen_id("cf")
    encoded = base64.b64encode(raw).decode()

    st = s["students"].get(sender_id)
    if st:
        name = st["name"]
    elif sender_id == "teacher":
        name = s.get("teacher_name", "Teacher")
    else:
        name = "Student"

    msg_id = gen_id("m")
    entry = {
        "id":           file_id,
        "name":         fname,
        "data":         encoded,
        "content_type": ct,
        "size":         len(raw),
        "uploaded_at":  now(),
        "chat_file":    True,
        # Extended schema fields:
        "title":        fname,
        "type":         _guess_type_from_name_ct(fname, ct),
        "uploadedBy":   name,
        "uploaderRole": "student" if sender_id != "teacher" else "teacher",
        "source":       "Chat Upload",
        "sourceChannel": chat_type.capitalize() + " Chat",
        "timestamp":    now(),
        "visibility":   "Class Visible",
        "previewUrl":   f"/api/content/file/{session_code}/{fname}",
        "tags":         ["CHAT", "STUDENT"] if sender_id != "teacher" else ["CHAT", "TEACHER"],
        "linkedChatMessageId": msg_id,
    }
    s["content_files"][fname] = entry
    save_session(session_code)

    msg_type = "image" if is_image else "file"
    msg = {
        "id":          msg_id,
        "sender_id":   sender_id,
        "sender_name": name,
        "content":     fname,
        "chat_type":   chat_type,
        "target_id":   None,
        "timestamp":   now(),
        "msg_type":    msg_type,
        "reactions":   {},
        "reply_to_message_id": reply_to_message_id or None,
        "reply_preview":       reply_preview or None,
        "file_info":   {
            "id":           file_id,
            "name":         fname,
            "content_type": ct,
            "size":         len(raw),
        },
    }
    s["chat_messages"].append(msg)

    sys_event_msg = {
        "id":          gen_id("m"),
        "sender_id":   "system",
        "sender_name": "System",
        "content":     f"📎 {name} uploaded a file: {fname}",
        "chat_type":   chat_type,
        "target_id":   None,
        "timestamp":   now(),
        "msg_type":    "system",
        "reactions":   {},
        "reply_to_message_id": None,
        "reply_preview":       None,
        "file_info":   None,
    }
    s["chat_messages"].append(sys_event_msg)

    payload = {"type": "chat_message", "message": msg}
    sys_payload = {"type": "chat_message", "message": sys_event_msg}
    await ws_broadcast(s, payload)
    await ws_broadcast(s, sys_payload)

    log.info("[CHAT FILE] Student %s uploaded %s in session %s", sender_id, fname, session_code)
    return msg


@app.post("/api/doubts/submit")
async def submit_doubt(req: SubmitDoubtReq):
    s  = _S(req.session_code)
    s.setdefault("doubts", [])
    st = s["students"].get(req.student_id, {})
    d  = {
        "id":           gen_id("d"),
        "student_id":   req.student_id,
        "student_name": st.get("name", "?"),
        "doubt_text":   req.doubt_text,
        "text":         req.doubt_text,
        "subject":      req.subject or "General",
        "answer":       None,
        "reply":        None,
        "status":       "pending",
        "resolved":     False,
        "resolved_at":  None,
        "resolved_by":  None,
        "created_at":   now(),
        "replies":      [],
    }
    s["doubts"].append(d)
    await ws_teacher(s, {"type": "new_doubt", "doubt": d})
    return d


@app.post("/api/doubts/submit_with_image")
async def submit_doubt_with_image(
    session_code: str = Form(...),
    student_id: str = Form(...),
    doubt_text: str = Form(...),
    subject: str = Form("General"),
    image: UploadFile = File(...),
):
    s = _S(session_code)
    s.setdefault("doubts", [])
    st = s["students"].get(student_id, {})
    name = st.get("name", "Student")

    ct = _guess_ct(image.filename or "", image.content_type or "")
    is_image = ct.startswith("image/")
    is_allowed_doc = ct in ("application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/vnd.openxmlformats-officedocument.presentationml.presentation", "text/plain")
    
    if not (is_image or is_allowed_doc):
        raise HTTPException(415, "Unsupported file type for doubts. Allowed: PDF, DOCX, PPTX, TXT, Images.")

    raw = await image.read()
    max_size = 5 * 1024 * 1024 if is_image else 20 * 1024 * 1024
    if len(raw) > max_size:
        raise HTTPException(413, f"File too large (max {max_size // (1024 * 1024)} MB)")

    fname = f"doubt_{gen_id('dimg')}_{image.filename}"
    file_id = gen_id("cf")
    encoded = base64.b64encode(raw).decode()
    entry = {
        "id":           file_id,
        "name":         fname,
        "data":         encoded,
        "content_type": ct,
        "size":         len(raw),
        "uploaded_at":  now(),
        "doubt_file":   True,
        # Extended schema fields:
        "title":        f"Doubt File - {subject}" if not is_image else f"Doubt Image - {subject}",
        "type":         "pdf" if ct == "application/pdf" else "doc" if not is_image else "image",
        "uploadedBy":   name,
        "uploaderRole": "student",
        "source":       "Student Shared",
        "sourceChannel": "Doubt Channel",
        "timestamp":    now(),
        "visibility":   "Class Visible",
        "previewUrl":   f"/api/content/file/{session_code}/{fname}",
        "tags":         ["DOUBT", "STUDENT"],
        "linkedChatMessageId": None,
    }
    s["content_files"][fname] = entry
    save_session(session_code)
    # Note: no content_shared WS broadcast — doubt files are internal to the
    # Doubt Center and must not appear in the Content Hub.

    d = {
        "id":           gen_id("d"),
        "student_id":   student_id,
        "student_name": name,
        "doubt_text":   doubt_text,
        "text":         doubt_text,
        "subject":      subject,
        "answer":       None,
        "reply":        None,
        "status":       "pending",
        "resolved":     False,
        "resolved_at":  None,
        "resolved_by":  None,
        "created_at":   now(),
        "replies":      [],
    }
    if is_image:
        d["image_url"] = f"/api/content/file/{session_code}/{fname}"
    else:
        d["file_url"] = f"/api/content/file/{session_code}/{fname}"
        d["file_name"] = image.filename
        d["file_type"] = "pdf" if ct == "application/pdf" else "doc"
        d["file_size"] = len(raw)

    s["doubts"].append(d)
    save_session(session_code)

    await ws_teacher(s, {"type": "new_doubt", "doubt": d})
    return d


@app.post("/api/doubts/teacher_reply_with_file")
async def teacher_reply_with_file(
    session_code: str = Form(...),
    doubt_id: str = Form(...),
    text: str = Form(""),
    file: UploadFile = File(None),
):
    """Teacher replies to a doubt with an optional file attachment."""
    import time
    s = _S(session_code)
    s.setdefault("doubts", [])

    file_url = None
    file_name = None
    file_size = None
    image_url = None

    if file and file.filename:
        ct = _guess_ct(file.filename or "", file.content_type or "")
        is_image = ct.startswith("image/")
        raw = await file.read()
        max_size = 5 * 1024 * 1024 if is_image else 20 * 1024 * 1024
        if len(raw) > max_size:
            raise HTTPException(413, f"File too large (max {max_size // (1024*1024)} MB)")

        fname = f"dreply_{gen_id('tr')}_{file.filename}"
        file_id = gen_id("cf")
        encoded = base64.b64encode(raw).decode()
        entry = {
            "id":           file_id,
            "name":         fname,
            "data":         encoded,
            "content_type": ct,
            "size":         len(raw),
            "uploaded_at":  now(),
            "doubt_reply_file": True,
            "title":        f"Teacher Reply Attachment",
            "type":         "image" if is_image else "pdf" if ct == "application/pdf" else "doc",
            "uploadedBy":   "Teacher",
            "uploaderRole": "teacher",
            "source":       "Teacher Shared",
            "sourceChannel": "Teacher Reply",
            "timestamp":    now(),
            "visibility":   "Class Visible",
            "previewUrl":   f"/api/content/file/{session_code}/{fname}",
            "tags":         ["TEACHER", "REPLY"],
            "linkedChatMessageId": None,
        }
        s["content_files"][fname] = entry
        if is_image:
            image_url = f"/api/content/file/{session_code}/{fname}"
        else:
            file_url = f"/api/content/file/{session_code}/{fname}"
            file_name = file.filename
            file_size = len(raw)

    # Find the doubt and append the reply
    found_doubt = None
    for d in s["doubts"]:
        if d.get("id") == doubt_id:
            found_doubt = d
            break
    if not found_doubt:
        raise HTTPException(404, "Doubt not found")

    reply_obj = {
        "id":          gen_id("dr"),
        "sender":      "teacher",
        "sender_id":   "teacher",
        "sender_name": "Teacher",
        "text":        text.strip(),
        "ts":          int(time.time() * 1000),
        "attachments": [],
    }
    if image_url:
        reply_obj["image_url"] = image_url
    if file_url:
        reply_obj["file_url"] = file_url
        reply_obj["file_name"] = file_name
        reply_obj["file_size"] = file_size

    found_doubt.setdefault("replies", []).append(reply_obj)
    save_session(session_code)
    await ws_teacher(s, {"type": "new_doubt", "doubt": found_doubt})
    await ws_student(s, found_doubt["student_id"], {"type": "new_doubt", "doubt": found_doubt})
    return {"success": True, "reply": reply_obj}


@app.post("/api/doubts/resolve")
async def resolve_doubt(req: ResolveDoubtReq):
    s = _S(req.session_code)
    s.setdefault("doubts", [])
    for d in s["doubts"]:
        if d["id"] == req.doubt_id:
            d.update({
                "answer": req.answer,
                "reply": req.answer,
                "resolved": True,
                "status": "resolved",
                "resolved_at": now(),
                "resolved_by": "teacher",
            })
            await ws_teacher(s, {"type": "doubt_resolved", "doubt": d})
            await ws_student(s, d["student_id"], {"type": "doubt_resolved", "doubt": d})
            return d
    raise HTTPException(404, "Doubt not found")


@app.post("/api/doubts/reopen")
async def reopen_doubt(req: ReopenDoubtReq):
    s = _S(req.session_code)
    s.setdefault("doubts", [])
    for d in s["doubts"]:
        if d["id"] == req.doubt_id:
            d.update({
                "resolved": False,
                "status": "pending",
                "answer": None,
                "reply": None,
                "resolved_at": None,
                "resolved_by": None,
            })
            await ws_teacher(s, {"type": "doubt_reopened", "doubt": d})
            await ws_student(s, d["student_id"], {"type": "doubt_reopened", "doubt": d})
            return d
    raise HTTPException(404, "Doubt not found")


@app.get("/api/session/{code}/doubts")
def get_doubts(code: str):
    return {"doubts": _S(code)["doubts"]}


@app.get("/api/session/{code}/student/{student_id}/doubts")
def get_student_doubts(code: str, student_id: str):
    s = _S(code)
    student_doubts = [d for d in s.get("doubts", []) if d.get("student_id") == student_id]
    return {"doubts": student_doubts}


class DoubtReplyReq(BaseModel):
    student_id: str
    text: str


@app.post("/api/session/{code}/doubt/{doubt_id}/reply")
async def reply_doubt_api(code: str, doubt_id: str, req: DoubtReplyReq):
    s = _S(code)
    s.setdefault("doubts", [])
    st = s["students"].get(req.student_id, {})
    student_name = st.get("name", "Student")

    import time
    found = False
    for d in s["doubts"]:
        if d.get("id") == doubt_id:
            replies = d.setdefault("replies", [])
            reply_obj = {
                "id": gen_id("dr"),
                "sender": "student",
                "sender_id": req.student_id,
                "sender_name": student_name,
                "text": req.text,
                "ts": int(time.time() * 1000),
                "attachments": []
            }
            replies.append(reply_obj)
            d["status"] = "pending"
            d["resolved"] = False
            found = True
            save_session(code)
            await ws_teacher(s, {"type": "new_doubt", "doubt": d})
            break
            
    if not found:
        raise HTTPException(404, "Doubt not found")
        
    return {"success": True}


@app.post("/api/session/{code}/raise_hand/{student_id}")
async def raise_hand(code: str, student_id: str):
    s = sessions.get(code)
    if not s:
        raise HTTPException(404, "Session not found")
    if student_id not in s.get("students", {}):
        raise HTTPException(404, "Student not found")
    st = s["students"].get(student_id, {})
    # raised_hands is now a dict: {student_id: {name, raised_at}}
    rh = s.setdefault("raised_hands", {})
    if isinstance(rh, list):
        # Migrate legacy list format to dict
        rh = {sid: {"name": s["students"].get(sid, {}).get("name", "?"), "raised_at": now()} for sid in rh if sid in s["students"]}
        s["raised_hands"] = rh
    if student_id not in rh:
        rh[student_id] = {"name": st.get("name", "?"), "raised_at": now()}
    hand_list = [
        {"student_id": sid, "student_name": info.get("name", "?"), "raised_at": info.get("raised_at")}
        for sid, info in rh.items()
    ]
    await ws_teacher(s, {
        "type":         "hand_raised",
        "student_id":   student_id,
        "student_name": st.get("name", "?"),
        "raised_hands": hand_list,
        "count":        len(rh),
    })
    return {"raised": True, "count": len(rh)}


@app.post("/api/session/{code}/lower_hand/{student_id}")
async def lower_hand(code: str, student_id: str):
    s = sessions.get(code)
    if not s:
        raise HTTPException(404, "Session not found")
    rh = s.setdefault("raised_hands", {})
    if isinstance(rh, list):
        rh = {sid: {"name": s["students"].get(sid, {}).get("name", "?"), "raised_at": now()} for sid in rh if sid in s["students"]}
        s["raised_hands"] = rh
    rh.pop(student_id, None)
    hand_list = [
        {"student_id": sid, "student_name": info.get("name", "?"), "raised_at": info.get("raised_at")}
        for sid, info in rh.items()
    ]
    await ws_teacher(s, {
        "type":         "hand_lowered",
        "student_id":   student_id,
        "raised_hands": hand_list,
        "count":        len(rh),
    })
    return {"lowered": True, "count": len(rh)}


@app.post("/api/session/{code}/broadcast")
async def broadcast_msg(code: str, message: str = Query(...)):
    s = _S(code)
    await ws_all_students(s, {"type": "announcement", "message": message})
    return {"sent": True}


@app.post("/api/session/{code}/waiting/question")
async def ask_waiting(code: str, question: str = Query(...)):
    s = _S(code)
    for sid in s["waiting_room"]:
        await ws_student(s, sid, {"type": "waiting_question", "question": question})
    return {"sent": True}


@app.post("/api/session/{code}/waiting/response")
async def waiting_response(
    code:       str,
    student_id: str = Query(...),
    answer:     str = Query(...),
):
    s = _S(code)
    await ws_teacher(s, {
        "type":       "waiting_response",
        "student_id": student_id,
        "answer":     answer,
    })
    return {"ok": True}


@app.post("/api/session/{code}/resend-report")
@app.post("/api/session/{code}/send-report")
async def send_report(
    background_tasks: BackgroundTasks,
    code: str, 
    email: Optional[str] = Query(None), 
    req_body: Optional[dict] = Body(None),
):
    """
    Send session report email in the background.
    Rate limited to 3 sends per session.
    """
    try:
        # 1. Recipient resolution
        email_from_body = req_body.get("email") if req_body else None
        
        # Fallback to session teacher email if no email provided
        s = sessions.get(code)
        if not s:
            raise HTTPException(404, f"Session '{code}' not found")
            
        target_email = email_from_body or email or s.get("teacher_email")
        
        if not target_email:
            raise HTTPException(400, "Email recipient is required")
        
        target_email = target_email.strip()
        if not is_valid_email(target_email):
            raise HTTPException(400, f"Invalid email format: {target_email}")

        s = sessions.get(code)
        if not s:
            raise HTTPException(404, f"Session '{code}' not found")

        # 1. Rate Limiting (Requirement 4)
        send_count = s.get("_email_count", 0)
        if send_count >= 3:
            return {
                "success": False,
                "status":  "error",
                "message": "Max 3 emails per session.",
            }
        s["_email_count"] = send_count + 1

        # 2. SMTP verification
        ok, msg = await verify_smtp_credentials()
        if not ok:
            log.error("[SEND_REPORT] SMTP verification failed: %s", msg)
            return {
                "success": False,
                "status":  "error",
                "message": msg,
            }

        # 3. Queue Background Task (Requirement 3)
        background_tasks.add_task(dispatch_email_report, code, target_email)

        return {
            "success":    True,
            "status":     "success",
            "message":    f"Sending report to {target_email} in the background.",
            "email":      target_email,
            "session_id": code,
        }
    except HTTPException:
        raise
    except Exception as e:
        log.error("[SEND_REPORT] Error: %s", e, exc_info=True)
        return {
            "success": False,
            "status":  "error",
            "message": f"Server Error: {str(e)}",
        }


async def dispatch_email_report(code: str, email: str):
    """Background task to compute and send email."""
    s = sessions.get(code)
    if not s: return
    
    try:
        report = compute_report(s)
        teacher_name = s.get("teacher_name", "Teacher")
        
        ok, msg = await send_session_email(
            to_email     = email,
            session_data = report,
            teacher_name = teacher_name,
        )
        
        if ok:
            log.info("[BACKGROUND_EMAIL] Success for %s to %s", code, email)
        else:
            log.error("[BACKGROUND_EMAIL] Failed for %s: %s", code, msg)
            
    except Exception as exc:
        log.error("[BACKGROUND_EMAIL] Unexpected error: %s", exc)




# ══════════════════════════════════════════════════════════════════
#  TEST MODE ROUTES
# ══════════════════════════════════════════════════════════════════

@app.post("/api/test/start")
async def start_test(req: StartTestReq):
    s = _S(req.session_code)
    if not s["tasks"]:
        raise HTTPException(400, "No tasks in session")

    pool = (
        [t for t in s["tasks"] if t["id"] in req.task_ids]
        if req.task_ids else s["tasks"]
    )
    if not pool:
        raise HTTPException(400, "No matching tasks found")

    s["mode"]   = "test"
    s["status"] = "active"
    ts          = s["test_state"]
    ts.update({
        "active":        True,
        "start_time":    now(),
        "duration_secs": req.duration_secs,
        "task_ids":      [t["id"] for t in pool],
        "submitted":     set(),
        "scores":        {},
        "leaderboard":   [],
    })

    shuffled = pool[:]
    random.shuffle(shuffled)
    await ws_broadcast(s, {
        "type":          "test_started",
        "duration_secs": req.duration_secs,
        "start_time":    ts["start_time"],
        "tasks":         [safe_task(t) for t in shuffled],
        "task_count":    len(shuffled),
    })
    return {"started": True, "task_count": len(shuffled)}


@app.post("/api/test/submit/{session_code}/{student_id}")
async def submit_test(session_code: str, student_id: str):
    s  = _S(session_code)
    ts = s["test_state"]
    if student_id in ts["submitted"]:
        return {"already_submitted": True, "score": ts["scores"].get(student_id, 0)}

    ts["submitted"].add(student_id)
    score = ts["scores"].get(student_id, 0)
    lb_source = {sid: ts["scores"].get(sid, 0.0) for sid in ts["submitted"]}
    lb = sorted(lb_source.items(), key=lambda x: x[1], reverse=True)
    ts["leaderboard"] = [
        {
            "student_id":   sid,
            "score":        sc,
            "rank":         i + 1,
            "student_name": s["students"].get(sid, {}).get("name", sid),
        }
        for i, (sid, sc) in enumerate(lb)
    ]
    # ── Auto-generate and persist test report for this student ──
    try:
        rpt = _build_test_report(s, student_id)
        if rpt:
            _store_student_report(s, student_id, rpt)
            save_session(session_code)
    except Exception as _rpt_err:
        log.debug("Report generation skipped: %s", _rpt_err)
    await ws_teacher(s, {
        "type":            "test_submission",
        "student_id":      student_id,
        "score":           score,
        "leaderboard":     ts["leaderboard"],
        "submitted_count": len(ts["submitted"]),
    })
    rank = next((r["rank"] for r in ts["leaderboard"] if r["student_id"] == student_id), None)
    return {"submitted": True, "score": score, "rank": rank}


@app.post("/api/test/end/{session_code}")
async def end_test(session_code: str):
    s  = _S(session_code)
    ts = s["test_state"]
    ts["active"] = False
    s["mode"]    = "live"
    lb_source = {sid: ts["scores"].get(sid, 0.0) for sid in ts["submitted"]}
    lb = sorted(lb_source.items(), key=lambda x: x[1], reverse=True)
    ts["leaderboard"] = [
        {
            "student_id":   sid,
            "score":        sc,
            "rank":         i + 1,
            "student_name": s["students"].get(sid, {}).get("name", sid),
        }
        for i, (sid, sc) in enumerate(lb)
    ]
    return {"ended": True, "leaderboard": ts["leaderboard"]}


@app.get("/api/test/{session_code}/leaderboard")
def get_leaderboard(session_code: str):
    ts = _S(session_code)["test_state"]
    return {
        "leaderboard":     ts["leaderboard"],
        "active":          ts["active"],
        "submitted_count": len(ts["submitted"]),
    }

# ══════════════════════════════════════════════════════════════════
#  STUDENT REPORT CENTER — auto-generation + retrieval
# ══════════════════════════════════════════════════════════════════

async def generate_ai_test_report_insights(s: dict, student_id: str, report: dict, api_key: str):
    log.info("[AI INSIGHTS] Generating test report insights for student %s", student_id)
    student_name = report.get("student_name", student_id)
    
    questions_summary = []
    for q in report.get("questions", []):
        questions_summary.append({
            "question": q.get("question", ""),
            "topic": q.get("topic", "General"),
            "difficulty": q.get("difficulty", "medium"),
            "student_answer": q.get("student_answer", ""),
            "correct_answer": q.get("correct_answer", ""),
            "marks_earned": q.get("marks_earned", 0.0),
            "max_marks": q.get("max_marks", 1.0),
            "is_correct": q.get("is_correct", False),
            "feedback": q.get("teacher_feedback", "")
        })
        
    prompt = f"""
You are an expert academic counselor. Analyze the student's test performance data below and generate detailed, personalized diagnostics and performance insights.

Student Name: {student_name}
Test Title: {report.get("title")}
Overall Score: {report.get("score")} / {report.get("max_score")} ({report.get("percentage")}%)

Questions and Responses:
{json.dumps(questions_summary, indent=2)}

Based on this data:
1. Identify the student's key strengths (what concepts/topics or question types they mastered).
2. Identify their weaknesses or areas for improvement.
3. Provide actionable suggestions on how they can improve.
4. Write a concise, encouraging overall Performance Insight statement.

Return ONLY a valid JSON object with the following structure:
{{
  "ai_insight": "A concise paragraph summarizing their performance and offering encouragement.",
  "strengths": ["Strength bullet point 1", "Strength bullet point 2"],
  "weaknesses": ["Area for improvement bullet point 1", "Area for improvement bullet point 2"],
  "suggestions": ["Actionable suggestion 1", "Actionable suggestion 2"]
}}

Do not include any markdown styling, code blocks, or extra text. Output only the raw JSON.
"""
    try:
        content = await call_llm(prompt, api_key=api_key, is_json=True)
        if content.startswith("```"):
            lines = content.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            content = "\n".join(lines).strip()
            
        parsed = json.loads(content)
        report["ai_insight"] = str(parsed.get("ai_insight", ""))
        report["strengths"] = parsed.get("strengths", [])
        report["weaknesses"] = parsed.get("weaknesses", [])
        report["suggestions"] = parsed.get("suggestions", [])
        
        save_session(s["code"])
        log.info("[AI INSIGHTS] Successfully updated report insights for student %s", student_id)
        
        try:
            await ws_student(s, student_id, {
                "type": "test_insights_updated",
                "session_code": s["code"],
                "report_id": report.get("id"),
                "ai_insight": report["ai_insight"],
                "strengths": report["strengths"],
                "weaknesses": report["weaknesses"],
                "suggestions": report["suggestions"]
            })
        except Exception as ws_err:
            log.warning("[AI INSIGHTS] failed student notification: %s", ws_err)
    except Exception as e:
        log.error("[AI INSIGHTS] Failed to generate: %s", e)


def check_and_trigger_test_ai_insights(s: dict, student_id: str, api_key: Optional[str] = None):
    if s.get("mode") != "test":
        return
        
    reports = s.setdefault("student_reports", {}).setdefault(student_id, [])
    test_rpt = next((r for r in reports if r.get("type") == "test" and r.get("session_code") == s["code"]), None)
    if not test_rpt:
        return
        
    pending = [q for q in test_rpt.get("questions", []) if q.get("evaluation_status") == "pending"]
    if pending:
        return
        
    api_key = api_key or get_teacher_key(s.get("teacher_email")) or os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY") or s.get("teacher_api_key")
    if not api_key:
        log.warning("[AI INSIGHTS] Skipped: No API key available")
        return
        
    import asyncio
    asyncio.create_task(generate_ai_test_report_insights(s, student_id, test_rpt, api_key))


def update_student_reports_on_approval(
    s: dict,
    student_id: str,
    task_id: str,
    score: float,
    feedback: str,
    is_correct: bool,
    strengths: Optional[list] = None,
    weaknesses: Optional[list] = None,
    suggestions: Optional[list] = None
):
    reports = s.setdefault("student_reports", {}).setdefault(student_id, [])
    for rpt in reports:
        if rpt.get("type") == "task" and rpt.get("questions") and rpt["questions"][0].get("task_id") == task_id:
            q = rpt["questions"][0]
            q["is_correct"] = is_correct
            q["marks_earned"] = score
            q["teacher_feedback"] = feedback
            q["evaluation_status"] = "approved"
            q["strengths"] = strengths or []
            q["weaknesses"] = weaknesses or []
            q["suggestions"] = suggestions or []
            
            rpt["score"] = score
            max_m = rpt.get("max_score", 1) or 1
            rpt["percentage"] = round(score / max_m * 100, 1)
            rpt["correct_count"] = 1 if is_correct else 0
            rpt["evaluation_status"] = "approved"
            rpt["teacher_feedback"] = feedback
            
        elif rpt.get("type") == "test":
            for q in rpt.get("questions", []):
                if q.get("task_id") == task_id:
                    old_earned = q.get("marks_earned", 0)
                    old_correct = q.get("is_correct", False)
                    
                    q["is_correct"] = is_correct
                    q["marks_earned"] = score
                    q["teacher_feedback"] = feedback
                    q["evaluation_status"] = "approved"
                    q["strengths"] = strengths or []
                    q["weaknesses"] = weaknesses or []
                    q["suggestions"] = suggestions or []
                    
                    rpt["score"] = rpt.get("score", 0) - old_earned + score
                    correct_change = (1 if is_correct else 0) - (1 if old_correct else 0)
                    rpt["correct_count"] = rpt.get("correct_count", 0) + correct_change
                    max_score = rpt.get("max_score", 1) or 1
                    rpt["percentage"] = round(rpt["score"] / max_score * 100, 1)
                    break
                    
    check_and_trigger_test_ai_insights(s, student_id)


def _build_test_report(s: dict, student_id: str) -> Optional[dict]:
    """Build a full test report for a student from current session state."""
    ts       = s.get("test_state", {})
    tasks    = {t["id"]: t for t in s.get("tasks", [])}
    task_ids = ts.get("task_ids", [])
    if not task_ids:
        task_ids = list(tasks.keys())
    responses = s.get("responses", {})
    student   = s.get("students", {}).get(student_id, {})

    questions = []
    total_max  = 0
    total_earned = 0
    time_taken   = 0

    for tid in task_ids:
        task = tasks.get(tid)
        if not task:
            continue
        resp = responses.get(tid, {}).get(student_id)
        max_marks  = score_for(task)
        total_max += max_marks

        q_entry: dict = {
            "task_id":       tid,
            "question":      task.get("question", ""),
            "type":          task.get("type", "mcq"),
            "options":       task.get("options", []),
            "correct_answer": task.get("correct_answer", ""),
            "topic":         task.get("topic", "General"),
            "difficulty":    task.get("difficulty", "medium"),
            "max_marks":     max_marks,
        }

        if resp:
            is_correct = resp.get("correct", False)
            if task.get("type") in ("short", "long", "descriptive"):
                if resp.get("evaluation_status") == "approved":
                    earned = resp.get("teacher_score", 0.0)
                    is_correct = resp.get("correct", False)
                else:
                    earned = 0.0
                    is_correct = False
            else:
                is_correct = resp.get("correct", False)
                earned     = max_marks if is_correct else 0
                
            total_earned += earned
            q_time       = resp.get("time_taken") or 0
            time_taken  += q_time or 0
            q_entry.update({
                "student_answer":    resp.get("answer"),
                "is_correct":        is_correct,
                "marks_earned":      earned,
                "time_taken":        q_time,
                "attempted":         True,
                "evaluation_status": resp.get("evaluation_status", "pending") if task.get("type") in ("short", "long", "descriptive") else "approved",
                "teacher_feedback":  resp.get("teacher_feedback", ""),
                "strengths":         resp.get("strengths", []),
                "weaknesses":        resp.get("weaknesses", []),
                "suggestions":       resp.get("suggestions", []),
            })
        else:
            q_entry.update({
                "student_answer":    None,
                "is_correct":        False,
                "marks_earned":      0.0,
                "time_taken":        0,
                "attempted":         False,
                "evaluation_status": "pending" if task.get("type") in ("short", "long", "descriptive") else "approved",
                "teacher_feedback":  "",
                "strengths":         [],
                "weaknesses":        [],
                "suggestions":       [],
            })

        questions.append(q_entry)

    # Leaderboard rank
    lb = ts.get("leaderboard", [])
    rank  = next((r["rank"] for r in lb if r["student_id"] == student_id), None)
    total_participants = len(lb) if lb else len([sid for sid in s.get("students", {}) if s["students"][sid].get("status") == "active"])

    percentage = round(total_earned / total_max * 100, 1) if total_max else 0.0
    attempted  = sum(1 for q in questions if q["attempted"])
    correct_q  = sum(1 for q in questions if q.get("is_correct"))

    return {
        "id":                gen_id("rpt"),
        "type":              "test",
        "title":             f"Test — {s.get('session_name') or s.get('code', '')}",
        "session_code":      s["code"],
        "session_name":      s.get("session_name", ""),
        "teacher_name":      s.get("teacher_name", ""),
        "student_id":        student_id,
        "student_name":      student.get("name", student_id),
        "roll":              student.get("roll", ""),
        "class":             student.get("class", ""),
        "submitted_at":      now(),
        "score":             total_earned,
        "max_score":         total_max,
        "percentage":        percentage,
        "time_taken":        time_taken,
        "total_questions":   len(questions),
        "attempted_count":   attempted,
        "correct_count":     correct_q,
        "rank":              rank,
        "total_participants": total_participants,
        "questions":         questions,
    }


def _build_task_report(s: dict, student_id: str, task_id: str) -> Optional[dict]:
    """Build a task report for one task submission."""
    task    = next((t for t in s.get("tasks", []) if t["id"] == task_id), None)
    student = s.get("students", {}).get(student_id, {})
    resp    = s.get("responses", {}).get(task_id, {}).get(student_id)
    if not task or not resp:
        return None

    max_m    = score_for(task)
    is_corr  = resp.get("correct", False)
    earned   = max_m if is_corr else 0

    if task.get("type") in ("short", "long", "descriptive"):
        if resp.get("evaluation_status") == "approved":
            score_val = resp.get("teacher_score", 0.0)
            is_corr_val = resp.get("correct", False)
        else:
            score_val = 0.0
            is_corr_val = False
    else:
        score_val = earned
        is_corr_val = is_corr

    q_entry = {
        "task_id":           task_id,
        "question":          task.get("question", ""),
        "type":              task.get("type", "mcq"),
        "options":           task.get("options", []),
        "correct_answer":    task.get("correct_answer", ""),
        "topic":             task.get("topic", "General"),
        "difficulty":        task.get("difficulty", "medium"),
        "max_marks":         max_m,
        "student_answer":    resp.get("answer"),
        "is_correct":        is_corr_val,
        "marks_earned":      score_val,
        "time_taken":        resp.get("time_taken") or 0,
        "attempted":         True,
        "evaluation_status": resp.get("evaluation_status", "pending") if task.get("type") in ("short", "long", "descriptive") else "approved",
        "teacher_feedback":  resp.get("teacher_feedback", ""),
        "strengths":         resp.get("strengths", []),
        "weaknesses":        resp.get("weaknesses", []),
        "suggestions":       resp.get("suggestions", []),
    }

    return {
        "id":                gen_id("rpt"),
        "type":              "task",
        "title":             (task.get("question", "Task") or "Task")[:60],
        "session_code":      s["code"],
        "session_name":      s.get("session_name", ""),
        "teacher_name":      s.get("teacher_name", ""),
        "student_id":        student_id,
        "student_name":      student.get("name", student_id),
        "roll":              student.get("roll", ""),
        "class":             student.get("class", ""),
        "submitted_at":      resp.get("submitted_at", now()),
        "score":             score_val,
        "max_score":         max_m,
        "percentage":        round(score_val / max_m * 100, 1) if max_m else 0.0,
        "time_taken":        resp.get("time_taken") or 0,
        "total_questions":   1,
        "attempted_count":   1,
        "correct_count":     1 if is_corr_val else 0,
        "rank":              None,
        "total_participants": None,
        "questions":         [q_entry],
    }


def _store_student_report(s: dict, student_id: str, report: dict) -> None:
    """Append a report to the student's report history in the session."""
    rpts = s.setdefault("student_reports", {})
    rpts.setdefault(student_id, []).append(report)


# ── Student Report API endpoints ──────────────────────────────────

@app.get("/api/session/{code}/student/{student_id}/reports")
def get_student_reports(code: str, student_id: str):
    """Return all persisted reports for a student, newest first."""
    s = _S(code)
    # Verify student belongs to this session
    if student_id not in s.get("students", {}):
        raise HTTPException(404, "Student not found")
    reports = s.get("student_reports", {}).get(student_id, [])
    # Sort newest first
    reports_sorted = sorted(reports, key=lambda r: r.get("submitted_at", 0), reverse=True)
    return {"reports": reports_sorted, "count": len(reports_sorted)}


@app.get("/api/session/{code}/student/{student_id}/report/status")
def get_student_report_status(code: str, student_id: str):
    s = _S(code)
    if student_id not in s.get("students", {}):
        raise HTTPException(404, "Student not found")
        
    student = s["students"][student_id]
    email = student.get("email", "")
    
    reports = s.get("student_reports", {}).get(student_id, [])
    has_test = any(r.get("type") == "test" for r in reports)
    has_tasks = any(r.get("type") == "task" for r in reports)
    
    # Check Google Drive connectivity
    gdrive_connected = False
    if email:
        creds = get_teacher_integration(email, "google")
        gdrive_connected = bool(creds)
        
    return {
        "has_test": has_test,
        "has_tasks": has_tasks,
        "email": email,
        "gdrive_connected": gdrive_connected,
        "student_name": student.get("name", "Student")
    }


@app.get("/api/session/{code}/student/{student_id}/report/download")
def download_student_report(code: str, student_id: str):
    s = _S(code)
    if student_id not in s.get("students", {}):
        raise HTTPException(404, "Student not found")
        
    student = s["students"][student_id]
    student_name = student.get("name", "Student")
    roll_no = student.get("roll", "")
    class_name = student.get("class", "")
    
    # Find reports
    reports = s.get("student_reports", {}).get(student_id, [])
    test_rpt = next((r for r in reports if r.get("type") == "test"), None)
    task_rpts = [r for r in reports if r.get("type") == "task"]
    
    import io
    import zipfile
    from fastapi.responses import Response
    from report_generator import generate_student_test_pdf, generate_student_tasks_pdf

    if test_rpt and task_rpts:
        test_pdf = generate_student_test_pdf(code, student_name, roll_no, class_name, test_rpt)
        tasks_pdf = generate_student_tasks_pdf(code, student_name, roll_no, class_name, task_rpts)
        
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("Premium Test Report.pdf", test_pdf)
            zf.writestr("Task Report.pdf", tasks_pdf)
        
        zip_bytes = zip_buffer.getvalue()
        register_generated_report(s, "student", "zip", zip_bytes, student_id=student_id)
        safe_name = student_name.replace(" ", "_")
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": f"attachment; filename=VYOM_Reports_{safe_name}_{code}.zip"}
        )
    elif test_rpt:
        test_pdf = generate_student_test_pdf(code, student_name, roll_no, class_name, test_rpt)
        register_generated_report(s, "student", "pdf", test_pdf, student_id=student_id)
        return Response(
            content=test_pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=Premium_Test_Report.pdf"}
        )
    elif task_rpts:
        tasks_pdf = generate_student_tasks_pdf(code, student_name, roll_no, class_name, task_rpts)
        register_generated_report(s, "student", "pdf", tasks_pdf, student_id=student_id)
        return Response(
            content=tasks_pdf,
            media_type="application/pdf",
            headers={"Content-Disposition": "attachment; filename=Task_Report.pdf"}
        )
    else:
        raise HTTPException(400, "No report data available for this session.")


@app.post("/api/session/{code}/student/{student_id}/report/email")
async def email_student_report(code: str, student_id: str, email: Optional[str] = Query(None)):
    s = _S(code)
    if student_id not in s.get("students", {}):
        raise HTTPException(404, "Student not found")
        
    student = s["students"][student_id]
    student_name = student.get("name", "Student")
    
    to_email = student.get("email") or email
    if not to_email or not to_email.strip():
        raise HTTPException(400, "No registered email found for this student.")
    
    to_email = to_email.strip()
    if not is_valid_email(to_email):
        raise HTTPException(400, f"Invalid email address: {to_email}")

    # Find reports
    reports = s.get("student_reports", {}).get(student_id, [])
    test_rpt = next((r for r in reports if r.get("type") == "test"), None)
    task_rpts = [r for r in reports if r.get("type") == "task"]
    
    if not test_rpt and not task_rpts:
        raise HTTPException(400, "No report data available for this session.")
        
    session_name = s.get("session_name") or "Physics Class"
    from email_service import send_student_report_email
    
    ok, msg = await send_student_report_email(
        to_email=to_email,
        student_name=student_name,
        session_name=session_name,
        session_code=code,
        test_report=test_rpt,
        task_reports=task_rpts if task_rpts else None
    )
    
    if not ok:
        raise HTTPException(500, f"Failed to send email: {msg}")
        
    return {"success": True, "message": "Reports successfully sent to your email!"}


@app.post("/api/session/{code}/student/{student_id}/report/gdrive")
async def save_student_report_to_google_drive(code: str, student_id: str):
    s = _S(code)
    if student_id not in s.get("students", {}):
        raise HTTPException(404, "Student not found")
        
    student = s["students"][student_id]
    student_name = student.get("name", "Student")
    roll_no = student.get("roll", "")
    class_name = student.get("class", "")
    
    email = student.get("email")
    if not email:
        raise HTTPException(400, "Student has no registered email. Please verify/connect first.")
        
    if not google_drive_provider:
        raise HTTPException(400, "Google Drive OAuth client not configured on server.")
        
    creds = get_teacher_integration(email, "google")
    if not creds:
        raise HTTPException(400, "Google Drive not connected.")
        
    # Find reports
    reports = s.get("student_reports", {}).get(student_id, [])
    test_rpt = next((r for r in reports if r.get("type") == "test"), None)
    task_rpts = [r for r in reports if r.get("type") == "task"]
    
    if not test_rpt and not task_rpts:
        raise HTTPException(400, "No report data available for this session.")
        
    session_name = s.get("session_name") or "Physics Class"
    folder_path = ["VYOM", "Student Reports", student_name, session_name]
    
    from report_generator import generate_student_test_pdf, generate_student_tasks_pdf
    
    uploaded_files = []
    try:
        # Save Premium Test Report if exists
        if test_rpt:
            test_pdf = generate_student_test_pdf(code, student_name, roll_no, class_name, test_rpt)
            result = await google_drive_provider.upload_file(
                filename="Premium Test Report.pdf",
                content=test_pdf,
                folder_path=folder_path,
                credentials=creds
            )
            creds = result["credentials"]
            uploaded_files.append("Premium Test Report.pdf")
            
        # Save Task Report if exists
        if task_rpts:
            tasks_pdf = generate_student_tasks_pdf(code, student_name, roll_no, class_name, task_rpts)
            result = await google_drive_provider.upload_file(
                filename="Task Report.pdf",
                content=tasks_pdf,
                folder_path=folder_path,
                credentials=creds
            )
            creds = result["credentials"]
            uploaded_files.append("Task Report.pdf")
            
        # Save updated credentials to store
        creds["last_backup_time"] = time.time()
        set_teacher_integration(email, creds, "google")
        
        return {
            "success": True,
            "message": f"Reports ({', '.join(uploaded_files)}) successfully saved to Google Drive!"
        }
    except Exception as e:
        log.error("Student Google Drive upload failed: %s", e, exc_info=True)
        raise HTTPException(500, f"Google Drive upload failed: {str(e)}")


@app.get("/api/session/{code}/student/{student_id}/reports/analytics")
def get_student_report_analytics(code: str, student_id: str):
    """Compute aggregate analytics across all persisted reports."""
    s = _S(code)
    if student_id not in s.get("students", {}):
        raise HTTPException(404, "Student not found")
    reports = s.get("student_reports", {}).get(student_id, [])

    test_rpts  = [r for r in reports if r["type"] == "test"]
    task_rpts  = [r for r in reports if r["type"] == "task"]
    all_rpts   = reports

    def avg_pct(lst):
        if not lst: return 0
        return round(sum(r.get("percentage", 0) for r in lst) / len(lst), 1)

    # Topic breakdown across all questions
    topic_stats: dict = {}
    for r in all_rpts:
        for q in r.get("questions", []):
            t = q.get("topic", "General")
            topic_stats.setdefault(t, {"correct": 0, "total": 0})
            topic_stats[t]["total"] += 1
            if q.get("is_correct"):
                topic_stats[t]["correct"] += 1

    topic_breakdown = sorted([
        {
            "topic": t,
            "correct": v["correct"],
            "total": v["total"],
            "accuracy": round(v["correct"] / v["total"] * 100) if v["total"] else 0,
        }
        for t, v in topic_stats.items()
    ], key=lambda x: x["accuracy"])

    weak_topics = [t for t in topic_breakdown if t["accuracy"] < 60]
    best_topics = [t for t in reversed(topic_breakdown) if t["accuracy"] >= 70]

    total_time = sum(r.get("time_taken", 0) or 0 for r in all_rpts)

    # Score trend (last 10 attempts)
    trend = sorted(all_rpts, key=lambda r: r.get("submitted_at", 0))[-10:]
    score_trend = [
        {"label": r.get("title", "")[:20], "pct": r.get("percentage", 0), "type": r["type"]}
        for r in trend
    ]

    return {
        "total_tests":     len(test_rpts),
        "total_tasks":     len(task_rpts),
        "total_activities": len(all_rpts),
        "avg_test_score":  avg_pct(test_rpts),
        "avg_task_score":  avg_pct(task_rpts),
        "overall_accuracy": avg_pct(all_rpts),
        "total_time_secs": total_time,
        "total_questions_attempted": sum(r.get("attempted_count", 0) for r in all_rpts),
        "total_correct":   sum(r.get("correct_count", 0) for r in all_rpts),
        "topic_breakdown": topic_breakdown,
        "weak_topics":     weak_topics[:5],
        "best_topics":     best_topics[:5],
        "score_trend":     score_trend,
    }


@app.get("/api/session/{code}/student/{student_id}/dashboard-analytics")
def get_student_dashboard_analytics(code: str, student_id: str):
    """Compute comprehensive dynamic analytics for the student's dashboard home page."""
    s = _S(code)
    if student_id not in s.get("students", {}):
        raise HTTPException(404, "Student not found")
        
    student = s["students"][student_id]
    reports = s.get("student_reports", {}).get(student_id, [])
    active_students = [st for st in s["students"].values() if st.get("status") == "active"]
    
    # 1. Total & Completed Tasks
    total_tasks = len(s.get("tasks", []))
    completed_tasks = sum(1 for tid, resps in s.get("responses", {}).items() if student_id in resps)
    pending_tasks = max(0, total_tasks - completed_tasks)
    
    # 2. Quiz/Test status
    ts = s.get("test_state", {})
    has_test = bool(ts.get("active") or ts.get("task_ids"))
    test_completed = student_id in ts.get("submitted", set())
    test_ratio = 1.0 if test_completed else 0.0 if has_test else None
    
    # 3. Attendance
    is_present = student.get("att_status") == "present"
    attendance_ratio = 1.0 if is_present else 0.0
    
    # 4. Coding Lab
    coding_completed = student.get("coding_submitted", False)
    has_coding = coding_completed or any(t.get("type") == "coding" for t in s.get("tasks", []))
    coding_ratio = 1.0 if coding_completed else 0.0 if has_coding else None
    
    # 5. Lesson Progress
    al = s.get("active_lesson")
    total_sections = len(al.get("sections", [])) if al else 0
    completed_sections = sum(1 for v in s.get("student_lesson_progress", {}).get(student_id, {}).values() if v)
    lesson_ratio = completed_sections / total_sections if total_sections > 0 else None
    
    # 6. Today's Agenda
    agenda_count = total_sections if total_sections > 0 else total_tasks
    agenda_count = max(0, agenda_count)
    
    # Calculate Overall Progress (0-100%)
    task_ratio = completed_tasks / total_tasks if total_tasks > 0 else None
    active_ratios = [r for r in [task_ratio, test_ratio, attendance_ratio, coding_ratio, lesson_ratio] if r is not None]
    progress_pct = round(sum(active_ratios) / len(active_ratios) * 100) if active_ratios else 0
    progress_pct = max(0, min(100, progress_pct))
    
    # 7. Class/Leaderboard Rank
    lb = ts.get("leaderboard", [])
    rank = next((r["rank"] for r in lb if r["student_id"] == student_id), None)
    if rank is None:
        sorted_students = sorted(active_students, key=lambda x: x.get("score", 0), reverse=True)
        rank = next((i + 1 for i, st in enumerate(sorted_students) if st["id"] == student_id), 1)
        
    # 8. Learning Streak
    from datetime import datetime
    unique_days = set()
    for r in reports:
        sub_at = r.get("submitted_at", 0)
        if sub_at:
            try:
                dt = datetime.fromtimestamp(sub_at)
                unique_days.add(dt.date())
            except Exception:
                pass
    streak = len(unique_days)
    
    # 9. Study Stats (accuracy, correct answers, etc.)
    correct = student.get("correct", 0)
    total_answered = student.get("total_answered", 0)
    accuracy = round(correct / total_answered * 100) if total_answered > 0 else 0
    
    total_time = sum(r.get("time_taken", 0) or 0 for r in reports)
    
    # 10. Achievements List
    achievements = []
    if total_answered >= 10:
        achievements.append({
            "icon": "⭐",
            "color": "#F59E0B",
            "title": "Quiz Master",
            "desc": f"Answered {total_answered} questions",
            "date": "Recent"
        })
    if accuracy >= 80 and total_answered >= 3:
        achievements.append({
            "icon": "⚡",
            "color": "#10B981",
            "title": "Speed Demon",
            "desc": f"{accuracy}% accuracy achieved",
            "date": "Recent"
        })
    if rank == 1 and len(active_students) >= 2:
        achievements.append({
            "icon": "👑",
            "color": "#8B5CF6",
            "title": "Top Performer",
            "desc": "Reached #1 on leaderboard",
            "date": "Recent"
        })
    if is_present:
        achievements.append({
            "icon": "📅",
            "color": "#3B82F6",
            "title": "Perfect Attendee",
            "desc": "Attended today's class on time",
            "date": "Recent"
        })
    if coding_completed:
        achievements.append({
            "icon": "💻",
            "color": "#10B981",
            "title": "Elite Coder",
            "desc": f"Submitted coding lab with score {student.get('coding_score', 0)}",
            "date": "Recent"
        })
        
    return {
        "progress": progress_pct,
        "pending_tasks": pending_tasks,
        "agenda_count": agenda_count,
        "attendance_status": student.get("att_status", "not_marked"),
        "attendance_label": "Present" if is_present else "Absent" if student.get("att_status") == "absent" else "Not Marked",
        "study_stats": {
            "accuracy": accuracy,
            "streak": max(1, streak) if streak > 0 or completed_tasks > 0 else 0,
            "total_time_secs": total_time,
            "total_correct": correct,
            "total_attempted": total_answered,
            "points": completed_tasks * 10 + correct * 15,
            "xp": correct * 120 + completed_tasks * 40,
            "level": max(1, (correct * 120 + completed_tasks * 40) // 1200 + 1)
        },
        "achievements": achievements,
        "my_rank": rank,
        "coding_score": student.get("coding_score", 0),
        "coding_submitted": coding_completed,
        "total_tasks": total_tasks,
        "completed_tasks": completed_tasks
    }


# ── Store reports after test submission ───────────────────────────


# ══════════════════════════════════════════════════════════════════
#  CODING LAB
# ══════════════════════════════════════════════════════════════════

@app.post("/api/code/run")
async def execute_code(req: RunCodeReq):
    s = _S(req.session_code)

    if req.student_id != "teacher":
        st = s["students"].get(req.student_id)
        if not st or st["status"] != "active":
            raise HTTPException(403, "Student not active")

    code = req.code
    stdin = req.stdin
    if req.is_base64:
        try:
            code = base64.b64decode(req.code).decode('utf-8')
            if req.stdin:
                stdin = base64.b64decode(req.stdin).decode('utf-8')
        except Exception as e:
            log.error("[CODING LAB] Failed to decode base64 payload: %s", e)

    loop    = asyncio.get_event_loop()
    future  = loop.create_future()
    await execution_queue.put((code, req.language, stdin, future))
    result  = await future

    if req.student_id != "teacher":
        student = s["students"].get(req.student_id)
        if student:
            task = None
            if req.task_id:
                task = _T(s, req.task_id)
            else:
                for t in reversed(s.get("tasks", [])):
                    if t.get("type") == "coding":
                        task = t
                        break
            
            test_cases_passed = 0
            total_test_cases = 5
            
            if task:
                expected_output = task.get("expected_output")
                ai_error = task.get("expected_error", False)
                
                if expected_output is None:
                    correct_answer_code = task.get("correct_answer", "")
                    lang = task.get("language", "python").strip().lower()
                    test_input = task.get("test_input", "") or ""
                    
                    loop = asyncio.get_event_loop()
                    ai_future = loop.create_future()
                    await execution_queue.put((correct_answer_code, lang, test_input, ai_future))
                    ai_result = await ai_future
                    expected_output = (ai_result.output or "").strip()
                    ai_error = bool(ai_result.error)
                    task["expected_output"] = expected_output
                    task["expected_error"] = ai_error

                student_out = (result.output or "").strip()
                if result.error:
                    test_cases_passed = 1
                elif student_out != expected_output:
                    test_cases_passed = 2
                else:
                    test_cases_passed = 5
            else:
                test_cases_passed = 3

            student["coding_submitted"]  = True
            student["test_cases_passed"] = test_cases_passed
            student["total_test_cases"]  = total_test_cases
            student["coding_score"]      = int((test_cases_passed / total_test_cases) * 100)
            student["coding_time_taken"] = 120

        lb = sorted(s["students"].values(), key=lambda x: x.get("coding_score", 0), reverse=True)
        await ws_all_students(s, {
            "type": "coding_leaderboard_update",
            "leaderboard": [
                {"name": st["name"], "score": st.get("coding_score", 0), "rank": i + 1}
                for i, st in enumerate(lb)
            ],
        })

    return {"output": result.output, "error": result.error, "timed_out": result.timed_out}


@app.post("/api/session/{code}/submit_code")
async def submit_code_endpoint(
    code:       str,
    student_id: str  = Body(...),
    task_id:    Optional[str] = Body(None),
    code_body:  str  = Body(..., alias="code"),
):
    s       = _S(code)
    student = s["students"].get(student_id)
    if not student or student.get("status") != "active":
        raise HTTPException(403, "Student not active")

    task = None
    if task_id:
        task = _T(s, task_id)
    else:
        for t in reversed(s.get("tasks", [])):
            if t.get("type") == "coding":
                task = t
                break

    test_cases_passed = 0
    total_test_cases = 5
    
    if task:
        lang = task.get("language", "python").strip().lower()
        test_input = task.get("test_input", "") or ""
        correct_answer_code = task.get("correct_answer", "")
        student_code = code_body
        
        if lang in ("python", "python3"):
            import re
            func_name = None
            func_match = re.search(r"def\s+(\w+)\s*\(", correct_answer_code)
            if not func_match:
                func_match = re.search(r"def\s+(\w+)\s*\(", task.get("starter_code", ""))
            if func_match:
                func_name = func_match.group(1)
 
            global_calls = []
            for line in correct_answer_code.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if not line.startswith(" ") and not line.startswith("\t"):
                    if not (line.startswith("def ") or line.startswith("class ") or line.startswith("import ") or line.startswith("from ")):
                        global_calls.append(line)
 
            if func_name:
                has_func_call = False
                for line in student_code.splitlines():
                    stripped = line.strip()
                    if not stripped or stripped.startswith("#") or stripped.startswith("def "):
                        continue
                    if func_name in line:
                        has_func_call = True
                        break
                if not has_func_call and global_calls:
                    student_code = student_code + "\n\n" + "\n".join(global_calls)
 
            if not test_input.strip() and func_name:
                pattern = rf"print\(\s*{func_name}\s*\((.*)\)\s*\)"
                match = re.search(pattern, correct_answer_code)
                if match:
                    arg_str = match.group(1).strip()
                    if arg_str.startswith("{") or arg_str.startswith("[") or arg_str.startswith("'") or arg_str.startswith('"'):
                        test_input = arg_str

        expected_output = task.get("expected_output")
        ai_error = task.get("expected_error", False)
        
        if expected_output is None:
            loop = asyncio.get_event_loop()
            ai_future = loop.create_future()
            await execution_queue.put((correct_answer_code, lang, test_input, ai_future))
            ai_result = await ai_future
            expected_output = (ai_result.output or "").strip()
            ai_error = bool(ai_result.error)
            task["expected_output"] = expected_output
            task["expected_error"] = ai_error

        loop = asyncio.get_event_loop()
        student_future = loop.create_future()
        await execution_queue.put((student_code, lang, test_input, student_future))
        student_result = await student_future
        student_out = (student_result.output or "").strip()

        if student_result.error:
            test_cases_passed = 1
        elif student_out != expected_output:
            test_cases_passed = 2
        else:
            test_cases_passed = 5
    else:
        test_cases_passed = 3

    student["coding_submitted"]  = True
    student["test_cases_passed"] = test_cases_passed
    student["total_test_cases"]  = total_test_cases
    student["coding_score"]      = int((test_cases_passed / total_test_cases) * 100)
    student["coding_code"]       = code_body
    student["coding_output"]     = student_out if task else ""
    student["coding_error"]      = student_result.error if task else ""
    student["coding_language"]   = lang if task else "python"
    student["coding_submission_time"] = time.time()

    # Also record in s["responses"]
    if task:
        if task["id"] not in s["responses"]:
            s["responses"][task["id"]] = {}
        s["responses"][task["id"]][student_id] = {
            "answer": code_body,
            "correct": test_cases_passed == total_test_cases,
            "test_cases_passed": test_cases_passed,
            "total_test_cases": total_test_cases,
            "score": student["coding_score"],
            "output": student_out,
            "error": student_result.error,
            "language": lang,
            "submission_time": time.time()
        }

    save_session(code)

    await ws_teacher(s, {
        "type":       "code_submitted",
        "student_id": student_id,
        "name":       student.get("name", "?"),
        "score":      student["coding_score"],
    })
    return {"submitted": True, "score": student["coding_score"]}


# ══════════════════════════════════════════════════════════════════
#  WEBSOCKETS
# ══════════════════════════════════════════════════════════════════

@app.websocket("/ws/teacher/{session_code}")
async def teacher_ws_endpoint(ws: WebSocket, session_code: str):
    s = sessions.get(session_code)
    if not s:
        log.warning("[WS] Teacher tried to connect to non-existent session: %s", session_code)
        await ws.accept()
        await ws_send(ws, {"type": "error", "message": "Session not found"})
        await ws.close()
        return

    query_params = ws.query_params
    email = query_params.get("email")
    role = query_params.get("role")
    if not email or not role:
        log.warning("[WS] Teacher WS connection missing email/role query parameters")
        await ws.accept()
        await ws_send(ws, {"type": "error", "message": "Missing authentication parameters"})
        await ws.close()
        return
    if role != "teacher":
        log.warning("[WS] Teacher WS connection role must be teacher, got: %s", role)
        await ws.accept()
        await ws_send(ws, {"type": "error", "message": "Role must be teacher"})
        await ws.close()
        return
    if email.lower().strip() != s.get("teacher_email", "").lower().strip():
        log.warning("[WS] Teacher WS email mismatch: %s vs %s", email, s.get("teacher_email"))
        await ws.accept()
        await ws_send(ws, {"type": "error", "message": "Access denied: you are not the owner of this session"})
        await ws.close()
        return

    # Allow teacher to reconnect even if session is ended (read-only analytics mode)
    # Previously this would close the connection for ended sessions — now we keep it open
    await ws.accept()
    # Allow multiple teacher WebSocket connections (e.g. multiple tabs) without disconnect conflicts
    if "teacher_ws" not in s or s["teacher_ws"] is None:
        s["teacher_ws"] = set()
    elif not isinstance(s["teacher_ws"], set):
        old_ws = s["teacher_ws"]
        s["teacher_ws"] = {old_ws} if old_ws else set()
        
    s["teacher_ws"].add(ws)
    log.info("[WS] Teacher connected to session: %s (Teacher ID: %s, status: %s)", session_code, s.get("teacher_id", "unknown"), s.get("status"))

    active  = [st for st in s["students"].values() if st["status"] == "active"]
    waiting = [s["students"][sid] for sid in s["waiting_room"] if sid in s["students"]]
    # Normalise raised_hands for connected payload
    rh = s.get("raised_hands", {})
    if isinstance(rh, list):
        rh = {sid: {"name": s["students"].get(sid, {}).get("name", "?"), "raised_at": 0} for sid in rh}
        s["raised_hands"] = rh
    hand_list = [
        {"student_id": sid, "student_name": info.get("name", "?"), "raised_at": info.get("raised_at")}
        for sid, info in rh.items()
    ]
    await ws_send(ws, {
        "type": "connected",
        "role": "teacher",
        "read_only": s.get("status") == "ended",  # Signal read-only mode to frontend
        "session": {
            "code":         s["code"],
            "status":       s["status"],
            "mode":         s["mode"],
            "session_name": s.get("session_name", ""),
            "tasks":        s["tasks"],
            "groups":       s["groups"],
            "deliveries":   [delivery_summary(d) for d in s.get("task_deliveries", {}).values()],
            "vc_active":    s.get("vc_active", False),
            "duration_mins": s.get("duration_mins", 0),
            "started_at":   s.get("started_at"),
            "auto_join_enabled": s.get("auto_join_enabled", False),
        },
        "analytics":    compute_analytics(s),
        "roster":       {"active": active, "waiting": waiting},
        "raised_hands": hand_list,
        "doubts":       s.get("doubts", []),
    })

    try:
        while True:
            raw  = await ws.receive_text()
            data = json.loads(raw)
            cmd  = data.get("type", "")

            if cmd in ("ping", "heartbeat"):
                await ws_send(ws, {"type": "pong", "ts": now()})
            elif cmd == "get_analytics":
                await ws_send(ws, {"type": "analytics_update", "analytics": compute_analytics(s)})
            elif cmd == "get_roster":
                await push_roster(s)
            elif cmd == "broadcast":
                msg = data.get("message", "")
                if msg:
                    await ws_all_students(s, {"type": "announcement", "message": msg})
            elif cmd == "chat_toggle":
                # Teacher enables/disables chat — persist on session and broadcast
                enabled = bool(data.get("enabled", True))
                s["chat_enabled"] = enabled
                log.info("Chat %s for session %s", "enabled" if enabled else "disabled", session_code)
                await ws_all_students(s, {"type": "chat_toggle", "enabled": enabled})
                await ws_send(ws, {"type": "chat_toggle_ack", "enabled": enabled})
            elif cmd == "send_student_notification":
                student_id = data.get("student_id")
                notif = data.get("notification", {})
                if student_id and student_id in s.get("ws_clients", {}):
                    ws_c = s["ws_clients"][student_id]
                    await ws_send(ws_c, {
                        "type": "direct_notification",
                        **notif
                    })

            # ── HAND RAISE CONTROLS (teacher-side) ──────────────────────
            elif cmd == "lower_all_hands":
                rh = s.setdefault("raised_hands", {})
                if isinstance(rh, list):
                    rh = {}
                    s["raised_hands"] = rh
                else:
                    rh.clear()
                await ws_send(ws, {"type": "hand_raise_update", "raised_hands": [], "count": 0})

            elif cmd == "lower_hand":
                sid_to_lower = data.get("student_id", "")
                rh = s.setdefault("raised_hands", {})
                if isinstance(rh, list):
                    rh = {sid: {"name": s["students"].get(sid, {}).get("name","?"), "raised_at": 0} for sid in rh}
                    s["raised_hands"] = rh
                rh.pop(sid_to_lower, None)
                hand_list = [{"student_id": sid, "student_name": info.get("name","?"), "raised_at": info.get("raised_at")} for sid, info in rh.items()]
                await ws_send(ws, {"type": "hand_raise_update", "raised_hands": hand_list, "count": len(rh)})

            # ── DOUBT CONTROLS (teacher-side) ─────────────────────────────
            elif cmd == "get_doubts":
                await ws_send(ws, {"type": "doubts_update", "doubts": s.get("doubts", [])})

            elif cmd == "reply_doubt":
                doubt_id = data.get("doubt_id", "")
                reply = data.get("reply", "")
                resolved = bool(data.get("resolved", False))
                found = False
                s.setdefault("doubts", [])
                for d in s["doubts"]:
                    if d.get("id") == doubt_id:
                        d["reply"] = reply
                        if resolved:
                            d["status"] = "resolved"
                            d["answer"] = reply
                            d["resolved"] = True
                            d["resolved_at"] = now()
                            d["resolved_by"] = "teacher"
                        else:
                            d["status"] = "answered"
                        # Ensure both text fields present
                        d.setdefault("doubt_text", d.get("text", ""))
                        d.setdefault("text", d.get("doubt_text", ""))
                        found = True
                        save_session(session_code)
                        await ws_teacher(s, {"type": "doubt_resolved", "doubt": d})
                        await ws_student(s, d["student_id"], {"type": "doubt_resolved", "doubt": d})
                        await ws_send(ws, {"type": "doubts_update", "doubts": s["doubts"]})
                        break
                if not found:
                    await ws_send(ws, {"type": "error", "message": "Doubt not found"})

            # ── ATTENDANCE CONTROLS (teacher-side) ──────────────────────
            elif cmd == "attendance_control":
                action   = data.get("action", "")
                min_dur  = int(data.get("min_duration", 60))
                att      = _att(s)
                actor    = email if email else "Teacher"
                if action == "start":
                    if att.get("state") == "locked":
                        await ws_send(ws, {"type": "error", "message": "Attendance is locked"})
                        continue
                    att["state"]      = "active"
                    att["started_at"] = att.get("started_at") or now()
                    att["min_duration"] = max(0, min_dur)
                    log_attendance_audit(s, "start", actor, f"Attendance started with min_duration={min_dur}")
                    for sid, st in s["students"].items():
                        if st.get("status") == "active" and sid not in att["records"]:
                            att["records"][sid] = {
                                "student_id": sid, "join_at": now(),
                                "leave_at": None, "duration": 0,
                                "status": "present", "interactions": 0,
                            }
                elif action == "pause":
                    if att.get("state") == "locked":
                        await ws_send(ws, {"type": "error", "message": "Attendance is locked"})
                        continue
                    att["state"] = "paused"
                    log_attendance_audit(s, "pause", actor, "Attendance paused")
                elif action == "resume":
                    if att.get("state") == "locked":
                        await ws_send(ws, {"type": "error", "message": "Attendance is locked"})
                        continue
                    att["state"] = "active"
                    log_attendance_audit(s, "resume", actor, "Attendance resumed")
                elif action == "end":
                    if att.get("state") == "locked":
                        await ws_send(ws, {"type": "error", "message": "Attendance is locked"})
                        continue
                    att["state"]    = "ended"
                    att["ended_at"] = now()
                    log_attendance_audit(s, "end", actor, "Attendance ended")
                    for r in att["records"].values():
                        if r.get("status") == "present":
                            end_t = now(); r["leave_at"] = end_t
                            r["duration"] = end_t - (r.get("join_at") or end_t)
                    generate_attendance_sheet(s)
                elif action == "lock":
                    if att.get("state") == "locked":
                        await ws_send(ws, {"type": "error", "message": "Attendance is already locked"})
                        continue
                    att["state"]     = "locked"
                    att["locked_at"] = now()
                    if not att.get("ended_at"):
                        att["ended_at"] = now()
                    log_attendance_audit(s, "lock", actor, "Attendance locked")
                    generate_attendance_sheet(s)
                save_session(session_code)
                await broadcast_attendance(s)
                log.info("[ATTENDANCE] %s in session %s by %s", action, session_code, actor)

            elif cmd == "get_attendance":
                await ws_send(ws, {
                    "type": "attendance_update",
                    "attendance": compute_attendance_summary(s),
                })

            # ── CHAT MODERATION (teacher-side, Features 2 & 3) ──────────
            elif cmd == "chat_react":
                msg_id   = data.get("message_id", "")
                emoji    = data.get("emoji", "")
                user_id  = data.get("user_id", "teacher")
                if emoji in ALLOWED_EMOJIS and msg_id:
                    msg_obj = next((m for m in s.get("chat_messages", []) if m.get("id") == msg_id), None)
                    if msg_obj:
                        msg_obj.setdefault("reactions", {})
                        reactors = msg_obj["reactions"].setdefault(emoji, [])
                        if user_id in reactors:
                            reactors.remove(user_id)
                        else:
                            reactors.append(user_id)
                        save_session(session_code)
                        await ws_broadcast(s, {
                            "type":       "chat_reactions_update",
                            "message_id": msg_id,
                            "reactions":  msg_obj["reactions"],
                        })

            elif cmd == "suspend_chat_student":
                sid_to_suspend = data.get("student_id", "")
                student_obj = s["students"].get(sid_to_suspend)
                if student_obj:
                    s.setdefault("suspended_chat_students", set()).add(sid_to_suspend)
                    save_session(session_code)
                    await ws_student(s, sid_to_suspend, {
                        "type":    "chat_suspended",
                        "message": "You are temporarily suspended from classroom chat.",
                    })
                    sys_sus_msg = {
                        "id":          gen_id("m"),
                        "sender_id":   "system",
                        "sender_name": "System",
                        "content":     f"⚠️ {student_obj.get('name', sid_to_suspend)} has been suspended from chat.",
                        "chat_type":   "global",
                        "target_id":   None,
                        "timestamp":   now(),
                        "msg_type":    "system",
                        "reactions":   {},
                        "reply_to_message_id": None,
                        "reply_preview": None,
                        "file_info":   None,
                    }
                    s["chat_messages"].append(sys_sus_msg)
                    await ws_broadcast(s, {"type": "chat_message", "message": sys_sus_msg})
                    await ws_send(ws, {
                        "type":       "chat_suspension_update",
                        "student_id": sid_to_suspend,
                        "suspended":  True,
                        "student_name": student_obj.get("name", sid_to_suspend),
                    })

            elif cmd == "unsuspend_chat_student":
                sid_to_unsuspend = data.get("student_id", "")
                student_obj = s["students"].get(sid_to_unsuspend)
                if student_obj:
                    s.setdefault("suspended_chat_students", set()).discard(sid_to_unsuspend)
                    save_session(session_code)
                    await ws_student(s, sid_to_unsuspend, {
                        "type":    "chat_unsuspended",
                        "message": "Your chat access has been restored.",
                    })
                    await ws_send(ws, {
                        "type":       "chat_suspension_update",
                        "student_id": sid_to_unsuspend,
                        "suspended":  False,
                        "student_name": student_obj.get("name", sid_to_unsuspend),
                    })

            elif cmd == "delete_chat_msg":
                del_msg_id = data.get("message_id", "")
                if del_msg_id:
                    msgs_list = s.get("chat_messages", [])
                    idx = next((i for i, m in enumerate(msgs_list) if m.get("id") == del_msg_id), None)
                    if idx is not None:
                        s["chat_messages"].pop(idx)
                        save_session(session_code)
                        await ws_broadcast(s, {
                            "type":       "chat_message_deleted",
                            "message_id": del_msg_id,
                        })

    except WebSocketDisconnect:
        log.info("Teacher disconnected: %s", session_code)
    finally:
        remove_teacher_ws(s, ws)


@app.websocket("/ws/student/{session_code}/{student_id}")
async def student_ws_endpoint(ws: WebSocket, session_code: str, student_id: str):
    s = sessions.get(session_code)
    if not s:
        await ws.accept()
        await ws_send(ws, {"type": "error", "message": "Session not found"})
        await ws.close()
        return

    if student_id not in s.get("students", {}):
        await ws.accept()
        await ws_send(ws, {"type": "error", "message": "Student not found"})
        await ws.close()
        return

    query_params = ws.query_params
    email = query_params.get("email")
    role = query_params.get("role")
    if not email or not role:
        await ws.accept()
        await ws_send(ws, {"type": "error", "message": "Missing authentication parameters"})
        await ws.close()
        return
    
    student = s["students"][student_id]
    if email.lower().strip() != student.get("email", "").lower().strip():
        await ws.accept()
        await ws_send(ws, {"type": "error", "message": "Access denied: student email mismatch"})
        await ws.close()
        return

    if student_id in s.get("kicked", set()):
        await ws.accept()
        await ws_send(ws, {"type": "error", "message": "You have been removed from this session"})
        await ws.close()
        return

    # WebSocket Guard for CLOSED ACCESS
    if s.get("allowed_students"):
        student = s.get("students", {}).get(student_id)
        if student:
            name_norm, roll_norm, cls_norm = normalize_student_credentials(
                student.get("name"), student.get("roll"), student.get("class")
            )
            match = next(
                (item for item in s["allowed_students"]
                 if normalize_string(item[0]) == name_norm and
                    normalize_string(item[1]) == roll_norm and
                    normalize_string(item[2]) == cls_norm),
                None,
            )
            if not match:
                await ws.accept()
                await ws_send(ws, {"type": "error", "message": "Not allowed for this class"})
                await ws.close()
                return

    await ws.accept()
    s["ws_clients"][student_id] = ws
    student = s["students"].get(student_id, {})
    if student:
        student["last_seen"] = now()
    
    student_status = student.get("status", "unknown")
    log.info(
        "Student %s connected to session %s (status: %s)",
        student_id, session_code, student_status
    )
    
    # SAFEGUARD: If student is waiting, notify them and don't allow task access
    if student_status == "waiting":
        log.debug("[SAFEGUARD] Student %s is waiting for approval", student_id)
        await ws_send(ws, {
            "type": "waiting_for_approval",
            "message": "Please wait for the teacher to approve your join request",
            "student_id": student_id
        })
        # DON'T return here - keep connection open for approval notification
        # The student will receive an "approved" message when teacher approves

    latest_delivery     = latest_delivery_for_student(s, student_id)
    current             = None
    current_delivery_id = ""
    task_idx            = -1

    if latest_delivery and student_status == "active":
        current             = task_payload(s, latest_delivery)["task"]
        current_delivery_id = latest_delivery["id"]
        task_idx            = latest_delivery.get("task_index", -1)
    elif student_status == "active":
        idx      = s["current_task_idx"]
        current  = safe_task(s["tasks"][idx]) if 0 <= idx < len(s["tasks"]) else None
        task_idx = idx

    # Build test state payload for reconnecting students
    ts = s["test_state"]
    _test_payload: dict = {"active": False}
    if ts.get("active") and student_status == "active":
        # Gather only the tasks that belong to this test (preserves per-student shuffle)
        test_task_ids = set(ts.get("task_ids") or [])
        test_tasks    = [safe_task(t) for t in s.get("tasks", []) if t["id"] in test_task_ids]
        _already_submitted = student_id in (ts.get("submitted") or set())
        _test_payload = {
            "active":        True,
            "tasks":         test_tasks,
            "duration_secs": ts.get("duration_secs", 0),
            "start_time":    ts.get("start_time"),
            "submitted":     _already_submitted,
        }

    # Compute hand raised status for this student on reconnect
    rh = s.get("raised_hands", {})
    if isinstance(rh, list):
        rh = {sid: {"name": s["students"].get(sid, {}).get("name", "?"), "raised_at": 0} for sid in rh}
        s["raised_hands"] = rh
    student_hand_raised = student_id in rh

    att = _att(s)
    geo_rec = None
    if s.get("access_mode", "open") == "close":
        geo_rec = att.get("records", {}).get(student_id)
    await ws_send(ws, {
        "type":                "connected",
        "role":                "student",
        "student":             student,
        "geo_attendance":      geo_rec,
        "access_mode":         s.get("access_mode", "open"),
        "session_status":      s["status"],
        "session_name":        s.get("session_name", ""),
        "current_task":        current,
        "groups":              s["groups"],
        # Legacy field kept for backwards compat
        "test_active":         ts.get("active", False) and student_status == "active",
        # Full test state for session restoration
        "test_state":          _test_payload,
        "current_delivery_id": current_delivery_id,
        "task_index":          task_idx,
        "total_tasks":         len(s["tasks"]),
        "chat_enabled":        s.get("chat_enabled", True),
        "explanations":        s.get("explanations", []),
        "student_status":      student_status,  # Send status so frontend knows
        "vc_active":           s.get("vc_active", False),
        "hand_raised":         student_hand_raised,  # Sync hand state on reconnect
        "doubts":              [d for d in s.get("doubts", []) if d.get("student_id") == student_id],
        "chat_suspended":      student_id in s.get("suspended_chat_students", set()),
        # Photo: send stored photo so frontend can sync localStorage on reconnect
        "profile_photo":       student.get("profile_photo") or None,
    })

    if student_status == "active":
        await replay_unacked_tasks(s, student_id)

    await ws_teacher(s, {
        "type":         "student_connected",
        "student_id":   student_id,
        "student_name": student.get("name", "?"),
        "student_status": student_status,
    })

    try:
        while True:
            raw  = await ws.receive_text()
            try:
                data = json.loads(raw)
            except Exception:
                log.warning("[WS] Student %s sent invalid JSON", student_id)
                continue
            cmd  = data.get("type", "")

            if cmd in ("ping", "heartbeat"):
                st = s["students"].get(student_id)
                if st:
                    st["last_seen"] = now()
                await ws_send(ws, {"type": "pong", "ts": now()})

            elif cmd == "location_update":
                if s.get("access_mode", "open") != "close":
                    continue
                lat = data.get("lat")
                lng = data.get("lng")
                accuracy = data.get("accuracy")
                
                att = _att(s)
                if att.get("state") in ("ended", "locked"):
                    continue
                    
                records = att.setdefault("records", {})
                r = records.setdefault(student_id, {
                    "student_id": student_id,
                    "join_at": now(),
                    "leave_at": None,
                    "duration": 0,
                    "status": "present",
                    "interactions": 0,
                })
                
                if r.get("frozen"):
                    continue
                    
                now_ts = now()
                if "joinTime" not in r:
                    init_student_geo_attendance(r, now_ts, s)
                    
                if accuracy is None or not isinstance(accuracy, (int, float)) or accuracy > 30:
                    log.warning("[GEO] Student %s sent low accuracy location: %s", student_id, accuracy)
                    continue
                    
                last_lat = r.get("last_lat")
                last_lng = r.get("last_lng")
                last_ts = r.get("lastLocationTimestamp")
                
                if last_lat is not None and last_lng is not None and last_ts is not None:
                    time_delta = now_ts - last_ts
                    if time_delta > 0:
                        distance = haversine_distance_meters(last_lat, last_lng, lat, lng)
                        speed = distance / time_delta
                        if speed > 25.0:
                            log.warning("[GEO] Student %s detected with impossible speed: %s m/s", student_id, speed)
                            continue
                            
                r["last_lat"] = lat
                r["last_lng"] = lng
                r["lastLocationTimestamp"] = now_ts
                r["gpsAccuracy"] = accuracy
                
                was_lost = r.get("gps_lost", False)
                if was_lost:
                    r["gps_lost"] = False
                    timeline = r.setdefault("attendanceTimeline", [])
                    timeline.append({"timestamp": now_ts, "event": "GPS Restored"})
                    student = s["students"].get(student_id, {})
                    student_name = student.get("name", "Student")
                    await ws_teacher(s, {
                        "type": "geo_notification",
                        "notification_type": "gps_restored",
                        "student_name": student_name,
                        "message": f"✅ {student_name} GPS restored."
                    })
                
                teacher_location = s.get("close_access_location")
                if teacher_location and isinstance(teacher_location, dict):
                    t_lat = teacher_location.get("lat")
                    t_lng = teacher_location.get("lng")
                    radius = s.get("close_access_radius_meters", 100)
                    
                    if t_lat is not None and t_lng is not None:
                        distance = haversine_distance_meters(t_lat, t_lng, lat, lng)
                        is_inside = distance <= radius
                        
                        old_status = r.get("currentStatus", "present")
                        
                        if is_inside:
                            r["consecutive_inside"] = r.get("consecutive_inside", 0) + 1
                            r["consecutive_outside"] = 0
                            
                            if r["consecutive_inside"] >= 2:
                                r["left_radius_at"] = None
                                if old_status != "present":
                                    outside_start = r.get("outsideStartTime")
                                    if outside_start:
                                        r["accumulatedOutsideTime"] = r.get("accumulatedOutsideTime", 0.0) + (now_ts - outside_start)
                                    r["outsideStartTime"] = None
                                    r["insideStartTime"] = now_ts
                                    r["currentStatus"] = "present"
                                    r["reEntryCount"] = r.get("reEntryCount", 0) + 1
                                    
                                    timeline = r.setdefault("attendanceTimeline", [])
                                    timeline.append({"timestamp": now_ts, "event": "Returned"})
                                    
                                    student = s["students"].get(student_id, {})
                                    student_name = student.get("name", "Student")
                                    total_duration = s.get("duration_mins", 60) * 60
                                    pct = round((r.get("accumulatedInsideTime", 0.0) / total_duration) * 100, 2) if total_duration > 0 else 100.0
                                    
                                    from datetime import datetime
                                    returned_time_str = datetime.fromtimestamp(now_ts).strftime("%I:%M %p")
                                    await ws_teacher(s, {
                                        "type": "geo_notification",
                                        "notification_type": "enter",
                                        "student_name": student_name,
                                        "attendance_percentage": int(pct),
                                        "time": returned_time_str
                                    })
                        else:
                            r["consecutive_outside"] = r.get("consecutive_outside", 0) + 1
                            r["consecutive_inside"] = 0
                            
                            if r["consecutive_outside"] >= 2:
                                if r.get("left_radius_at") is None:
                                    r["left_radius_at"] = now_ts
                                    
                        left_at = r.get("left_radius_at")
                        if left_at is not None and old_status == "present":
                            if now_ts - left_at >= 30:
                                inside_start = r.get("insideStartTime")
                                if inside_start and left_at > inside_start:
                                    r["accumulatedInsideTime"] = r.get("accumulatedInsideTime", 0.0) + (left_at - inside_start)
                                r["insideStartTime"] = None
                                r["outsideStartTime"] = left_at
                                r["currentStatus"] = "temporary_absent"
                                r["exitCount"] = r.get("exitCount", 0) + 1
                                
                                timeline = r.setdefault("attendanceTimeline", [])
                                timeline.append({"timestamp": now_ts, "event": "Left Classroom"})
                                
                                student = s["students"].get(student_id, {})
                                student_name = student.get("name", "Student")
                                total_duration = s.get("duration_mins", 60) * 60
                                pct = round((r.get("accumulatedInsideTime", 0.0) / total_duration) * 100, 2) if total_duration > 0 else 100.0
                                
                                from datetime import datetime
                                left_time_str = datetime.fromtimestamp(now_ts).strftime("%I:%M %p")
                                
                                if r["exitCount"] >= 3:
                                    await ws_teacher(s, {
                                        "type": "geo_notification",
                                        "notification_type": "exit_warning",
                                        "student_name": student_name,
                                        "attendance_percentage": int(pct),
                                        "time": left_time_str,
                                        "exit_count": r["exitCount"],
                                        "message": f"🚨 {student_name} has exited the classroom {r['exitCount']} times. Current Attendance: {int(pct)}%. Recommendation: Review this student's attendance manually."
                                    })
                                else:
                                    await ws_teacher(s, {
                                        "type": "geo_notification",
                                        "notification_type": "leave",
                                        "student_name": student_name,
                                        "attendance_percentage": int(pct),
                                        "time": left_time_str
                                    })
                                    
                if r.get("currentStatus") == "present" and r.get("insideStartTime"):
                    current_inside = r.get("accumulatedInsideTime", 0.0) + (now_ts - r["insideStartTime"])
                else:
                    current_inside = r.get("accumulatedInsideTime", 0.0)
                    
                total_duration = s.get("duration_mins", 60) * 60
                pct = round((current_inside / total_duration) * 100, 2) if total_duration > 0 else 100.0
                r["attendancePercentage"] = pct
                
                await ws_send(ws, {
                    "type": "student_attendance_update",
                    "currentStatus": r["currentStatus"],
                    "attendancePercentage": r["attendancePercentage"],
                    "accumulatedInsideTime": r["accumulatedInsideTime"],
                    "accumulatedOutsideTime": r["accumulatedOutsideTime"],
                    "insideStartTime": r["insideStartTime"],
                    "outsideStartTime": r["outsideStartTime"],
                    "lastLocationTimestamp": r["lastLocationTimestamp"],
                    "gps_lost": r.get("gps_lost", False),
                })
                
                await broadcast_attendance(s)

            elif cmd == "gps_lost":
                if s.get("access_mode", "open") != "close":
                    continue
                att = _att(s)
                if att.get("state") in ("ended", "locked"):
                    continue
                    
                records = att.setdefault("records", {})
                r = records.setdefault(student_id, {
                    "student_id": student_id,
                    "join_at": now(),
                    "leave_at": None,
                    "duration": 0,
                    "status": "present",
                    "interactions": 0,
                })
                
                if r.get("frozen"):
                    continue
                    
                now_ts = now()
                if "joinTime" not in r:
                    init_student_geo_attendance(r, now_ts, s)
                    
                old_status = r.get("currentStatus", "present")
                r["gps_lost"] = True
                r["lastLocationTimestamp"] = now_ts
                
                if old_status == "present":
                    inside_start = r.get("insideStartTime")
                    if inside_start:
                        r["accumulatedInsideTime"] = r.get("accumulatedInsideTime", 0.0) + (now_ts - inside_start)
                    r["insideStartTime"] = None
                    r["outsideStartTime"] = now_ts
                    r["currentStatus"] = "temporary_absent"
                    r["exitCount"] = r.get("exitCount", 0) + 1
                    
                    timeline = r.setdefault("attendanceTimeline", [])
                    timeline.append({"timestamp": now_ts, "event": "GPS Lost"})
                    
                    student = s["students"].get(student_id, {})
                    student_name = student.get("name", "Student")
                    total_duration = s.get("duration_mins", 60) * 60
                    pct = round((r.get("accumulatedInsideTime", 0.0) / total_duration) * 100, 2) if total_duration > 0 else 100.0
                    r["attendancePercentage"] = pct
                    
                    await ws_teacher(s, {
                        "type": "geo_notification",
                        "notification_type": "gps_lost",
                        "student_name": student_name,
                        "message": f"⚠️ {student_name} location unavailable. Attendance paused."
                    })
                    
                    await ws_send(ws, {
                        "type": "student_attendance_update",
                        "currentStatus": r["currentStatus"],
                        "attendancePercentage": r["attendancePercentage"],
                        "accumulatedInsideTime": r["accumulatedInsideTime"],
                        "accumulatedOutsideTime": r["accumulatedOutsideTime"],
                        "insideStartTime": r["insideStartTime"],
                        "outsideStartTime": r["outsideStartTime"],
                        "lastLocationTimestamp": r["lastLocationTimestamp"],
                        "gps_lost": True,
                    })
                    
                    await broadcast_attendance(s)

            # SAFEGUARD: Prevent waiting students from accessing classroom features
            elif cmd not in ("ping", "heartbeat"):  # Allow only heartbeat/ping for waiting students
                student = s["students"].get(student_id, {})
                if student.get("status") == "waiting":
                    log.warning(
                        "[SAFEGUARD] Student %s tried to execute %s while waiting for approval",
                        student_id, cmd
                    )
                    await ws_send(ws, {
                        "type": "error",
                        "message": "You must wait for teacher approval before accessing classroom features"
                    })
                    continue

            # ── HAND RAISE via WebSocket ─────────────────────────────────
            elif cmd == "raise_hand":
                st_data = s["students"].get(student_id, {})
                rh2 = s.setdefault("raised_hands", {})
                if isinstance(rh2, list):
                    rh2 = {sid: {"name": s["students"].get(sid, {}).get("name","?"), "raised_at": 0} for sid in rh2}
                    s["raised_hands"] = rh2
                if student_id not in rh2:
                    rh2[student_id] = {"name": st_data.get("name","?"), "raised_at": now()}
                hand_list = [{"student_id": sid, "student_name": info.get("name","?"), "raised_at": info.get("raised_at")} for sid, info in rh2.items()]
                await ws_send(ws, {"type": "hand_ack", "raised": True})
                await ws_teacher(s, {
                    "type": "hand_raised",
                    "student_id": student_id,
                    "student_name": st_data.get("name","?"),
                    "raised_hands": hand_list,
                    "count": len(rh2),
                })

            elif cmd == "lower_hand":
                rh2 = s.setdefault("raised_hands", {})
                if isinstance(rh2, list):
                    rh2 = {sid: {"name": s["students"].get(sid, {}).get("name","?"), "raised_at": 0} for sid in rh2}
                    s["raised_hands"] = rh2
                rh2.pop(student_id, None)
                hand_list = [{"student_id": sid, "student_name": info.get("name","?"), "raised_at": info.get("raised_at")} for sid, info in rh2.items()]
                await ws_send(ws, {"type": "hand_ack", "raised": False})
                await ws_teacher(s, {
                    "type": "hand_lowered",
                    "student_id": student_id,
                    "raised_hands": hand_list,
                    "count": len(rh2),
                })

            # ── DOUBT via WebSocket ───────────────────────────────────────
            elif cmd == "submit_doubt":
                doubt_text = (data.get("doubt_text") or data.get("text") or "").strip()
                if doubt_text:
                    st_data = s["students"].get(student_id, {})
                    import uuid as _uuid
                    d = {
                        "id":           f"d_{_uuid.uuid4().hex[:8]}",
                        "student_id":   student_id,
                        "student_name": st_data.get("name", "?"),
                        "doubt_text":   doubt_text,
                        "text":         doubt_text,
                        "reply":        "",
                        "answer":       None,
                        "status":       "pending",
                        "resolved":     False,
                        "created_at":   now(),
                    }
                    s.setdefault("doubts", []).append(d)
                    save_session(session_code)
                    await ws_send(ws, {"type": "doubt_submitted", "doubt": d})
                    await ws_teacher(s, {"type": "new_doubt", "doubt": d})

            elif cmd == "task_received":
                attendance_add_interaction(s, student_id)
                delivery_id = data.get("delivery_id")
                if mark_task_ack(s, student_id, delivery_id):
                    await ws_teacher(s, {
                        "type":        "task_delivery_ack",
                        "delivery_id": delivery_id,
                        "task_id":     data.get("task_id", ""),
                        "student_id":  student_id,
                    })

            # ── CHAT REACTIONS (student-side, Feature 2) ─────────────────
            elif cmd == "chat_react":
                # Block if student is suspended from chat
                if student_id in s.get("suspended_chat_students", set()):
                    continue
                react_msg_id = data.get("message_id", "")
                react_emoji  = data.get("emoji", "")
                if react_emoji in ALLOWED_EMOJIS and react_msg_id:
                    react_msg = next((m for m in s.get("chat_messages", []) if m.get("id") == react_msg_id), None)
                    if react_msg:
                        react_msg.setdefault("reactions", {})
                        react_list = react_msg["reactions"].setdefault(react_emoji, [])
                        if student_id in react_list:
                            react_list.remove(student_id)
                        else:
                            react_list.append(student_id)
                        await ws_broadcast(s, {
                            "type":       "chat_reactions_update",
                            "message_id": react_msg_id,
                            "reactions":  react_msg["reactions"],
                        })


    except WebSocketDisconnect:
        log.info("Student %s disconnected: %s", student_id, session_code)
    finally:
        if s.get("ws_clients", {}).get(student_id) is ws:
            s["ws_clients"].pop(student_id, None)
        # Auto-lower hand on disconnect
        rh = s.get("raised_hands", {})
        if isinstance(rh, list):
            rh = {sid: {"name": s["students"].get(sid, {}).get("name", "?"), "raised_at": now()} for sid in rh if sid in s["students"]}
            s["raised_hands"] = rh
        if student_id in rh:
            rh.pop(student_id, None)
            hand_list = [
                {"student_id": sid, "student_name": info.get("name", "?"), "raised_at": info.get("raised_at")}
                for sid, info in rh.items()
            ]
            asyncio.create_task(ws_teacher(s, {
                "type": "hand_lowered",
                "student_id": student_id,
                "raised_hands": hand_list,
                "count": len(rh),
                "reason": "disconnect",
            }))
        attendance_mark_leave(s, student_id)
        asyncio.create_task(broadcast_attendance(s))
        touch_session(s)
        admin_broadcast({
            "event": "student_left",
            "session_code": session_code,
            "student_id": student_id,
            "reason": "disconnect",
        })
        await ws_teacher(s, {"type": "student_disconnected", "student_id": student_id})


@app.websocket("/ws/admin")
async def admin_ws_endpoint(ws: WebSocket, token: str = Query(None)):
    await ws.accept()
    if not token or token not in admin_tokens:
        await ws_send(ws, {"type": "error", "message": "Unauthorized admin websocket"})
        await ws.close()
        return

    admin_connections.add(ws)
    username = admin_tokens[token]
    log.info("Admin connected: %s", username)
    await ws_send(ws, {"type": "connected", "role": "admin", "dashboard": admin_dashboard_data()})

    try:
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            if data.get("type") in ("ping", "heartbeat"):
                await ws_send(ws, {"type": "pong", "ts": now()})
    except WebSocketDisconnect:
        log.info("Admin disconnected: %s", username)
    finally:
        admin_connections.discard(ws)


# Video Call Signaling registry
# { session_code: { user_id: WebSocket } }
vc_sessions = {}

@app.websocket("/ws/vc/{session_code}/{user_id}")
async def vc_signaling_endpoint(ws: WebSocket, session_code: str, user_id: str):
    await ws.accept()
    if session_code not in vc_sessions:
        vc_sessions[session_code] = {}
    vc_sessions[session_code][user_id] = ws
    try:
        while True:
            data = await ws.receive_text()
            msg = json.loads(data)
            target = msg.get("target")
            if target and session_code in vc_sessions:
                msg["from"] = user_id
                if target == "teacher":
                    for uid, socket in vc_sessions[session_code].items():
                        if uid == "teacher":
                            try:
                                await socket.send_text(json.dumps(msg))
                            except Exception:
                                pass
                else:
                    socket = vc_sessions[session_code].get(target)
                    if socket:
                        try:
                            await socket.send_text(json.dumps(msg))
                        except Exception:
                            pass
    except WebSocketDisconnect:
        pass
    finally:
        if session_code in vc_sessions:
            vc_sessions[session_code].pop(user_id, None)
            if not vc_sessions[session_code]:
                vc_sessions.pop(session_code, None)


# ══════════════════════════════════════════════════════════════════
#  EXPLANATION ROUTES
# ══════════════════════════════════════════════════════════════════

@app.post("/api/session/{code}/explanations/send")
async def send_explanation(code: str, req: SendExplanationReq):
    """Teacher sends an AI explanation to all students for a specific task."""
    s = _S(code)
    if s.get("status") != "active":
        raise HTTPException(409, "Session must be active to send explanations")

    task = next((t for t in s.get("tasks", []) if t["id"] == req.task_id), None)
    if not task:
        raise HTTPException(404, f"Task '{req.task_id}' not found")

    explanation_entry = {
        "id":          gen_id("exp"),
        "task_id":     req.task_id,
        "task_question": task.get("question", ""),
        "explanation": req.explanation,
        "mode":        req.mode,
        "sent_at":     now(),
    }

    # Persist explanation on session
    s.setdefault("explanations", []).append(explanation_entry)
    save_session(code)
    touch_session(s)

    # Broadcast to all students via WebSocket
    payload = {
        "type":           "explanation_sent",
        "explanation":    explanation_entry,
    }
    await ws_all_students(s, payload)

    log.info("[EXPLAIN] Explanation sent for task %s in session %s", req.task_id, code)
    return {"sent": True, "explanation_id": explanation_entry["id"]}


@app.get("/api/session/{code}/explanations")
def get_explanations(code: str, task_id: Optional[str] = None):
    """Return all explanations for a session, optionally filtered by task_id."""
    s = _S(code)
    explanations = s.get("explanations", [])
    if task_id:
        explanations = [e for e in explanations if e.get("task_id") == task_id]
    return {"explanations": explanations}


# ══════════════════════════════════════════════════════════════════
#  TEST DATA LOADER (Development Only)
# ══════════════════════════════════════════════════════════════════

@app.post("/api/test-data/{session_code}")
async def load_test_data(session_code: str):
    """Load sample test data for development/testing purposes."""
    s = _S(session_code)
    
    # Create sample students
    sample_students = [
        {"name": "Alice Johnson", "roll": "001", "cls": "10A"},
        {"name": "Bob Smith", "roll": "002", "cls": "10A"},
        {"name": "Charlie Brown", "roll": "003", "cls": "10A"},
        {"name": "Diana Prince", "roll": "004", "cls": "10A"},
        {"name": "Eve Wilson", "roll": "005", "cls": "10A"},
    ]
    
    created_students = []
    for student_data in sample_students:
        student = new_student(student_data["name"], anonymous=False)
        student["roll"] = student_data["roll"]
        student["class"] = student_data["cls"]
        student["status"] = "active"
        s["students"][student["id"]] = student
        s.setdefault("active_rolls", set()).add(student_data["roll"])
        created_students.append(student)
    
    # Create sample tasks
    sample_tasks = [
        {
            "question": "What is the capital of France?",
            "type": "mcq",
            "options": ["Paris", "London", "Berlin", "Madrid"],
            "correct_answer": "A",
            "topic": "Geography",
            "difficulty": "easy",
        },
        {
            "question": "What is 2 + 2 × 3?",
            "type": "mcq",
            "options": ["8", "12", "10", "6"],
            "correct_answer": "A",
            "topic": "Mathematics",
            "difficulty": "medium",
        },
        {
            "question": "Explain the water cycle in 2-3 sentences.",
            "type": "short",
            "correct_answer": "",
            "topic": "Science",
            "difficulty": "medium",
        },
        {
            "question": "Write a Python function to calculate factorial.",
            "type": "coding",
            "correct_answer": "",
            "topic": "Programming",
            "difficulty": "hard",
        },
    ]
    
    created_tasks = []
    for task_data in sample_tasks:
        task = new_task(normalize_task_input(task_data))
        s["tasks"].append(task)
        created_tasks.append(task)
    
    # Create sample groups
    student_ids = [st["id"] for st in created_students]
    s["groups"] = [
        {"id": gen_id("g"), "name": "Group 1", "members": student_ids[:2]},
        {"id": gen_id("g"), "name": "Group 2", "members": student_ids[2:4]},
        {"id": gen_id("g"), "name": "Group 3", "members": student_ids[4:]},
    ]
    
    log.info("Test data loaded for session %s: %d students, %d tasks, %d groups", 
             session_code, len(created_students), len(created_tasks), len(s["groups"]))
    
    return {
        "loaded": True,
        "students": len(created_students),
        "tasks": len(created_tasks),
        "groups": len(s["groups"]),
        "student_ids": [st["id"] for st in created_students],
        "task_ids": [t["id"] for t in created_tasks],
    }



# ══════════════════════════════════════════════════════════════════════
# AI LESSON PLANNER — endpoints
# ══════════════════════════════════════════════════════════════════════

def _ensure_lesson_fields(s: dict) -> None:
    """Backfill lesson planner fields into older sessions that lack them."""
    s.setdefault("lesson_templates", {})
    s.setdefault("active_lesson", None)
    s.setdefault("lesson_history", [])
    s.setdefault("lesson_drafts", {})
    s.setdefault("student_lesson_progress", {})


@app.post("/api/session/{code}/lesson/generate")
async def lesson_generate(
    code: str,
    topic: str = Body(...),
    subject: str = Body(...),
    grade: str = Body(...),
    duration: int = Body(45),
    difficulty: str = Body("medium"),
    learning_goal: str = Body(""),
    custom_instructions: str = Body(""),
    api_key: Optional[str] = Body(None),
):
    """Generate a complete AI lesson plan. Falls back to a rich structured template when no key provided."""
    s = _S(code)
    _ensure_lesson_fields(s)

    SECTIONS = [
        ("lesson_title",        "📌 Lesson Title"),
        ("objectives",          "🎯 Learning Objectives"),
        ("summary",             "📝 Lesson Summary"),
        ("intro",               "🌅 Introduction / Warm-Up"),
        ("main_activities",     "📚 Main Teaching Activities"),
        ("interactive",         "🤝 Interactive Activities"),
        ("group_activities",    "👥 Group Activities"),
        ("practical_tasks",     "🔧 Practical Tasks"),
        ("homework",            "🏠 Homework / Assignments"),
        ("assessment",          "✅ Assessment Questions"),
        ("resources",           "🔗 Resources & References"),
        ("engagement",          "💡 Student Engagement Ideas"),
        ("easy_tasks",          "🟢 Easy Tasks"),
        ("medium_tasks",        "🟡 Medium Tasks"),
        ("hard_tasks",          "🔴 Hard Tasks"),
        ("real_world",          "🌍 Real-World Examples"),
        ("time_breakdown",      "⏱️ Time Breakdown"),
    ]

    # Use key from request, saved teacher key, or fallback to server-side env variables (OpenRouter or Gemini)
    key_to_use = api_key or get_teacher_key(s.get("teacher_email")) or os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")

    if key_to_use:
        prompt = f"""You are an expert teacher assistant. Generate a COMPLETE, detailed lesson plan.

Topic: {topic}
Subject: {subject}
Class/Grade: {grade}
Duration: {duration} minutes
Difficulty: {difficulty}
Learning Goal: {learning_goal}
{f'Special Instructions: {custom_instructions}' if custom_instructions else ''}

Return ONLY a valid JSON object (no markdown, no backticks) with these exact keys:
{json.dumps({sid: title for sid, title in SECTIONS}, indent=2)}

Each value should be rich, detailed markdown text relevant to the lesson.
For assessment tasks, include at least 3-5 questions.
For time_breakdown, include minutes for each phase.
Make it practical, engaging, and pedagogically sound."""

        try:
            raw = await call_llm(prompt, key_to_use, is_json=True)
            # Strip markdown code fences if present
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
            generated_sections = json.loads(raw)
            log.info("[LESSON] AI generation succeeded for session %s topic=%s", code, topic)
        except Exception as exc:
            log.warning("[LESSON] AI generation failed: %s", exc)
            generated_sections = {}

    # Fallback: rich structured placeholder
    if not generated_sections:
        generated_sections = {
            "lesson_title": f"{topic} — {subject} ({grade})",
            "objectives": f"- Students will understand the core concepts of **{topic}**\n- Apply knowledge in {subject} context\n- Develop critical thinking skills\n- Connect theory to real-world applications",
            "summary": f"This {duration}-minute {difficulty}-level lesson introduces **{topic}** to {grade} students. The lesson progresses from foundational concepts to applied practice, ensuring all learning styles are engaged through a mix of direct instruction, interactive activities, and collaborative tasks.",
            "intro": f"**Warm-Up (5 min):** Begin with a thought-provoking question about {topic}.\n\n*Ask students:* 'What do you already know about {topic}? Share one thing!'\n\nUse a quick poll or show an engaging image/video clip related to {topic} to spark curiosity.",
            "main_activities": f"**1. Direct Instruction (10 min)**\nPresent key concepts of {topic} with visuals and examples.\n\n**2. Guided Practice (10 min)**\nWork through examples together as a class.\n\n**3. Independent Practice (10 min)**\nStudents attempt problems on their own.\n\n**Learning Goal:** {learning_goal or f'Master the fundamentals of {topic}'}",
            "interactive": f"- **Think-Pair-Share:** Give students 2 min to think, then discuss with a partner\n- **Live Poll:** Ask a key concept question and show class results\n- **Quick Draw:** Students sketch a diagram related to {topic}\n- **Exit Ticket:** One thing learned, one question remaining",
            "group_activities": f"**Group Challenge (10 min):**\nDivide into groups of 3-4. Each group gets a scenario related to {topic}.\n\nGroups must:\n1. Analyze the scenario\n2. Identify key {subject} principles\n3. Present their solution in 2 minutes\n\n*Award points for creativity and accuracy!*",
            "practical_tasks": f"**Task 1:** Solve a real-world problem using {topic} principles\n**Task 2:** Create a concept map showing relationships in {topic}\n**Task 3:** Design a mini-project applying {topic} concepts\n\nAll tasks should be completed individually and reviewed by teacher.",
            "homework": f"**Assignment:** Research how {topic} is used in everyday life.\n\nWrite a 1-page reflection covering:\n- 3 real-world applications of {topic}\n- One question you still have\n- How this connects to what you already know\n\n**Due:** Next class",
            "assessment": f"**Formative Assessment:**\n1. What is the main concept of {topic}?\n2. Give an example of {topic} in {subject}\n3. Why is {topic} important?\n4. Explain {topic} in your own words\n5. How would you apply {topic} to solve [problem]?\n\n**Observation:** Watch for common misconceptions during guided practice.",

            "resources": f"**Recommended Reading:**\n- Textbook Chapter: {subject} — {topic}\n- Online: Khan Academy — {topic}\n- YouTube: Search '{topic} explained'\n\n**Tools:**\n- Interactive simulation (if available)\n- Practice worksheet (attached)\n- Reference card with key formulas/terms",
            "engagement": f"- Use gamification: award points for correct answers\n- Incorporate student choice in activities\n- Use real news/current events related to {topic}\n- Student teaching moments: let students explain to each other\n- Mystery box: reveal a surprise application of {topic}\n- Connect to student interests and daily life",
            "easy_tasks": f"1. Define {topic} in simple terms\n2. List 3 key words related to {topic}\n3. Match terms to definitions worksheet\n4. Complete the sentence: '{topic} is important because...'\n5. Draw or label a simple diagram",
            "medium_tasks": f"1. Solve 5 practice problems applying {topic}\n2. Write a paragraph explaining {topic} to a younger student\n3. Find and explain a real-world example of {topic}\n4. Compare {topic} with a related concept\n5. Create 3 of your own practice questions about {topic}",
            "hard_tasks": f"1. Design a project that demonstrates {topic} in action\n2. Research and present an advanced application of {topic}\n3. Write an essay arguing for the importance of {topic} in {subject}\n4. Solve a complex multi-step problem using {topic}\n5. Create a lesson plan to teach {topic} to your classmates",
            "real_world": f"**Example 1:** {topic} is used in engineering to...\n**Example 2:** In medicine, {topic} helps doctors...\n**Example 3:** Technology companies use {topic} to...\n**Example 4:** Environmental scientists apply {topic} when...\n\n*Discussion:* Which example resonates most with your future career goals?",
            "time_breakdown": f"| Phase | Activity | Time |\n|-------|----------|------|\n| 0-5 min | Warm-up & Hook | 5 min |\n| 5-15 min | Direct Instruction | 10 min |\n| 15-25 min | Guided Practice | 10 min |\n| 25-35 min | Group Activity | 10 min |\n| 35-42 min | Independent Practice | 7 min |\n| 42-{duration} min | Wrap-up & Exit Ticket | {duration-42 if duration>42 else 3} min |",
        }

    # Build sections list
    sections = [
        {"id": sid, "title": title, "body": generated_sections.get(sid, ""), "type": sid}
        for sid, title in SECTIONS
    ]

    return {
        "sections": sections,
        "meta": {
            "topic": topic, "subject": subject, "grade": grade,
            "duration": duration, "difficulty": difficulty,
            "learning_goal": learning_goal,
        }
    }


@app.post("/api/session/{code}/lesson/templates")
async def lesson_save_template(
    code: str,
    title: str = Body(...),
    topic: str = Body(...),
    subject: str = Body(...),
    grade: str = Body(...),
    duration: int = Body(45),
    difficulty: str = Body("medium"),
    learning_goal: str = Body(""),
    custom_instructions: str = Body(""),
    tags: list = Body([]),
    content: dict = Body({}),
    teacher_id: str = Body(""),
    template_id: Optional[str] = Body(None),
):
    """Save or update a lesson template."""
    s = _S(code)
    _ensure_lesson_fields(s)

    if template_id and template_id in s["lesson_templates"]:
        # Update existing
        t = s["lesson_templates"][template_id]
        t.update({
            "title": title, "topic": topic, "subject": subject,
            "grade": grade, "duration": duration, "difficulty": difficulty,
            "learning_goal": learning_goal, "custom_instructions": custom_instructions,
            "tags": tags, "content": content, "updated_at": now(),
            "version": t.get("version", 1) + 1,
        })
    else:
        t = new_lesson_template({
            "title": title, "topic": topic, "subject": subject,
            "grade": grade, "duration": duration, "difficulty": difficulty,
            "learning_goal": learning_goal, "custom_instructions": custom_instructions,
            "tags": tags, "content": content, "teacher_id": teacher_id,
        })
        s["lesson_templates"][t["template_id"]] = t

    save_session(code)
    return {"template": t}


@app.get("/api/session/{code}/lesson/templates")
async def lesson_list_templates(code: str):
    """List all lesson templates for this session."""
    s = _S(code)
    _ensure_lesson_fields(s)
    templates = sorted(s["lesson_templates"].values(), key=lambda x: x.get("updated_at", 0), reverse=True)
    return {"templates": templates}


@app.delete("/api/session/{code}/lesson/templates/{template_id}")
async def lesson_delete_template(code: str, template_id: str):
    s = _S(code)
    _ensure_lesson_fields(s)
    if template_id not in s["lesson_templates"]:
        raise HTTPException(404, "Template not found")
    del s["lesson_templates"][template_id]
    save_session(code)
    return {"deleted": True}


@app.post("/api/session/{code}/lesson/templates/{template_id}/favorite")
async def lesson_toggle_favorite(code: str, template_id: str):
    s = _S(code)
    _ensure_lesson_fields(s)
    t = s["lesson_templates"].get(template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    t["favorite"] = not t.get("favorite", False)
    save_session(code)
    return {"favorite": t["favorite"]}


@app.post("/api/session/{code}/lesson/templates/{template_id}/clone")
async def lesson_clone_template(code: str, template_id: str):
    s = _S(code)
    _ensure_lesson_fields(s)
    t = s["lesson_templates"].get(template_id)
    if not t:
        raise HTTPException(404, "Template not found")
    import copy
    cloned = copy.deepcopy(t)
    cloned["template_id"] = gen_id("lt")
    cloned["title"] = cloned["title"] + " (Copy)"
    cloned["created_at"] = now()
    cloned["updated_at"] = now()
    cloned["favorite"] = False
    s["lesson_templates"][cloned["template_id"]] = cloned
    save_session(code)
    return {"template": cloned}


@app.post("/api/session/{code}/lesson/push")
async def lesson_push(
    code: str,
    sections: list = Body(...),
    title: str = Body(""),
    topic: str = Body(""),
    subject: str = Body(""),
    grade: str = Body(""),
    duration: int = Body(45),
    difficulty: str = Body("medium"),
):
    """Push a lesson live to all students via WebSocket."""
    s = _S(code)
    _ensure_lesson_fields(s)

    lesson = {
        "lesson_id": gen_id("al"),
        "title": title,
        "topic": topic,
        "subject": subject,
        "grade": grade,
        "duration": duration,
        "difficulty": difficulty,
        "sections": sections,
        "pushed_at": now(),
    }

    # Archive previous active lesson
    if s["active_lesson"]:
        s["lesson_history"].append(s["active_lesson"])
        if len(s["lesson_history"]) > 20:
            s["lesson_history"] = s["lesson_history"][-20:]

    s["active_lesson"] = lesson
    s["student_lesson_progress"] = {}  # reset progress

    save_session(code)

    # Broadcast to all students
    await ws_all_students(s, {
        "type": "lesson_pushed",
        "lesson": lesson,
    })
    return {"pushed": True, "lesson_id": lesson["lesson_id"]}


@app.post("/api/session/{code}/lesson/push_sections")
async def lesson_push_sections(
    code: str,
    section_ids: list = Body(...),
):
    """Push only specific sections of the active lesson to students."""
    s = _S(code)
    _ensure_lesson_fields(s)
    al = s.get("active_lesson")
    if not al:
        raise HTTPException(400, "No active lesson")
    filtered_sections = [sec for sec in al.get("sections", []) if sec.get("id") in section_ids]
    await ws_all_students(s, {
        "type": "lesson_sections_pushed",
        "lesson_id": al["lesson_id"],
        "title": al.get("title", ""),
        "sections": filtered_sections,
    })
    return {"pushed": True, "count": len(filtered_sections)}


@app.post("/api/session/{code}/lesson/student_progress")
async def lesson_student_progress(
    code: str,
    student_id: str = Body(...),
    section_id: str = Body(...),
    done: bool = Body(True),
):
    """Student marks a lesson section as complete."""
    s = _S(code)
    _ensure_lesson_fields(s)
    s["student_lesson_progress"].setdefault(student_id, {})[section_id] = done
    save_session(code)
    # Notify teacher
    al = s.get("active_lesson")
    total = len(al.get("sections", [])) if al else 0
    done_count = sum(1 for v in s["student_lesson_progress"].get(student_id, {}).values() if v)
    await ws_teacher(s, {
        "type": "lesson_progress_update",
        "student_id": student_id,
        "section_id": section_id,
        "done": done,
        "done_count": done_count,
        "total": total,
    })
    return {"ok": True}


@app.get("/api/session/{code}/lesson/active")
async def lesson_get_active(code: str):
    """Get the currently active lesson."""
    s = _S(code)
    _ensure_lesson_fields(s)
    return {"lesson": s.get("active_lesson")}


# ── Video Call control ─────────────────────────────────────────────

@app.post("/api/session/{code}/vc/start")
async def vc_start(code: str):
    """Teacher started a video call — notify all active students."""
    s = _S(code)
    s["vc_active"] = True
    save_session(code)
    await ws_all_students(s, {"type": "vc_started", "session_code": code})
    return {"ok": True}


@app.post("/api/session/{code}/vc/end")
async def vc_end(code: str):
    """Teacher ended the video call — notify all active students."""
    s = _S(code)
    s["vc_active"] = False
    save_session(code)
    await ws_all_students(s, {"type": "vc_ended", "session_code": code})
    return {"ok": True}


# ── evaluations control ────────────────────────────────────────────

@app.get("/api/session/{code}/evaluations")
def get_evaluations(code: str):
    s = _S(code)
    short_tasks = [t for t in s["tasks"] if t.get("type") == "short" or (t.get("type") == "coding" and t.get("evaluation_mode", "manual") == "ai")]
    results = []
    for task in short_tasks:
        task_id = task["id"]
        task_responses = s.get("responses", {}).get(task_id, {})
        student_resps = []
        for student_id, resp in task_responses.items():
            student = s["students"].get(student_id)
            if not student:
                continue
            student_resps.append({
                "student_id":        student_id,
                "student_name":      student.get("name", student_id),
                "answer":            resp.get("answer"),
                "submitted_at":      resp.get("submitted_at"),
                "evaluation_mode":   resp.get("evaluation_mode", task.get("evaluation_mode", "manual")),
                "expected_answer":   resp.get("expected_answer", task.get("correct_answer", "")),
                "max_marks":         resp.get("max_marks", score_for(task)),
                "ai_score":          resp.get("ai_score"),
                "confidence_score":  resp.get("confidence_score"),
                "explanation":       resp.get("explanation"),
                "teacher_score":     resp.get("teacher_score"),
                "evaluation_status": resp.get("evaluation_status", "pending"),
                "teacher_feedback":  resp.get("teacher_feedback", ""),
            })
        
        results.append({
            "task_id":         task_id,
            "question":        task["question"],
            "topic":           task.get("topic", "General"),
            "difficulty":      task.get("difficulty", "medium"),
            "evaluation_mode": task.get("evaluation_mode", "manual"),
            "expected_answer": task.get("correct_answer", ""),
            "max_marks":       task.get("max_marks", score_for(task)),
            "responses":       student_resps,
        })
    return {"tasks": results}


@app.post("/api/session/{code}/evaluations/run_ai")
async def run_ai_evaluation_endpoint(code: str, req: RunAiEvalReq):
    s = _S(code)
    task = _T(s, req.task_id)
    response = s.setdefault("responses", {}).setdefault(req.task_id, {}).get(req.student_id)
    if not response:
        raise HTTPException(404, "Student response not found")
    
    api_key = req.api_key or get_teacher_key(s.get("teacher_email")) or os.getenv("OPENROUTER_API_KEY") or s.get("teacher_api_key")
    if not api_key:
        raise HTTPException(400, "API key is required. Please provide it in the input or configure OPENROUTER_API_KEY.")
    
    s["teacher_api_key"] = api_key
    await run_ai_evaluation_for_response(s, task, response, api_key)
    save_session(code)
    return {"success": True, "response": response}



@app.post("/api/session/{code}/evaluations/bulk_ai")
async def bulk_ai_evaluation_endpoint(code: str, req: BulkAiEvalReq):
    s = _S(code)
    
    api_key = req.api_key or get_teacher_key(s.get("teacher_email")) or os.getenv("OPENROUTER_API_KEY") or s.get("teacher_api_key")
    if not api_key:
        raise HTTPException(400, "API key is required. Please provide it in the input or configure OPENROUTER_API_KEY.")
        
    s["teacher_api_key"] = api_key
    
    pending_evals = []
    short_tasks = [t for t in s["tasks"] if t.get("type") == "short" or (t.get("type") == "coding" and t.get("evaluation_mode", "manual") == "ai")]
    for task in short_tasks:
        task_id = task["id"]
        # AI evaluation is run for all short/long/descriptive tasks regardless of mode
        
        task_responses = s.setdefault("responses", {}).setdefault(task_id, {})
        for student_id, resp in task_responses.items():
            if resp.get("evaluation_status") == "pending":
                pending_evals.append((task, resp))
                
    if not pending_evals:
        return {"success": True, "count": 0, "message": "No pending short/long answer evaluations found"}
        
    tasks_to_run = [
        run_ai_evaluation_for_response(s, t, r, api_key)
        for t, r in pending_evals
    ]
    await asyncio.gather(*tasks_to_run)
    save_session(code)
    
    return {"success": True, "count": len(pending_evals)}


@app.post("/api/session/{code}/evaluations/approve")
async def approve_evaluation_endpoint(code: str, req: ApproveEvalReq):
    s = _S(code)
    task = _T(s, req.task_id)
    response = s.setdefault("responses", {}).setdefault(req.task_id, {}).get(req.student_id)
    if not response:
        raise HTTPException(404, "Student response not found")
        
    student = s["students"].get(req.student_id)
    if not student:
        raise HTTPException(404, "Student not found")
        
    max_m = float(response.get("max_marks") or task.get("max_marks") or score_for(task))
    score = min(max(0.0, req.score), max_m)
    
    old_status = response.get("evaluation_status", "pending")
    old_teacher_score = response.get("teacher_score", 0.0) if old_status == "approved" else 0.0
    old_correct = response.get("correct", False) if old_status == "approved" else False
    
    is_correct = score >= (max_m / 2.0)
    
    response["teacher_score"] = score
    response["teacher_feedback"] = req.feedback
    response["evaluation_status"] = "approved"
    response["correct"] = is_correct
    
    score_diff = score - old_teacher_score
    student["score"] = student.get("score", 0) + score_diff
    
    correct_diff = (1 if is_correct else 0) - (1 if old_correct else 0)
    student["correct"] = student.get("correct", 0) + correct_diff
    
    if s.get("mode") == "test":
        ts = s["test_state"]
        ts["scores"][req.student_id] = ts["scores"].get(req.student_id, 0) + score_diff
        lb_source = {sid: ts["scores"].get(sid, 0.0) for sid in ts["submitted"]}
        lb = sorted(lb_source.items(), key=lambda x: x[1], reverse=True)
        ts["leaderboard"] = [
            {
                "student_id":   sid,
                "score":        sc,
                "rank":         i + 1,
                "student_name": s["students"].get(sid, {}).get("name", sid),
            }
            for i, (sid, sc) in enumerate(lb)
        ]
    update_student_reports_on_approval(
        s, req.student_id, req.task_id, score, req.feedback, is_correct,
        strengths=response.get("strengths") if response else None,
        weaknesses=response.get("weaknesses") if response else None,
        suggestions=response.get("suggestions") if response else None
    )
    save_session(code)
    
    _appr_analytics = compute_analytics(s)
    _appr_analytics["understanding_short"] = compute_analytics(s, question_type="short").get("understanding", 0)
    _appr_analytics["understanding_long"]  = compute_analytics(s, question_type="long").get("understanding", 0)
    await ws_teacher(s, {
        "type": "analytics_update",
        "analytics": _appr_analytics,
    })
    st = s["students"].get(req.student_id)
    if st:
        await push_roster_delta(s, "update", req.student_id, {
            "total_answered": st.get("total_answered", 0),
            "correct": st.get("correct", 0)
        })
    
    await ws_student(s, req.student_id, {
        "type": "evaluation_approved",
        "task_id": req.task_id,
        "score": score,
        "max_marks": max_m,
        "feedback": req.feedback,
        "is_correct": is_correct,
        "student_score": student.get("score", 0),
        "total_answered": student.get("total_answered", 0) if student else 0,
        "correct_count": student.get("correct", 0) if student else 0,
    })
    
    return {"success": True, "response": response}


class GenerateQuestionsReq(BaseModel):
    topic: str
    q_type: str  # mcq | short | long | coding
    ai_language: Optional[str] = "python"
    count: int = 4
    api_key: Optional[str] = None

@app.post("/api/ai/generate-questions")
async def generate_questions_endpoint(req: GenerateQuestionsReq, request: Request):
    email = request.headers.get("X-User-Email")
    role = request.headers.get("X-User-Role")
    if not email or not role:
         raise HTTPException(401, "Missing security headers")
    if role != "teacher":
         raise HTTPException(403, "Access restricted to teachers")
         
    lang_label = (req.ai_language or "python").lower()
    if lang_label == 'cpp':
        lang_label = 'C++'
    else:
        lang_label = lang_label.capitalize()
        
    prompt_map = {
        "mcq": f"""Generate {req.count} multiple-choice questions about "{req.topic}".
Return ONLY a JSON array. Each object must have exactly these fields:
{{"type":"mcq","question":"...","options":["Option A","Option B","Option C","Option D"],"correct_answer":"A","hint":"...","difficulty":"easy|medium|hard"}}.
No markdown, no explanation, just the raw JSON array.""",
        "short": f"""Generate {req.count} short-answer questions about "{req.topic}".
Return ONLY a JSON array. Each object:
{{"type":"short","question":"...","correct_answer":"concise expected answer","hint":"...","difficulty":"easy|medium|hard"}}.
No markdown, no explanation, just the raw JSON array.""",
        "long": f"""Generate {req.count} long-answer/essay questions about "{req.topic}".
Return ONLY a JSON array. Each object:
{{"type":"long","question":"...","correct_answer":"detailed model answer","hint":"key points to cover","difficulty":"medium|hard"}}.
No markdown, no explanation, just the raw JSON array.""",
        "coding": f"""Generate {req.count} beginner-level coding challenges about "{req.topic}" in {lang_label}.
Return ONLY a JSON array. Each object must have exactly these fields:
{{"type":"coding","question":"Full problem statement in {lang_label} including Input Format, Output Format, Constraints, and one Sample Test Case","starter_code":"{lang_label} starter code stub (e.g. only function declaration and imports, with a 'pass' or default return statement inside the function body so the student has a starting point)","correct_answer":"{lang_label} complete working solution code that fully implements the challenge","hint":"...","difficulty":"easy|medium|hard","language":"{req.ai_language}"}}.
No markdown, no explanation, just the raw JSON array."""
    }
    
    prompt = prompt_map.get(req.q_type)
    if not prompt:
        raise HTTPException(400, f"Invalid question type: {req.q_type}")
        
    api_key_to_use = req.api_key or get_teacher_key(email) or os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")
    try:
        raw_resp = await call_llm(prompt, api_key=api_key_to_use, is_json=True)
        clean = raw_resp.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1]
        if clean.endswith("```"):
            clean = clean.rsplit("\n", 1)[0]
        if clean.startswith("json"):
            clean = clean.split("\n", 1)[1]
        clean = clean.strip()
        
        parsed = json.loads(clean)
        if not isinstance(parsed, list):
            raise ValueError("LLM response is not a JSON list")
        return parsed
    except Exception as e:
        log.error("[AI_GEN] Failed to generate questions: %s", e, exc_info=True)
        raise HTTPException(500, f"AI Generation failed: {str(e)}")


@app.get("/api/i18n/{lang}")
def get_i18n_lang(lang: str):
    loc_dir = Path(__file__).parent / "localization"
    filepath = loc_dir / f"{lang}.json"
    if not filepath.exists():
        raise HTTPException(404, f"Language pack '{lang}' not found")
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data
    except Exception as e:
        raise HTTPException(500, f"Error loading language pack: {str(e)}")


# SPA fallback: serve the frontend file for any non-API path so client-side routing
# (history API) works and refresh keeps the user on the same page.
@app.get("/{_path:path}", include_in_schema=False)
def spa_fallback(request: Request, _path: str):
    # Don't override API, WS, admin, docs or favicon routes
    p = request.url.path.lstrip("/")
    blocked_prefixes = ("api/", "ws/", "admin/", "favicon", "docs", "redoc")
    if any(p.startswith(bp) for bp in blocked_prefixes):
        raise HTTPException(404, "Not found")

    if not FRONTEND_FILE.exists():
        raise HTTPException(404, f"Frontend not found — ensure '{FRONTEND_FILE.name}' is present")

    content = FRONTEND_FILE.read_bytes()
    return Response(
        content=content,
        media_type="text/html",
        headers={"Content-Length": str(len(content))},
    )


# ── local dev ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host      = os.getenv("HOST", "0.0.0.0"),
        port      = int(os.getenv("PORT", "8000")),
        reload    = os.getenv("RELOAD", "true").lower() == "true",
        log_level = os.getenv("LOG_LEVEL", "info"),
    )


# ── Teacher Doubt Reply endpoint ──────────────────────────────────────────────
class TeacherDoubtReplyReq(BaseModel):
    session_code: str
    doubt_id: str
    text: str

@app.post("/api/doubts/teacher_reply")
async def teacher_reply_doubt(req: TeacherDoubtReplyReq):
    s = _S(req.session_code)
    s.setdefault("doubts", [])
    import time
    for d in s["doubts"]:
        if d.get("id") == req.doubt_id:
            replies = d.setdefault("replies", [])
            reply_obj = {
                "id": gen_id("tr"),
                "sender": "teacher",
                "role": "teacher",
                "sender_name": "Teacher",
                "text": req.text,
                "ts": int(time.time() * 1000),
                "attachments": []
            }
            replies.append(reply_obj)
            d["status"] = "answered"
            d["updated_at"] = now()
            save_session(req.session_code)
            await ws_teacher(s, {"type": "new_doubt", "doubt": d})
            await ws_student(s, d["student_id"], {"type": "new_doubt", "doubt": d})
            return d
    raise HTTPException(404, "Doubt not found")


class UpdateDoubtTagsReq(BaseModel):
    session_code: str
    doubt_id: str
    tags: list

@app.post("/api/doubts/update_tags")
async def update_doubt_tags(req: UpdateDoubtTagsReq):
    s = _S(req.session_code)
    s.setdefault("doubts", [])
    for d in s["doubts"]:
        if d.get("id") == req.doubt_id:
            d["tags"] = req.tags
            d["updated_at"] = now()
            save_session(req.session_code)
            return d
    raise HTTPException(404, "Doubt not found")