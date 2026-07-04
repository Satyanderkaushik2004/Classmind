"""
store.py  —  VYOM in-memory data store
All session state lives here. Structure is Redis-ready (flat dicts).
Adds optional JSON persistence: load on startup, auto-save on change.
"""
import json
import logging
import os
import random
import string
import time
import uuid
import concurrent.futures
import threading
from pathlib import Path
from typing import Dict, Optional

log = logging.getLogger("vyom.store")

# ── global store ──────────────────────────────────────────────────
sessions: Dict[str, dict] = {}   # session_code -> session dict
teacher_sessions: Dict[str, str] = {}  # teacher_id (email) -> session_code

# ── persistence config (set by main.py after loading .env) ────────
_persistence_mode: str = "none"   # "none" | "json"
_data_dir: Path = Path("data")


def configure_persistence(mode: str, data_dir: str) -> None:
    """Called once from main.py lifespan after reading .env."""
    global _persistence_mode, _data_dir
    _persistence_mode = mode.lower().strip()
    _data_dir = Path(data_dir)
    if _persistence_mode == "json":
        _data_dir.mkdir(parents=True, exist_ok=True)
        log.info("Persistence: JSON -> %s", _data_dir.resolve())
    else:
        log.info("Persistence: in-memory only (sessions reset on restart)")


# ── id helpers ────────────────────────────────────────────────────
def gen_code() -> str:
    for _ in range(20):
        c = "".join(random.choices(string.digits, k=6))
        if c not in sessions:
            return c
    raise RuntimeError("Cannot generate unique code")


def gen_id(prefix="") -> str:
    return prefix + uuid.uuid4().hex[:8]


def now() -> float:
    return time.time()


# ── JSON persistence helpers ──────────────────────────────────────

def _session_path(code: str) -> Path:
    return _data_dir / f"session_{code}.json"


def _serialize_session(s: dict) -> dict:
    """Convert non-serialisable types (sets, WebSockets) before JSON dump."""
    def _convert(obj):
        if isinstance(obj, set):
            if any(hasattr(x, "send_text") for x in obj):
                return None
            return {"__set__": list(obj)}
        if hasattr(obj, "send_text"):          # WebSocket — never serialise
            return None
        raise TypeError(f"Cannot serialise {type(obj)}")

    return json.loads(json.dumps(s, default=_convert))


