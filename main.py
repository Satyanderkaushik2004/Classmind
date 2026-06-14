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
import random
import time
import uuid
from contextlib import asynccontextmanager
from io import StringIO
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
)
import string
from email_service import (
    send_session_email, is_valid_email,
    send_student_report_email, send_class_starting_email,
    send_otp_email,
)
from video_call import router as vc_router




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
    if not sg_key or "your_api_key" in sg_key:
        log.warning("[!] SENDGRID_API_KEY is not configured in .env. Emails will not be sent.")
    else:
        log.info("[OK] SendGrid Email system configured.")
    
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
ADMIN_EMAILS = os.getenv("ADMIN_EMAILS", "vyom7@gmail.com").split(",")


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
    return s.setdefault("attendance", {
        "state": "inactive", "started_at": None, "ended_at": None,
        "locked_at": None, "min_duration": 60, "records": {},
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
        }

    return {
        "state":        att.get("state", "inactive"),
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
    }


async def broadcast_attendance(s: dict) -> None:
    summary = compute_attendance_summary(s)
    await ws_teacher(s, {"type": "attendance_update", "attendance": summary})


def attendance_mark_join(s: dict, student_id: str) -> None:
    """Called when a student is approved (becomes active)."""
    att = _att(s)
    if att.get("state") not in ("active", "paused"):
        return
    if att.get("locked_at"):
        return
    records = att.setdefault("records", {})
    if student_id not in records:
        records[student_id] = {
            "student_id":  student_id,
            "join_at":     now(),
            "leave_at":    None,
            "duration":    0,
            "status":      "present",
            "interactions": 0,
        }
    else:
        r = records[student_id]
        if r.get("status") == "exited":
            r["join_at"]  = now()
            r["leave_at"] = None
            r["status"]   = "present"


def attendance_mark_leave(s: dict, student_id: str) -> None:
    """Called when a student WebSocket disconnects."""
    att = _att(s)
    if att.get("state") not in ("active", "paused"):
        return
    if att.get("locked_at"):
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

    min_dur      = att.get("min_duration", 60)
    interactions = r.get("interactions", 0)

    if duration >= min_dur or interactions > 0:
        r["status"] = "exited"
    else:
        r["status"] = "revoked"


def attendance_add_interaction(s: dict, student_id: str) -> None:
    """Increment interaction counter for a student (chat, answer, code run)."""
    att = _att(s)
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
    s = sessions.get(code)
    if not s:
        raise HTTPException(404, f"Session '{code}' not found")
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
        "starter_code":    starter_code or correct_answer,
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
                    lb = sorted(ts["scores"].items(), key=lambda x: x[1], reverse=True)
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
    touch_session(s)
    
    # Broadcast to all connected clients
    await ws_broadcast(s, {"type": "session_status", "status": "ended"})
    
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

async def autosave_worker():
    """Periodically persist all sessions to disk."""
    interval = int(os.getenv("AUTOSAVE_INTERVAL", "10"))
    while True:
        await asyncio.sleep(interval)
        for code in list(sessions):
            save_session(code)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global semaphore, execution_queue
    semaphore       = asyncio.Semaphore(3)
    execution_queue = asyncio.Queue()

    # ── Persistence: configure and load saved sessions ────────────
    configure_persistence(
        mode     = os.getenv("PERSISTENCE", "json"),
        data_dir = os.getenv("DATA_DIR", "data"),
    )
    loaded = load_all_sessions()
    if loaded:
        log.info("Restored %d session(s) from disk", loaded)

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
    yield
    # Final save before shutdown
    for code in list(sessions):
        save_session(code)
    t1.cancel(); t2.cancel(); t3.cancel(); t4.cancel(); t5.cancel()
    log.info("VYOM stopped.")


app = FastAPI(
    title="VYOM API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.include_router(vc_router)

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
    
    return {
        "sessions": teacher_history,
        "stats": {
            "total_sessions": len(teacher_history),
            "total_students": total_students,
            "avg_participation": round(avg_participation, 1),
            "avg_understanding": round(avg_understanding, 1),
        }
    }

# Consolidated exception handling moved to bottom

# ── CORS: single-origin setup — fully open so no fetch failures ─
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
FRONTEND_FILE = Path(__file__).with_name(os.getenv("FRONTEND_FILE", "vyom_single.html"))

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

class SendOtpReq(BaseModel):
    email: str
    name: str
    role: str
    phone: Optional[str] = None

class VerifyOtpReq(BaseModel):
    email: str
    otp: str

@app.post("/api/auth/send-otp")
async def send_otp(req: SendOtpReq):
    email = req.email.strip().lower()
    name = req.name.strip()
    role = req.role.strip().lower()
    phone = (req.phone or "").strip()
    
    if not email:
        raise HTTPException(400, "Email is required")
    if not is_valid_email(email):
        raise HTTPException(400, f"Invalid email format: {email}")
    if not name:
        raise HTTPException(400, "Name is required")
    if role not in ["teacher", "student"]:
        raise HTTPException(400, "Invalid role. Must be 'teacher' or 'student'")

    # Generate 6-digit OTP code
    otp = "".join(random.choices(string.digits, k=6))
    
    # Store with expiration of 5 minutes (300 seconds)
    expires_at = time.time() + 300
    otp_store[email] = {
        "otp": otp,
        "expires_at": expires_at,
        "name": name,
        "phone": phone,
        "role": role
    }
    
    # Check if email config is present (SendGrid key)
    from email_service import validate_smtp_config
    if not validate_smtp_config():
        log.warning(f"\n"
                    f"========================================\n"
                    f"🔑 [DEMO MODE] EMAIL NOT CONFIGURED\n"
                    f"📧 Email: {email}\n"
                    f"👤 Name: {name} ({role})\n"
                    f"🔢 OTP Code: {otp}\n"
                    f"========================================\n")
        return {
            "success": True,
            "demo": True,
            "message": "Demo mode: Email service not configured on server. Please check the backend console logs for your OTP code."
        }
        
    try:
        # Send OTP email
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
        # Fallback to demo mode printed log if send fails (resilient)
        log.warning(f"\n"
                    f"========================================\n"
                    f"🔑 [FALLBACK DEMO] SMTP SEND FAILED\n"
                    f"📧 Email: {email}\n"
                    f"👤 Name: {name} ({role})\n"
                    f"🔢 OTP Code: {otp}\n"
                    f"========================================\n")
        return {
            "success": True,
            "demo": True,
            "message": f"Could not deliver email. The OTP code is printed to backend console logs for local testing."
        }

@app.get("/api/debug/otp")
async def debug_otp(email: str, request: Request):
    if request.client is None or request.client.host not in ("127.0.0.1", "::1"):
        raise HTTPException(403, "Debug OTP access is restricted to localhost")
    record = otp_store.get(email.strip().lower())
    if not record:
        raise HTTPException(404, "No OTP found for this email")
    return {
        "email": email,
        "otp": record["otp"],
        "expires_at": record["expires_at"],
    }

@app.post("/api/auth/verify-otp")
async def verify_otp(req: VerifyOtpReq):
    email = req.email.strip().lower()
    otp_code = req.otp.strip()
    
    if not email or not otp_code:
        raise HTTPException(400, "Email and OTP code are required")
        
    record = otp_store.get(email)
    if not record:
        raise HTTPException(400, "No verification pending for this email. Please request a new code.")
        
    if time.time() > record["expires_at"]:
        otp_store.pop(email, None)
        raise HTTPException(400, "Verification code has expired. Please request a new code.")
        
    if record["otp"] != otp_code:
        raise HTTPException(400, "Incorrect verification code. Please try again.")
        
    # Success! Remove OTP from store
    otp_store.pop(email, None)
    
    # Construct profile matching format
    profile = {
        "id": "u_" + str(int(time.time() * 1000)),
        "name": record["name"],
        "email": email,
        "phone": record["phone"],
        "role": record["role"],
        "createdAt": int(time.time() * 1000),
        "roleHistory": [record["role"]],
        "sessionsCreated": [],
        "sessionsJoined": [],
        "stats": {
            "totalSessionsCreated": 0,
            "totalSessionsJoined": 0,
            "avgParticipation": 0,
            "avgUnderstanding": 0
        }
    }
    
    log.info("[OTP] OTP verification successful for %s (%s)", email, record["role"])
    return {
        "success": True,
        "profile": profile
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


@app.get("/vyom_logo.png", include_in_schema=False)
def get_vyom_logo():
    logo_path = Path(__file__).parent / "vyom_logo.png"
    if logo_path.exists():
        return FileResponse(logo_path, media_type="image/png")
    raise HTTPException(404, "Logo not found")


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
    touch_session(s)
    await ws_broadcast(s, {"type": "session_ended", "session_code": code})
    admin_broadcast({"event": "session_ended", "session_code": code, "teacher_name": s.get("teacher_name")})
    log.info("Admin ended session %s by %s", code, admin_username)
    return {"ended": True, "session_code": code}


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

    try:
        # 1. Validate SMTP config first
        from email_service import validate_smtp_config
        if not validate_smtp_config():
            log.error("[EMAIL_TASK] FAILED: SMTP not configured (check .env for session %s)", code)
            return

        # 2. Compute report
        try:
            report = compute_report(s)
            if not report:
                log.error("[EMAIL_TASK] FAILED: compute_report returned None for %s", code)
                return
        except Exception as exc:
            log.error("[EMAIL_TASK] FAILED: compute_report error for %s: %s", code, exc)
            return

        # 3. Check email
        if not teacher_email or not is_valid_email(teacher_email):
            log.warning("[EMAIL_TASK] SKIPPED: No valid teacher email for session %s", code)
            return

        # 4. SEND (Awaited)
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
                    att.setdefault("records", {})[sid] = {
                        "student_id": sid,
                        "join_at":    now(),
                        "leave_at":   None,
                        "duration":   0,
                        "status":     "present",
                        "interactions": 0,
                    }
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
            log.info("[AUTO-EMAIL] End-of-session email task queued for %s", code)
    elif action == "start":
        # ── Notify students with emails that class has started ────────
        if background_tasks is not None:
            background_tasks.add_task(_send_class_start_notifications, s)
            log.info("[AUTO-EMAIL] Class-start notification task queued for %s", code)
        # ── Broadcast attendance state after auto-start ───────────────
        asyncio.create_task(broadcast_attendance(s))
    save_session(code)
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

    # ═ STEP 1: Create student and add to waiting room ═
    student          = new_student(name_n, anonymous)
    student["roll"]  = roll_n
    student["class"] = cls_n
    student["status"] = "waiting"  # Explicitly set to waiting
    if email and email.strip():
        student["email"] = email.strip()
    if phone and phone.strip():
        student["phone"] = phone.strip()

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
    await push_roster(s)  # This sends both active and waiting to teacher
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
    await push_roster(s)
    
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
    await push_roster(s)
    
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
    await push_roster(s)
    roll = s["students"].get(student_id, {}).get("roll")
    if roll:
        s.get("active_rolls", set()).discard(normalize_string(roll))
    return {"kicked": True}


# ── Student Profile Photo ──────────────────────────────────────────

class PhotoUploadReq(BaseModel):
    photo: str   # base64 data URL, e.g. "data:image/jpeg;base64,..."

@app.post("/api/session/{code}/student/{student_id}/photo")
async def upload_student_photo(code: str, student_id: str, req: PhotoUploadReq):
    """Store student's profile photo (base64 data URL) on their session record.
    Returns immediately; no WebSocket broadcast needed — photo is cosmetic only."""
    s = _S(code)
    student = s["students"].get(student_id)
    if not student:
        raise HTTPException(404, "Student not found")
    if not req.photo or not req.photo.startswith("data:image/"):
        raise HTTPException(400, "Invalid photo format — must be a base64 image data URL")
    # Limit to ~3 MB base64 payload (4 bytes per 3 raw bytes ≈ 4 MB base64 for 3 MB image)
    if len(req.photo) > 4_100_000:
        raise HTTPException(400, "Photo too large — max 3 MB")
    student["profile_photo"] = req.photo
    touch_session(s)
    save_session(code)
    log.info("[PHOTO] Saved profile photo for student %s in session %s", student_id, code)
    # Notify teacher so their roster/avatar updates immediately
    await push_roster(s)
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
    await push_roster(s)
    
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
    s = _S(code)
    return compute_attendance_summary(s)


@app.post("/api/session/{code}/attendance/control")
async def attendance_control_endpoint(
    code:         str,
    action:       str = Query(...),
    min_duration: int = Query(60),
):
    """Teacher controls attendance: start|pause|resume|end|lock."""
    s   = _S(code)
    att = _att(s)

    if action == "start":
        if att.get("state") == "locked":
            raise HTTPException(409, "Attendance is locked — cannot restart")
        att["state"]      = "active"
        att["started_at"] = att.get("started_at") or now()
        att["min_duration"] = max(0, min_duration)
        # Retroactively mark all currently active students as present
        for sid, st in s["students"].items():
            if st.get("status") == "active" and sid not in att["records"]:
                att["records"][sid] = {
                    "student_id": sid,
                    "join_at":    now(),
                    "leave_at":   None,
                    "duration":   0,
                    "status":     "present",
                    "interactions": 0,
                }

    elif action == "pause":
        att["state"] = "paused"

    elif action == "resume":
        if att.get("state") == "locked":
            raise HTTPException(409, "Attendance is locked")
        att["state"] = "active"

    elif action == "end":
        att["state"]    = "ended"
        att["ended_at"] = now()
        # Finalize durations for all still-present students
        for r in att["records"].values():
            if r.get("status") == "present":
                end_t = now()
                r["leave_at"] = end_t
                r["duration"] = end_t - (r.get("join_at") or end_t)

    elif action == "lock":
        att["state"]     = "locked"
        att["locked_at"] = now()
        if not att.get("ended_at"):
            att["ended_at"] = now()

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
    status:     str = Query(...),
):
    """Teacher manually overrides a single student's attendance status."""
    s   = _S(code)
    att = _att(s)
    if att.get("state") == "locked":
        raise HTTPException(409, "Attendance is locked — cannot edit")
    valid = {"present", "absent", "exited", "revoked"}
    if status not in valid:
        raise HTTPException(400, f"status must be one of {valid}")
    records = att.setdefault("records", {})
    if student_id not in records:
        records[student_id] = {"student_id": student_id, "join_at": None,
                               "leave_at": None, "duration": 0, "interactions": 0}
    records[student_id]["status"] = status
    save_session(code)
    await broadcast_attendance(s)
    return {"updated": True}
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
    s["access_mode"] = req.access_mode
    save_session(code)
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

    # Use key from request or fallback to server-side env variables (OpenRouter or Gemini)
    key_to_use = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")

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
    
    prompt = f"""
You are an expert academic evaluator. Compare the student's answer against the expected answer and grade it out of {max_marks} marks.

Question: {question}
Expected Answer: {expected_answer}
Student Answer: {student_answer}
Maximum Marks: {max_marks}

Evaluate based on relevance, correctness, completeness, and semantic similarity. Do not penalize for exact keyword mismatch if the meaning is correct.

Return ONLY a valid JSON object with the following keys:
- "suggested_marks": a number (integer or float) between 0 and {max_marks} representing the score.
- "confidence_score": a number between 0 and 1 representing your confidence.
- "explanation": a brief, clear explanation of the grade.

Do not include any markdown styling, code blocks, or extra text. Output only the raw JSON.
"""
    try:
        import httpx
        import json
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://openrouter.ai/api/v1/chat/completions",
                headers={
                    "Content-Type":  "application/json",
                    "Authorization": f"Bearer {api_key}",
                    "HTTP-Referer":  "https://vyom.app",
                    "X-Title":       "VYOM AI Evaluation",
                },
                json={
                    "model":    "openai/gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 400,
                },
            )
        if resp.status_code == 200:
            data = resp.json()
            content = (
                data.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
                .strip()
            )
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
            
            response["ai_score"] = min(max(0.0, suggested_marks), max_marks)
            response["confidence_score"] = confidence
            response["explanation"] = explanation
            
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
                    lb = sorted(ts["scores"].items(), key=lambda x: x[1], reverse=True)
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
                    update_student_reports_on_approval(s, student_id, task["id"], score, explanation, is_correct)
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
                    await push_roster(s)
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
                    })
                except Exception as ws_student_err:
                    log.warning("[AI EVALUATION] failed to notify student: %s", ws_student_err)
        else:
            raise RuntimeError(f"API Error {resp.status_code}: {resp.text}")
            
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
    is_short_answer = task.get("type") == "short"  # covers both short and long_answer

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
    elif is_short_answer:
        correct = False
    else:
        correct = req.answer.strip() == task.get("correct_answer", "").strip()

    if is_short_answer:
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
        s["responses"].setdefault(req.task_id, {})[req.student_id] = resp_data
        
        if student:
            student["total_answered"] += 1
            student["last_seen"] = now()
            
        api_key = os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY") or s.get("teacher_api_key")
        if eval_mode == "ai" and api_key:
            background_tasks.add_task(
                run_ai_evaluation_for_response, s, task, resp_data, api_key
            )
    else:
        s["responses"].setdefault(req.task_id, {})[req.student_id] = {
            "answer":       req.answer,
            "correct":      correct,
            "time_taken":   req.time_taken,
            "submitted_at": now(),
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
        }
    
    return {
        "correct":        correct,
        "score":          score_for(task) if correct else 0,
        "correct_answer": task.get("correct_answer", ""),
        "student_score":  student.get("score", 0) if student else 0,
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
    })
    return {"id": file_id, "filename": fname, "size": len(raw), "content_type": ct}