def _deserialize_session(d: dict) -> dict:
    """Restore sets from the __set__ sentinel; reinit runtime-only fields."""
    def _restore(obj):
        if isinstance(obj, dict):
            if "__set__" in obj and len(obj) == 1:
                items = obj["__set__"]
                # Tuples are stored as JSON arrays; convert back to tuples so
                # they are hashable and can be re-added to a Python set.
                try:
                    return set(
                        tuple(i) if isinstance(i, list) else i
                        for i in items
                    )
                except TypeError:
                    return set()
            return {k: _restore(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_restore(i) for i in obj]
        return obj

    s = _restore(d)
    # Runtime WebSocket fields are never stored — reinit to None / empty dict
    s["teacher_ws"] = None
    s.setdefault("ws_clients", {})
    s.setdefault("duration_mins", 0)
    s.setdefault("started_at", None)
    # ── Migrate old tasks to include starter_code ─────────────────────
    for t in s.get("tasks", []):
        if isinstance(t, dict) and "starter_code" not in t:
            t["starter_code"] = t.get("correct_answer", "")
    # ── Migrate old content_files entries that lack an 'id' or other new fields ──
    for fname, cf in s.get("content_files", {}).items():
        if "id" not in cf:
            import uuid as _uuid
            cf["id"] = "cf" + _uuid.uuid4().hex[:8]
        cf.setdefault("title", cf.get("title", fname))
        if "type" not in cf:
            name_lower = fname.lower()
            ct = (cf.get("content_type") or "").lower()
            if ct.startswith("image/") or any(name_lower.endswith(ext) for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]):
                cf["type"] = "image"
            elif ct == "application/pdf" or name_lower.endswith(".pdf"):
                cf["type"] = "pdf"
            elif ct.startswith("video/") or any(name_lower.endswith(ext) for ext in [".mp4", ".webm", ".mov", ".avi"]):
                cf["type"] = "video"
            elif any(name_lower.endswith(ext) for ext in [".ppt", ".pptx"]):
                cf["type"] = "presentation"
            elif any(name_lower.endswith(ext) for ext in [".doc", ".docx", ".txt"]):
                cf["type"] = "note"
            else:
                cf["type"] = "note"
        cf.setdefault("uploadedBy", cf.get("uploadedBy", s.get("teacher_name", "Teacher")))
        cf.setdefault("uploaderRole", cf.get("uploaderRole", "teacher"))
        cf.setdefault("source", cf.get("source", "Content Upload"))
        cf.setdefault("sourceChannel", cf.get("sourceChannel", "Library"))
        cf.setdefault("timestamp", cf.get("timestamp", cf.get("uploaded_at", now())))
        cf.setdefault("visibility", cf.get("visibility", "Class Visible"))
        cf.setdefault("previewUrl", cf.get("previewUrl", f"/api/content/file/{s.get('code', '')}/{fname}"))
        cf.setdefault("tags", cf.get("tags", ["TEACHER"]))
        cf.setdefault("linkedChatMessageId", cf.get("linkedChatMessageId", None))
    # ── Migrate: add suspended_chat_students if missing ───────────────
    if "suspended_chat_students" not in s:
        s["suspended_chat_students"] = set()
    elif not isinstance(s["suspended_chat_students"], set):
        s["suspended_chat_students"] = set(s.get("suspended_chat_students") or [])
    # ── Migrate: add class_end_warning_flags if missing ───────────────
    if "class_end_warning_flags" not in s:
        s["class_end_warning_flags"] = {}
    # ── Migrate: ensure all chat messages have reactions dict ─────────
    for m in s.get("chat_messages", []):
        if isinstance(m, dict) and "reactions" not in m:
            m["reactions"] = {}
    # ── Migrate: ensure all students have profile_photo field ─────────
    for st in s.get("students", {}).values():
        if isinstance(st, dict) and "profile_photo" not in st:
            st["profile_photo"] = None
    return s


# Thread pool for asynchronous background saving
_save_executor = concurrent.futures.ThreadPoolExecutor(max_workers=3)
_save_locks = {}
_save_locks_lock = threading.Lock()

def _get_session_lock(code: str) -> threading.Lock:
    with _save_locks_lock:
        if code not in _save_locks:
            _save_locks[code] = threading.Lock()
        return _save_locks[code]

def _bg_save_session(code: str, serialized_data: dict, path: Path) -> None:
    lock = _get_session_lock(code)
    with lock:
        try:
            tmp = path.with_suffix(".tmp")
            content = json.dumps(serialized_data, ensure_ascii=False, indent=2)
            tmp.write_text(content, encoding="utf-8")
            tmp.replace(path)
        except Exception as exc:
            log.warning("Failed to save session %s in background: %s", code, exc)

# Track dirty sessions in memory for batch saving
dirty_sessions = set()
dirty_lock = threading.Lock()

def mark_session_dirty(code: str) -> None:
    with dirty_lock:
        dirty_sessions.add(code)

def save_session(code: str, force: bool = False) -> None:
    """Save session to disk. If force is False, it is marked dirty for batch saving."""
    if _persistence_mode != "json":
        return
    
    if not force:
        mark_session_dirty(code)
        return
        
    s = sessions.get(code)
    if s is None:
        return
    try:
        with dirty_lock:
            dirty_sessions.discard(code)
            
        # Serialize synchronously to prevent concurrent modification errors in background thread
        serialized_data = _serialize_session(s)
        path = _session_path(code)
        _save_executor.submit(_bg_save_session, code, serialized_data, path)
    except Exception as exc:
        log.warning("Failed to queue save for session %s: %s", code, exc)


def delete_session_file(code: str) -> None:
    """Remove a persisted session file."""
    if _persistence_mode != "json":
        return
    try:
        _session_path(code).unlink(missing_ok=True)
    except Exception as exc:
        log.debug("Could not delete session file %s: %s", code, exc)


def load_all_sessions() -> int:
    """Load all session files from disk into memory. Returns count loaded."""
    if _persistence_mode != "json":
        return 0
    loaded = 0
    if not _data_dir.exists():
        return 0
    for path in sorted(_data_dir.glob("session_*.json")):
        code = path.stem.replace("session_", "")
        try:
            raw = path.read_text(encoding="utf-8")
            s   = _deserialize_session(json.loads(raw))
            sessions[code] = s
            # Rebuild teacher_sessions mapping
            t_id = s.get("teacher_email") or s.get("teacher_id")
            if t_id and s.get("status") != "ended":
                teacher_sessions[t_id] = code
            loaded += 1
            log.info("Loaded session %s (%s)", code, s.get("status", "?"))
        except Exception as exc:
            log.warning("Skipped corrupt session file %s: %s", path.name, exc)
    return loaded


# ── session factory ───────────────────────────────────────────────
def new_session(code: str, teacher_name: str) -> dict:
    return {
        "code":             code,
        "teacher_name":     teacher_name,
        "teacher_id":       None,        # Linked to Google email
        "status":           "waiting",   # waiting|active|paused|ended
        "mode":             "live",      # live|test
        "created_at":       now(),
        "last_activity_at": now(),
        "duration_mins":    0,
        "started_at":       None,
        "vc_active":        False,
        # websockets (runtime only — never persisted)
        "teacher_ws":       None,
        "ws_clients":       {},          # student_id -> WebSocket
        # roster
        "students":         {},          # student_id -> student dict
        "waiting_room":     [],          # [student_id, ...]
        "kicked":           set(),
        "access_mode":      "open",        # "open" | "closed"  (closed = CSV uploaded) | "close" (geo-fenced)
        "allowed_students": set(),        # optional CSV admission list (tuples: name,roll,cls)
        "active_rolls":     set(),        # duplicate login guard
        "close_access_location": None,     # teacher GPS location for Close Access mode
        "close_access_radius_meters": 100, # validation radius for Close Access mode
        # tasks
        "tasks":            [],
        "current_task_idx": -1,
        "responses":        {},          # task_id -> {student_id -> response}
        "delivery_seq":     0,
        "task_deliveries":  {},          # delivery_id -> delivery metadata
        "student_current_task": {},      # student_id -> latest task_id assigned
        # groups
        "groups":           [],
        # communication
        "chat_messages":    [],
        "doubts":           [],
        # ── Chat moderation ───────────────────────────────────────────
        "suspended_chat_students": set(),   # student_ids suspended from sending chat
        # ── Class-end timer warnings (emitted once each) ──────────────
        "class_end_warning_flags": {},      # {"10": False, "5": False, "2": False}
        "raised_hands":     {},         # dict: {student_id: {name, raised_at}}
        # content
        "content_files":    {},          # filename -> {name,data,content_type,size}
        "quiz":             None,
        # ── attendance ────────────────────────────────────────────────
        "attendance": {
            "state":        "inactive",  # inactive|active|paused|ended|locked
            "started_at":   None,
            "ended_at":     None,
            "locked_at":    None,
            "min_duration": 60,          # seconds before a join counts as present
            "records":      {},          # student_id -> record dict
        },
        # ── student reports (persisted review data) ──────────────────
        # student_id -> list of report dicts (test/quiz/task)
        "student_reports": {},

        # ── AI Lesson Planner ─────────────────────────────────────────
        "lesson_templates": {},      # template_id -> template dict
        "active_lesson":    None,    # currently pushed lesson (or None)
        "lesson_history":   [],      # list of previously pushed lessons
        "lesson_drafts":    {},      # draft_id -> draft dict
        "student_lesson_progress": {},  # student_id -> {section_id -> done}

        # test mode
        "test_state": {
            "active":        False,
            "start_time":    None,
            "duration_secs": 0,
            "task_ids":      [],
            "submitted":     set(),
            "scores":        {},          # student_id -> int
            "leaderboard":   [],
            "quiz":          None,
            "answers":       {},          # student_id -> {answers, submitted_at, student_name}
        },
    }