@app.get("/api/session/{code}/content")
def list_content(code: str):
    s     = _S(code)
    files = [
        {
            "id":           v.get("id", v["name"]),
            "name":         v["name"],
            "content_type": v["content_type"],
            "size":         v["size"],
            "uploaded_at":  v["uploaded_at"],
        }
        for v in s["content_files"].values()
    ]
    return {"files": files}


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
    entry = {
        "id":           file_id,
        "name":         fname,
        "data":         encoded,
        "content_type": ct,
        "size":         len(raw),
        "uploaded_at":  now(),
        "chat_file":    True,   # mark as chat file
    }
    s["content_files"][fname] = entry
    save_session(code)

    # Create chat message with file attachment
    msg_type = "image" if is_image else "file"
    sys_file_msg = {
        "id":          gen_id("m"),
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
    entry = {
        "id":           file_id,
        "name":         fname,
        "data":         encoded,
        "content_type": ct,
        "size":         len(raw),
        "uploaded_at":  now(),
        "chat_file":    True,
    }
    s["content_files"][fname] = entry
    save_session(session_code)

    st = s["students"].get(sender_id)
    if st:
        name = st["name"]
    elif sender_id == "teacher":
        name = s.get("teacher_name", "Teacher")
    else:
        name = "Student"

    msg_type = "image" if is_image else "file"
    msg = {
        "id":          gen_id("m"),
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
    if not ct.startswith("image/"):
        raise HTTPException(415, "Only images allowed in doubts")

    raw = await image.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(413, "Image too large (max 5 MB)")

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
    }
    s["content_files"][fname] = entry
    save_session(session_code)

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
        "image_url":    f"/api/content/file/{session_code}/{fname}",
    }
    s["doubts"].append(d)
    save_session(session_code)

    await ws_teacher(s, {"type": "new_doubt", "doubt": d})
    return d


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
            await ws_broadcast(s, {"type": "doubt_resolved", "doubt": d})
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
            await ws_broadcast(s, {"type": "doubt_reopened", "doubt": d})
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

        # 2. SMTP basic check
        from email_service import validate_smtp_config
        if not validate_smtp_config():
            log.error("[SEND_REPORT] SMTP missing credentials")
            return {
                "success": False,
                "status":  "error",
                "message": "Email service not configured.",
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
    lb    = sorted(ts["scores"].items(), key=lambda x: x[1], reverse=True)
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
    lb           = sorted(ts["scores"].items(), key=lambda x: x[1], reverse=True)
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

def update_student_reports_on_approval(s: dict, student_id: str, task_id: str, score: float, feedback: str, is_correct: bool):
    reports = s.setdefault("student_reports", {}).setdefault(student_id, [])
    for rpt in reports:
        if rpt.get("type") == "task" and rpt.get("questions") and rpt["questions"][0].get("task_id") == task_id:
            q = rpt["questions"][0]
            q["is_correct"] = is_correct
            q["marks_earned"] = score
            q["teacher_feedback"] = feedback
            q["evaluation_status"] = "approved"
            
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
                    
                    rpt["score"] = rpt.get("score", 0) - old_earned + score
                    correct_change = (1 if is_correct else 0) - (1 if old_correct else 0)
                    rpt["correct_count"] = rpt.get("correct_count", 0) + correct_change
                    max_score = rpt.get("max_score", 1) or 1
                    rpt["percentage"] = round(rpt["score"] / max_score * 100, 1)
                    break


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
            if task.get("type") == "short":
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
                "evaluation_status": resp.get("evaluation_status", "pending") if task.get("type") == "short" else "approved",
                "teacher_feedback":  resp.get("teacher_feedback", ""),
            })
        else:
            q_entry.update({
                "student_answer":    None,
                "is_correct":        False,
                "marks_earned":      0.0,
                "time_taken":        0,
                "attempted":         False,
                "evaluation_status": "pending" if task.get("type") == "short" else "approved",
                "teacher_feedback":  "",
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

    if task.get("type") == "short":
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
        "evaluation_status": resp.get("evaluation_status", "pending") if task.get("type") == "short" else "approved",
        "teacher_feedback":  resp.get("teacher_feedback", ""),
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
            student["coding_submitted"]  = True
            student["test_cases_passed"] = random.randint(2, 5)
            student["total_test_cases"]  = 5
            student["coding_score"]      = int((student["test_cases_passed"] / 5) * 100)
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

    student["coding_submitted"]  = True
    student["test_cases_passed"] = random.randint(3, 5)
    student["total_test_cases"]  = 5
    student["coding_score"]      = int((student["test_cases_passed"] / 5) * 100)

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
                        await ws_broadcast(s, {"type": "doubt_resolved", "doubt": d})
                        await ws_send(ws, {"type": "doubts_update", "doubts": s["doubts"]})
                        break
                if not found:
                    await ws_send(ws, {"type": "error", "message": "Doubt not found"})

            # ── ATTENDANCE CONTROLS (teacher-side) ──────────────────────
            elif cmd == "attendance_control":
                action   = data.get("action", "")
                min_dur  = int(data.get("min_duration", 60))
                att      = _att(s)
                if action == "start":
                    att["state"]      = "active"
                    att["started_at"] = att.get("started_at") or now()
                    att["min_duration"] = max(0, min_dur)
                    for sid, st in s["students"].items():
                        if st.get("status") == "active" and sid not in att["records"]:
                            att["records"][sid] = {
                                "student_id": sid, "join_at": now(),
                                "leave_at": None, "duration": 0,
                                "status": "present", "interactions": 0,
                            }
                elif action == "pause":
                    att["state"] = "paused"
                elif action == "resume":
                    att["state"] = "active"
                elif action == "end":
                    att["state"]    = "ended"
                    att["ended_at"] = now()
                    for r in att["records"].values():
                        if r.get("status") == "present":
                            end_t = now(); r["leave_at"] = end_t
                            r["duration"] = end_t - (r.get("join_at") or end_t)
                elif action == "lock":
                    att["state"]     = "locked"
                    att["locked_at"] = now()
                    if not att.get("ended_at"):
                        att["ended_at"] = now()
                save_session(session_code)
                await broadcast_attendance(s)
                log.info("[ATTENDANCE] %s in session %s", action, session_code)

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

    await ws_send(ws, {
        "type":                "connected",
        "role":                "student",
        "student":             student,
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

    # Use key from request or fallback to server-side env variables (OpenRouter or Gemini)
    key_to_use = api_key or os.getenv("OPENROUTER_API_KEY") or os.getenv("GEMINI_API_KEY")

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
    short_tasks = [t for t in s["tasks"] if t.get("type") == "short"]
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
    
    api_key = req.api_key or os.getenv("OPENROUTER_API_KEY") or s.get("teacher_api_key")
    if not api_key:
        raise HTTPException(400, "API key is required. Please provide it in the input or configure OPENROUTER_API_KEY.")
    
    s["teacher_api_key"] = api_key
    await run_ai_evaluation_for_response(s, task, response, api_key)
    save_session(code)
    return {"success": True, "response": response}



@app.post("/api/session/{code}/evaluations/bulk_ai")
async def bulk_ai_evaluation_endpoint(code: str, req: BulkAiEvalReq):
    s = _S(code)
    
    api_key = req.api_key or os.getenv("OPENROUTER_API_KEY") or s.get("teacher_api_key")
    if not api_key:
        raise HTTPException(400, "API key is required. Please provide it in the input or configure OPENROUTER_API_KEY.")
        
    s["teacher_api_key"] = api_key
    
    pending_evals = []
    short_tasks = [t for t in s["tasks"] if t.get("type") == "short"]
    for task in short_tasks:
        task_id = task["id"]
        if task.get("evaluation_mode", "manual") != "ai":
            continue
        
        task_responses = s.setdefault("responses", {}).setdefault(task_id, {})
        for student_id, resp in task_responses.items():
            if resp.get("evaluation_status") == "pending":
                pending_evals.append((task, resp))
                
    if not pending_evals:
        return {"success": True, "count": 0, "message": "No pending AI-enabled evaluations found"}
        
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
        lb = sorted(ts["scores"].items(), key=lambda x: x[1], reverse=True)
        ts["leaderboard"] = [
            {
                "student_id":   sid,
                "score":        sc,
                "rank":         i + 1,
                "student_name": s["students"].get(sid, {}).get("name", sid),
            }
            for i, (sid, sc) in enumerate(lb)
        ]
        
    update_student_reports_on_approval(s, req.student_id, req.task_id, score, req.feedback, is_correct)
    save_session(code)
    
    _appr_analytics = compute_analytics(s)
    _appr_analytics["understanding_short"] = compute_analytics(s, question_type="short").get("understanding", 0)
    _appr_analytics["understanding_long"]  = compute_analytics(s, question_type="long").get("understanding", 0)
    await ws_teacher(s, {
        "type": "analytics_update",
        "analytics": _appr_analytics,
    })
    await push_roster(s)
    
    await ws_student(s, req.student_id, {
        "type": "evaluation_approved",
        "task_id": req.task_id,
        "score": score,
        "max_marks": max_m,
        "feedback": req.feedback,
        "is_correct": is_correct,
        "student_score": student.get("score", 0),
    })
    
    return {"success": True, "response": response}


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