# ── student factory ───────────────────────────────────────────────
def new_student(name: str, anonymous: bool = True) -> dict:
    sid = gen_id()
    return {
        "id":             sid,
        "name":           name,
        "real_name":      name,
        "anonymous":      anonymous,
        "status":         "waiting",
        "score":          0,
        "correct":        0,
        "total_answered": 0,
        "hint_requests":  0,
        "joined_at":      now(),
        "last_seen":      now(),
        "allowed_students": set(),
        "active_rolls":   set(),
        # profile photo (base64 data URL, stored on upload)
        "profile_photo":  None,
        # coding analytics
        "coding_score":       0,
        "coding_submitted":   False,
        "test_cases_passed":  0,
        "total_test_cases":   0,
        "coding_time_taken":  0,
        # attendance
        "att_status":    "not_marked",  # not_marked|present|exited|revoked|absent
        "att_join_at":   None,
        "att_leave_at":  None,
        "att_duration":  0,
        "att_interactions": 0,
    }


# ── task factory ──────────────────────────────────────────────────
def new_task(d: dict) -> dict:
    return {
        "id":              gen_id("t"),
        "question":        d.get("question", ""),
        "type":            d.get("type", "mcq"),         # mcq|short|coding
        "options":         d.get("options", []),
        "correct_answer":  d.get("correct_answer", d.get("answer", "")),
        "starter_code":    d.get("starter_code", ""),
        "test_input":      d.get("test_input", ""),
        "topic":           d.get("topic", "General"),
        "difficulty":      d.get("difficulty", "medium"),
        "hint":            d.get("hint"),
        "hint_visibility": d.get("hint_visibility", "on_request"),
        "time_limit":      d.get("time_limit"),
        "long_answer":     bool(d.get("long_answer", False)),
        "content_file":    d.get("content_file"),
        "language":        str(d.get("language") or "python").strip().lower(),
        "evaluation_mode": d.get("evaluation_mode", "manual"),
        "max_marks":       d.get("max_marks", None),
        "created_at":      now(),
    }


# ── helpers ───────────────────────────────────────────────────────
DIFF_SCORE = {"easy": 5, "medium": 10, "hard": 20}


def score_for(task: dict) -> int:
    if task.get("max_marks") is not None:
        try:
            return int(task["max_marks"])
        except (ValueError, TypeError):
            pass
    return DIFF_SCORE.get(task.get("difficulty", "medium"), 10)


def safe_task(task: dict) -> dict:
    """Strip correct_answer and hide hint unless visibility=always."""
    t = {k: v for k, v in task.items() if k != "correct_answer"}
    t["id"]              = str(t.get("id") or "")
    t["question"]        = str(t.get("question") or "")
    t["type"]            = str(t.get("type") or "mcq")
    t["options"]         = t.get("options") or []
    t["topic"]           = str(t.get("topic") or "General")
    t["difficulty"]      = str(t.get("difficulty") or "medium")
    t["hint_visibility"] = str(t.get("hint_visibility") or "on_request")
    t["language"]        = str(task.get("language") or "python").strip().lower()
    t["starter_code"]    = str(task.get("starter_code") or "")
    t["test_input"]      = str(task.get("test_input") or "")
    t["evaluation_mode"] = str(task.get("evaluation_mode") or "manual").strip().lower()
    t["max_marks"]       = int(task.get("max_marks") or score_for(task))
    if t.get("hint_visibility") != "always":
        t["hint"] = None
    return t


def get_session(code: str) -> Optional[dict]:
    """Return session or None."""
    return sessions.get(code)


# ── Lesson Planner helpers ────────────────────────────────────────

def new_lesson_template(data: dict) -> dict:
    """Create a new lesson template structure."""
    return {
        "template_id":  gen_id("lt"),
        "title":        data.get("title", "Untitled Lesson"),
        "topic":        data.get("topic", ""),
        "subject":      data.get("subject", ""),
        "grade":        data.get("grade", ""),
        "duration":     data.get("duration", 45),
        "difficulty":   data.get("difficulty", "medium"),
        "learning_goal": data.get("learning_goal", ""),
        "custom_instructions": data.get("custom_instructions", ""),
        "tags":         data.get("tags", []),
        "content":      data.get("content", {}),   # section_id -> {title, body}
        "favorite":     False,
        "created_at":   now(),
        "updated_at":   now(),
        "teacher_id":   data.get("teacher_id", ""),
        "version":      1,
    }


def new_active_lesson(template: dict, sections: list) -> dict:
    """Wrap a template into a pushed-live lesson record."""
    return {
        "lesson_id":    gen_id("al"),
        "template_id":  template.get("template_id", ""),
        "title":        template.get("title", ""),
        "topic":        template.get("topic", ""),
        "subject":      template.get("subject", ""),
        "grade":        template.get("grade", ""),
        "duration":     template.get("duration", 45),
        "difficulty":   template.get("difficulty", "medium"),
        "sections":     sections,   # list of {id, title, body, type}
        "pushed_at":    now(),
        "pushed_by":    template.get("teacher_id", ""),
    }


# ── Teacher API Key storage helper ───────────────────────────────
TEACHER_KEYS_FILE = Path("data/teacher_api_keys.json")
_teacher_api_keys: Dict[str, str] = {}


def load_teacher_keys() -> None:
    global _teacher_api_keys
    try:
        if TEACHER_KEYS_FILE.exists():
            with open(TEACHER_KEYS_FILE, "r", encoding="utf-8") as f:
                _teacher_api_keys = json.load(f)
        else:
            _teacher_api_keys = {}
    except Exception as e:
        log.warning("Failed to load teacher keys: %s", e)
        _teacher_api_keys = {}


def save_teacher_keys() -> None:
    try:
        TEACHER_KEYS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TEACHER_KEYS_FILE, "w", encoding="utf-8") as f:
            json.dump(_teacher_api_keys, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning("Failed to save teacher keys: %s", e)


def get_teacher_key(email: str) -> Optional[str]:
    if not email:
        return None
    return _teacher_api_keys.get(email.strip().lower())


def set_teacher_key(email: str, api_key: str) -> None:
    if not email:
        return
    _teacher_api_keys[email.strip().lower()] = api_key.strip()
    save_teacher_keys()


def delete_teacher_key(email: str) -> None:
    if not email:
        return
    email_clean = email.strip().lower()
    if email_clean in _teacher_api_keys:
        del _teacher_api_keys[email_clean]
        save_teacher_keys()


# ── Teacher Cloud Storage integration storage helper ─────────────
TEACHER_INTEGRATIONS_FILE = Path("data/teacher_cloud_integrations.json")
_teacher_integrations: Dict[str, dict] = {}


def load_teacher_integrations() -> None:
    global _teacher_integrations
    try:
        if TEACHER_INTEGRATIONS_FILE.exists():
            with open(TEACHER_INTEGRATIONS_FILE, "r", encoding="utf-8") as f:
                _teacher_integrations = json.load(f)
        else:
            _teacher_integrations = {}
    except Exception as e:
        log.warning("Failed to load teacher cloud integrations: %s", e)
        _teacher_integrations = {}


def save_teacher_integrations() -> None:
    try:
        TEACHER_INTEGRATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TEACHER_INTEGRATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(_teacher_integrations, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning("Failed to save teacher cloud integrations: %s", e)


def get_teacher_integration(email: str, provider: str = "google") -> Optional[dict]:
    if not email:
        return None
    email_clean = email.strip().lower()
    return _teacher_integrations.get(email_clean, {}).get(provider)


def set_teacher_integration(email: str, data: dict, provider: str = "google") -> None:
    if not email:
        return
    email_clean = email.strip().lower()
    if email_clean not in _teacher_integrations:
        _teacher_integrations[email_clean] = {}
    _teacher_integrations[email_clean][provider] = data
    save_teacher_integrations()


def delete_teacher_integration(email: str, provider: str = "google") -> None:
    if not email:
        return
    email_clean = email.strip().lower()
    if email_clean in _teacher_integrations and provider in _teacher_integrations[email_clean]:
        del _teacher_integrations[email_clean][provider]
        if not _teacher_integrations[email_clean]:
            del _teacher_integrations[email_clean]
        save_teacher_integrations()


# ── Teacher Notification Preferences storage helper ────────────────
TEACHER_NOTIFICATIONS_FILE = Path("data/teacher_notification_prefs.json")
_teacher_notification_prefs: Dict[str, dict] = {}


def load_teacher_notification_prefs() -> None:
    global _teacher_notification_prefs
    try:
        if TEACHER_NOTIFICATIONS_FILE.exists():
            with open(TEACHER_NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
                _teacher_notification_prefs = json.load(f)
        else:
            _teacher_notification_prefs = {}
    except Exception as e:
        log.warning("Failed to load teacher notification preferences: %s", e)
        _teacher_notification_prefs = {}


def save_teacher_notification_prefs() -> None:
    try:
        TEACHER_NOTIFICATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TEACHER_NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(_teacher_notification_prefs, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning("Failed to save teacher notification preferences: %s", e)


def get_teacher_notification_prefs(email: str) -> dict:
    if not email:
        return {}
    email_clean = email.strip().lower()
    return _teacher_notification_prefs.get(email_clean, {
        "global_enabled": True,
        "categories": {
            "chat": {
                "enabled": True,
                "types": {
                    "new_doubts": True,
                    "student_messages": True,
                    "chat_uploads": True
                }
            },
            "classroom": {
                "enabled": True,
                "types": {
                    "waiting_room": True,
                    "attendance_updates": True,
                    "session_events": True
                }
            },
            "tasks": {
                "enabled": True,
                "types": {
                    "deadlines": True,
                    "evaluations": True,
                    "task_created": True
                }
            }
        }
    })


def set_teacher_notification_prefs(email: str, prefs: dict) -> None:
    if not email:
        return
    email_clean = email.strip().lower()
    _teacher_notification_prefs[email_clean] = prefs
    save_teacher_notification_prefs()


# ── Student Notification Preferences storage helper ────────────────
STUDENT_NOTIFICATIONS_FILE = Path("data/student_notification_prefs.json")
_student_notification_prefs: Dict[str, dict] = {}

_STUDENT_NOTIF_DEFAULTS = {
    "global_enabled": True,
    "preset": "standard",
    "categories": {
        "classroom": {
            "enabled": True,
            "types": {
                "session_started": True,
                "teacher_announcements": True,
                "attendance_updates": True,
                "live_class_reminder": True,
                "class_cancelled": True,
            }
        },
        "tasks": {
            "enabled": True,
            "types": {
                "new_assignment": True,
                "assignment_due_reminder": True,
                "assignment_graded": True,
                "submission_confirmation": True,
                "late_submission_warning": True,
            }
        },
        "chat": {
            "enabled": True,
            "types": {
                "teacher_reply": True,
                "new_chat_message": True,
                "doubt_answered": True,
                "mention_notifications": True,
            }
        },
        "ai": {
            "enabled": True,
            "types": {
                "daily_learning_tips": True,
                "ai_study_suggestions": True,
                "weak_topic_alerts": True,
                "personalized_recommendations": True,
            }
        },
        "reports": {
            "enabled": True,
            "types": {
                "test_result_published": True,
                "weekly_progress": True,
                "performance_report": True,
                "achievement_earned": True,
            }
        },
        "system": {
            "enabled": True,
            "types": {
                "login_alerts": True,
                "account_updates": True,
                "security_notifications": True,
                "maintenance_notices": True,
            }
        }
    }
}


def load_student_notification_prefs() -> None:
    global _student_notification_prefs
    try:
        if STUDENT_NOTIFICATIONS_FILE.exists():
            with open(STUDENT_NOTIFICATIONS_FILE, "r", encoding="utf-8") as f:
                _student_notification_prefs = json.load(f)
        else:
            _student_notification_prefs = {}
    except Exception as e:
        log.warning("Failed to load student notification preferences: %s", e)
        _student_notification_prefs = {}


def save_student_notification_prefs() -> None:
    try:
        STUDENT_NOTIFICATIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(STUDENT_NOTIFICATIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(_student_notification_prefs, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning("Failed to save student notification preferences: %s", e)


def get_student_notification_prefs(identifier: str) -> dict:
    """Get student notification prefs by email or student_id."""
    if not identifier:
        return dict(_STUDENT_NOTIF_DEFAULTS)
    key = identifier.strip().lower()
    return _student_notification_prefs.get(key, dict(_STUDENT_NOTIF_DEFAULTS))


def set_student_notification_prefs(identifier: str, prefs: dict) -> None:
    if not identifier:
        return
    key = identifier.strip().lower()
    _student_notification_prefs[key] = prefs
    save_student_notification_prefs()


def student_notification_enabled(identifier: str, category: str, type_: str) -> bool:
    """Return True if a given student notification type is enabled."""
    if not identifier:
        return True
    prefs = get_student_notification_prefs(identifier)
    if not prefs:
        return True
    if prefs.get("global_enabled") is False:
        return False
    cat = prefs.get("categories", {}).get(category, {})
    if cat.get("enabled") is False:
        return False
    return cat.get("types", {}).get(type_) is not False


# ── Downloads Library persistence storage helpers ─────────────────
DOWNLOADS_FILE = Path("data/downloads.json")
REPORTS_DIR = Path("data/reports")
_downloads_store: Dict[str, list] = {}


def load_downloads() -> None:
    global _downloads_store
    try:
        if DOWNLOADS_FILE.exists():
            with open(DOWNLOADS_FILE, "r", encoding="utf-8") as f:
                _downloads_store = json.load(f)
        else:
            _downloads_store = {}
    except Exception as e:
        log.warning("Failed to load downloads: %s", e)
        _downloads_store = {}


def save_downloads() -> None:
    try:
        DOWNLOADS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(DOWNLOADS_FILE, "w", encoding="utf-8") as f:
            json.dump(_downloads_store, f, indent=2, ensure_ascii=False)
    except Exception as e:
        log.warning("Failed to save downloads: %s", e)


def get_downloads(email: str) -> list:
    if not email:
        return []
    email_clean = email.strip().lower()
    return _downloads_store.get(email_clean, [])


def add_download(email: str, entry: dict) -> None:
    if not email:
        return
    email_clean = email.strip().lower()
    lib = _downloads_store.setdefault(email_clean, [])
    # Unshift to the top of list
    lib.insert(0, entry)
    _downloads_store[email_clean] = lib[:200]
    save_downloads()


def delete_download(email: str, report_id: str) -> None:
    if not email:
        return
    email_clean = email.strip().lower()
    lib = _downloads_store.get(email_clean, [])
    entry = next((r for r in lib if r.get("id") == report_id), None)
    if entry:
        file_path = entry.get("file_path")
        if file_path:
            try:
                p = Path(file_path)
                if p.exists():
                    p.unlink()
            except Exception as e:
                log.warning("Failed to delete report file %s: %s", file_path, e)
    _downloads_store[email_clean] = [r for r in lib if r.get("id") != report_id]
    save_downloads()


def cleanup_inactive_sessions(max_inactive_hours: int = 24) -> int:
    """Remove sessions that have been inactive or ended for too long. Returns purged count."""
    now_ts = now()
    max_inactive_secs = max_inactive_hours * 3600
    to_remove = []
    
    for code, s in list(sessions.items()):
        status = s.get("status", "waiting")
        last_activity = s.get("last_activity_at", s.get("created_at", now_ts))
        
        is_inactive = (now_ts - last_activity) > max_inactive_secs
        is_ended = status == "ended"
        
        # Clean up ended sessions after 2 hours, or active/waiting after max_inactive_hours
        if (is_ended and (now_ts - last_activity) > 7200) or is_inactive:
            to_remove.append(code)
            
    purged = 0
    for code in to_remove:
        s = sessions.get(code)
        if s:
            try:
                # Save state before purging
                save_session(code, force=True)
            except Exception as e:
                log.warning("[MEM PURGE] Failed to save session %s before purging: %s", code, e)
                
            sessions.pop(code, None)
            t_email = s.get("teacher_email")
            if t_email and teacher_sessions.get(t_email) == code:
                teacher_sessions.pop(t_email, None)
            purged += 1
            
    if purged > 0:
        log.info("[MEM PURGE] Cleaned %d expired/ended session(s) from memory", purged)
    return purged