"""
main.py  ─  ClassMind Backend  (fully reconstructed)
Run:  uvicorn main:app --host 0.0.0.0 --port 8000 --reload

WebSocket endpoints
  ws://host/ws/teacher/{session_code}
  ws://host/ws/student/{session_code}/{student_id}
"""

from __future__ import annotations

import asyncio
import base64
import csv
import json
import logging
import random
import time
from contextlib import asynccontextmanager
from io import StringIO
from pathlib import Path
from typing import Dict, List, Optional
from fastapi.middleware.cors import CORSMiddleware
from fastapi import (
    Body, FastAPI, File, Form, HTTPException,
    Query, UploadFile, WebSocket, WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from analytics import compute_analytics, compute_report
from sandbox import RunResult, run_code
from store import (
    gen_code, gen_id, new_session, new_student, new_task,
    now, safe_task, score_for, sessions,
)

# ── logging ───────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("classmind")

# ── concurrency helpers ───────────────────────────────────────────
semaphore: asyncio.Semaphore        # initialised in lifespan
execution_queue: asyncio.Queue      # initialised in lifespan
session_locks: Dict[str, asyncio.Lock] = {}


def session_lock(code: str) -> asyncio.Lock:
    if code not in session_locks:
        session_locks[code] = asyncio.Lock()
    return session_locks[code]


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


async def ws_teacher(s: dict, data: dict) -> bool:
    if s.get("teacher_ws"):
        return await ws_send(s["teacher_ws"], data)
    return False


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
    active  = [st for st in s["students"].values() if st["status"] == "active"]
    waiting = [s["students"][sid] for sid in s["waiting_room"] if sid in s["students"]]
    await ws_teacher(s, {
        "type":         "roster_update",
        "active":       active,
        "waiting":      waiting,
        "raised_hands": s["raised_hands"],
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
            "data":         cf["data"],
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
    # ✅ ALLOW QUIZ SUBMISSIONS — quiz questions are never in the task delivery
    # pipeline, so delivery-based validation must be fully bypassed when a quiz
    # is active (quiz_meta present) OR session is in test mode.
    if s.get("quiz_meta"):          # quiz_start was sent via /quiz/send
        return True
    if s.get("mode") == "test":     # legacy test mode
        return True
    return any(
        student_id in d.get("recipients", []) and d.get("task_id") == task_id
        for d in s.get("task_deliveries", {}).values()
    )


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
        "topic":           str(data.get("topic") or "General").strip() or "General",
        "difficulty":      difficulty,
        "hint":            str(data.get("hint")).strip() if data.get("hint") else None,
        "hint_visibility": hint_visibility,
        "time_limit":      time_limit,
        "long_answer":     long_answer,
        "content_file":    data.get("content_file"),
    }


# ══════════════════════════════════════════════════════════════════
#  PYDANTIC MODELS
# ══════════════════════════════════════════════════════════════════

class CreateSessionReq(BaseModel):
    teacher_name: str

class CreateTaskReq(BaseModel):
    session_code:    str
    question:        str
    type:            str = "mcq"
    options:         Optional[List[str]] = []
    correct_answer:  Optional[str] = ""
    topic:           str = "General"
    difficulty:      str = "medium"
    hint:            Optional[str] = None
    hint_visibility: str = "on_request"
    time_limit:      Optional[int] = None
    long_answer:     bool = False

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

class SubmitDoubtReq(BaseModel):
    session_code: str
    student_id:   str
    doubt_text:   str

class ResolveDoubtReq(BaseModel):
    session_code: str
    doubt_id:     str
    answer:       str

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

class SaveQuizReq(BaseModel):
    session_code: str
    quiz:         list
    task_ids:     Optional[List[str]] = None   # preferred: ordered task IDs


class SendQuizReq(BaseModel):
    task_ids:    Optional[List[str]] = None
    target_type: str = "all"
    target_id:   Optional[str] = "all"


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


async def code_worker():
    while True:
        code, language, future = await execution_queue.get()
        try:
            async with semaphore:
                result = run_code(code, language)
            future.set_result(result)
        except Exception as e:
            future.set_result(RunResult(f"Error: {e}", error=True))
        finally:
            execution_queue.task_done()


# ══════════════════════════════════════════════════════════════════
#  APP SETUP
# ══════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    global semaphore, execution_queue
    semaphore       = asyncio.Semaphore(3)
    execution_queue = asyncio.Queue()

    log.info("ClassMind starting…")
    t1 = asyncio.create_task(analytics_broadcaster())
    t2 = asyncio.create_task(test_timer_watcher())
    t3 = asyncio.create_task(code_worker())
    yield
    t1.cancel(); t2.cancel(); t3.cancel()
    log.info("ClassMind stopped.")


app = FastAPI(
    title="ClassMind API",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://satyanderkaushik2004.github.io",
        "https://satyanderkaushik2004.github.io/classmind-frontend"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_FILE = Path(__file__).with_name("classmind_enhanced.html")


@app.get("/")
def serve_frontend():
    if not FRONTEND_FILE.exists():
        raise HTTPException(404, "Frontend not found")
    return FileResponse(FRONTEND_FILE)


@app.get("/health")
def health():
    return {"status": "ok", "sessions": len(sessions)}


# ══════════════════════════════════════════════════════════════════
#  SESSION ROUTES
# ══════════════════════════════════════════════════════════════════

@app.post("/api/session/create")
async def create_session(req: CreateSessionReq):
    code = gen_code()
    sessions[code] = new_session(code, req.teacher_name)
    log.info("Session created: %s by %s", code, req.teacher_name)
    return {"session_code": code, "teacher_name": req.teacher_name}


@app.get("/api/session/{code}")
def get_session_info(code: str):
    s = _S(code)
    return {
        "code":             s["code"],
        "status":           s["status"],
        "mode":             s["mode"],
        "teacher_name":     s["teacher_name"],
        "student_count":    sum(1 for st in s["students"].values() if st["status"] == "active"),
        "waiting_count":    len(s["waiting_room"]),
        "current_task_idx": s["current_task_idx"],
        "total_tasks":      len(s["tasks"]),
        "created_at":       s["created_at"],
    }


@app.post("/api/session/{code}/control")
async def session_control(code: str, action: str = Query(...)):
    s   = _S(code)
    MAP = {"start": "active", "pause": "paused", "resume": "active", "end": "ended"}
    if action not in MAP:
        raise HTTPException(400, f"Unknown action '{action}'")
    s["status"] = MAP[action]
    await ws_broadcast(s, {"type": "session_status", "status": s["status"]})
    return {"status": s["status"]}


@app.post("/api/session/{code}/join")
async def join_session(
    code:      str,
    name:      str  = Query(...),
    roll:      str  = Query(...),
    cls:       str  = Query(...),
    anonymous: bool = Query(True),
):
    s = _S(code)
    if s["status"] == "ended":
        raise HTTPException(400, "Session has already ended")

    name_n = name.strip().lower()
    roll_n = roll.strip()
    cls_n  = cls.strip().upper()

    if s.get("allowed_students"):
        match = next(
            (item for item in s["allowed_students"]
             if item[0] == name_n and item[1] == roll_n and item[2] == cls_n),
            None,
        )
        if not match:
            raise HTTPException(403, "You are not allowed in this session")
        name_n, roll_n, cls_n = match

    if roll_n in s.get("active_rolls", set()):
        raise HTTPException(403, "This roll number is already active")

    student          = new_student(name, anonymous)
    student["roll"]  = roll_n
    student["class"] = cls_n

    s["students"][student["id"]] = student
    s["waiting_room"].append(student["id"])
    s.setdefault("active_rolls", set()).add(roll_n)

    await ws_teacher(s, {
        "type":         "student_waiting",
        "student_id":   student["id"],
        "display_name": student["name"],
    })
    return {"student_id": student["id"], "display_name": student["name"]}


@app.post("/api/session/{code}/approve/{student_id}")
async def approve_student(code: str, student_id: str):
    s = _S(code)
    if student_id not in s["students"]:
        raise HTTPException(404, "Student not found")
    if student_id in s["waiting_room"]:
        s["waiting_room"].remove(student_id)
    s["students"][student_id]["status"] = "active"
    await ws_student(s, student_id, {"type": "approved"})
    await push_roster(s)
    return {"approved": True}


@app.post("/api/session/{code}/reject/{student_id}")
async def reject_student(code: str, student_id: str):
    s = _S(code)
    if student_id in s["waiting_room"]:
        s["waiting_room"].remove(student_id)
    if student_id in s["students"]:
        s["students"][student_id]["status"] = "removed"
    s["kicked"].add(student_id)
    await ws_student(s, student_id, {"type": "rejected"})
    await push_roster(s)
    roll = s["students"].get(student_id, {}).get("roll")
    if roll:
        s.get("active_rolls", set()).discard(roll)
    return {"rejected": True}


@app.post("/api/session/{code}/kick/{student_id}")
async def kick_student(code: str, student_id: str):
    s = _S(code)
    if student_id in s["students"]:
        s["students"][student_id]["status"] = "removed"
    s["kicked"].add(student_id)
    await ws_student(s, student_id, {"type": "kicked"})
    await push_roster(s)
    roll = s["students"].get(student_id, {}).get("roll")
    if roll:
        s.get("active_rolls", set()).discard(roll)
    return {"kicked": True}


@app.get("/api/session/{code}/students")
def get_students(code: str):
    s       = _S(code)
    active  = [st for st in s["students"].values() if st["status"] == "active"]
    waiting = [s["students"][sid] for sid in s["waiting_room"] if sid in s["students"]]
    return {"active": active, "waiting": waiting}


@app.post("/api/session/{code}/upload_students")
async def upload_students(code: str, file: UploadFile = File(...)):
    s       = _S(code)
    content = await file.read()
    decoded = content.decode("utf-8")
    lines   = decoded.splitlines()

    header_index = 0
    for i, line in enumerate(lines):
        if "Name" in line and ("Roll" in line or "Enrollment" in line):
            header_index = i
            break

    cleaned = "\n".join(lines[header_index:])
    reader  = csv.DictReader(StringIO(cleaned), delimiter=",")

    allowed = set()
    skipped: list = []
    for i, row in enumerate(reader, start=1):
        name = (row.get("Name") or row.get("Student Name") or "").strip().lower()
        roll = (row.get("Roll No") or row.get("Enrollment No") or "").strip()
        cls  = (row.get("Branch") or row.get("Class") or row.get("Section") or "").strip().upper()
        if name and roll and cls:
            allowed.add((name, roll, cls))
        else:
            skipped.append({"row_number": i, "raw": row})

    s["allowed_students"] = allowed
    log.info("Student CSV loaded=%s skipped=%s", len(allowed), len(skipped))
    return {"loaded": len(allowed), "skipped": skipped[:5], "message": "Upload processed"}


# ══════════════════════════════════════════════════════════════════
#  TASK ROUTES
# ══════════════════════════════════════════════════════════════════

@app.post("/api/tasks/create")
async def create_task(req: CreateTaskReq):
    s    = _S(req.session_code)
    task = new_task(normalize_task_input(req.model_dump()))
    async with session_lock(req.session_code):
        s["tasks"].append(task)
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


# ── Task sending ───────────────────────────────────────────────────

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


# ── Responses ──────────────────────────────────────────────────────

@app.post("/api/responses/submit")
async def submit_response(req: SubmitResponseReq):
    s       = _S(req.session_code)
    task    = _T(s, req.task_id)
    student = s["students"].get(req.student_id)

    if not student or student.get("status") != "active":
        raise HTTPException(403, "Student is not active")
    if not student_can_submit_task(s, req.student_id, req.task_id):
        raise HTTPException(403, "Task has not been delivered to this student")

    correct = req.answer.strip() == task.get("correct_answer", "").strip()
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

    await ws_teacher(s, {
        "type":           "analytics_update",
        "analytics":      compute_analytics(s),
        "task_id":        req.task_id,
        "response_count": len(s["responses"].get(req.task_id, {})),
    })
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
    "application/pdf",
    "image/png", "image/jpeg", "image/jpg",
    "image/gif", "image/webp", "image/svg+xml",
}
MAX_BYTES = 10 * 1024 * 1024  # 10 MB


@app.post("/api/content/upload")
async def upload_content(session_code: str = Form(...), file: UploadFile = File(...)):
    s  = _S(session_code)
    ct = file.content_type or ""
    if ct not in ALLOWED_CT:
        raise HTTPException(415, f"File type '{ct}' not supported")
    raw = await file.read()
    if len(raw) > MAX_BYTES:
        raise HTTPException(413, "File too large (max 10 MB)")

    fname   = file.filename or f"file_{int(now())}"
    encoded = base64.b64encode(raw).decode()
    s["content_files"][fname] = {
        "name": fname, "data": encoded,
        "content_type": ct, "size": len(raw), "uploaded_at": now(),
    }
    await ws_all_students(s, {
        "type":         "content_shared",
        "filename":     fname,
        "content_type": ct,
        "data":         encoded,
    })
    return {"filename": fname, "size": len(raw), "content_type": ct}


@app.get("/api/session/{code}/content")
def list_content(code: str):
    s     = _S(code)
    files = [
        {"name": v["name"], "content_type": v["content_type"],
         "size": v["size"], "uploaded_at": v["uploaded_at"]}
        for v in s["content_files"].values()
    ]
    return {"files": files}


@app.delete("/api/session/{code}/content/{filename}")
async def delete_content(code: str, filename: str):
    s = _S(code)
    if filename not in s["content_files"]:
        raise HTTPException(404, "File not found")
    del s["content_files"][filename]
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
    st   = s["students"].get(req.sender_id)
    name = st["name"] if st else "Teacher"

    msg = {
        "id":          gen_id("m"),
        "sender_id":   req.sender_id,
        "sender_name": name,
        "content":     req.content,
        "chat_type":   req.chat_type,
        "target_id":   req.target_id,
        "timestamp":   now(),
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


@app.post("/api/doubts/submit")
async def submit_doubt(req: SubmitDoubtReq):
    s  = _S(req.session_code)
    st = s["students"].get(req.student_id, {})
    d  = {
        "id":           gen_id("d"),
        "student_id":   req.student_id,
        "student_name": st.get("name", "?"),
        "text":         req.doubt_text,
        "answer":       None,
        "resolved":     False,
        "created_at":   now(),
    }
    s["doubts"].append(d)
    await ws_teacher(s, {"type": "new_doubt", "doubt": d})
    return d


@app.post("/api/doubts/resolve")
async def resolve_doubt(req: ResolveDoubtReq):
    s = _S(req.session_code)
    for d in s["doubts"]:
        if d["id"] == req.doubt_id:
            d.update({"answer": req.answer, "resolved": True, "resolved_at": now()})
            await ws_broadcast(s, {"type": "doubt_resolved", "doubt": d})
            return d
    raise HTTPException(404, "Doubt not found")


@app.get("/api/session/{code}/doubts")
def get_doubts(code: str):
    return {"doubts": _S(code)["doubts"]}


@app.post("/api/session/{code}/raise_hand/{student_id}")
async def raise_hand(code: str, student_id: str):
    s  = _S(code)
    if student_id not in s["raised_hands"]:
        s["raised_hands"].append(student_id)
    st = s["students"].get(student_id, {})
    await ws_teacher(s, {
        "type":         "hand_raised",
        "student_id":   student_id,
        "student_name": st.get("name", "?"),
    })
    return {"raised": True}


@app.post("/api/session/{code}/lower_hand/{student_id}")
async def lower_hand(code: str, student_id: str):
    s = _S(code)
    if student_id in s["raised_hands"]:
        s["raised_hands"].remove(student_id)
    await ws_teacher(s, {"type": "hand_lowered", "student_id": student_id})
    return {"lowered": True}


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


@app.post("/api/session/{code}/send-report")
async def send_report(code: str, email: str = Query(...)):
    return {"status": "email sent (mock)", "email": email}


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


# ── Quiz helpers ───────────────────────────────────────────────────

@app.post("/api/session/{code}/quiz/send")
async def send_quiz(code: str, req: SendQuizReq = Body(default=SendQuizReq())):
    """
    Send quiz to all students as a SINGLE atomic quiz_start WS event.
    Quiz is completely isolated from the task delivery pipeline.
    """
    s = _S(code)

    # Resolve ordered task ID list
    task_ids: List[str] = []
    if req.task_ids:
        task_ids = req.task_ids
    elif s.get("quiz_task_ids"):
        task_ids = s["quiz_task_ids"]
    elif s.get("quiz"):
        raw = s["quiz"]
        task_ids = [
            item["id"] if isinstance(item, dict) and "id" in item else item
            for item in raw if isinstance(item, (str, dict))
        ]
    else:
        raise HTTPException(400, "No quiz questions specified")

    if not task_ids:
        raise HTTPException(400, "Quiz has no questions")

    # Build safe question payloads (correct_answer stripped)
    questions = [safe_task(t) for tid in task_ids
                 for t in [next((x for x in s["tasks"] if x["id"] == tid), None)] if t]

    if not questions:
        raise HTTPException(400, "None of the quiz task IDs exist in this session")

    quiz_id = gen_id("qz")

    # Store quiz metadata for reconnect recovery and submission validation
    s["quiz_meta"] = {
        "id":       quiz_id,
        "task_ids": task_ids,
        "sent_at":  now(),
        "total":    len(questions),
    }

    payload = {
        "type": "quiz_start",
        "quiz": {
            "id":        quiz_id,
            "questions": questions,
            "total":     len(questions),
        },
    }

    log.info("Quiz %s sent to session %s — %d questions", quiz_id, code, len(questions))
    await ws_all_students(s, payload)
    return {"status": "quiz sent", "quiz_id": quiz_id, "total": len(questions)}


@app.post("/api/session/quiz/save")
async def save_quiz(req: SaveQuizReq):
    s = _S(req.session_code)
    s["quiz"] = req.quiz
    if req.task_ids:
        s["quiz_task_ids"] = req.task_ids
    return {"status": "saved"}


# ══════════════════════════════════════════════════════════════════
#  QUIZ REPORT SYSTEM
# ══════════════════════════════════════════════════════════════════

def evaluate_quiz(s: dict, quiz_questions: list) -> dict:
    """
    Evaluate all student answers against quiz_questions.
    Returns { student_id -> { score, total, details, student_name } }
    """
    results: dict = {}
    ts = s.get("test_state", {})

    for student_id, data in ts.get("answers", {}).items():
        student_answers = data.get("answers", {})
        score    = 0
        detailed = []

        for q in quiz_questions:
            task_id = str(q.get("id", ""))
            correct = str(q.get("correct_answer", "")).strip().upper()

            # answers are keyed by task_id (sent from frontend as q.id)
            student_ans = student_answers.get(task_id) or student_answers.get(task_id.upper())

            if q.get("type", "mcq") == "coding":
                # Coding questions: manual grading pending
                is_correct = False
            else:
                is_correct = bool(
                    student_ans is not None and
                    str(student_ans).strip().upper() == correct
                )

            if is_correct:
                score += 1

            detailed.append({
                "question":       q.get("question", ""),
                "correct_answer": q.get("correct_answer", ""),
                "student_answer": student_ans,
                "is_correct":     is_correct,
                "type":           q.get("type", "mcq"),
                "options":        q.get("options", []),
                "topic":          q.get("topic", ""),
            })

        results[student_id] = {
            "score":        score,
            "total":        len(quiz_questions),
            "details":      detailed,
            "student_name": data.get("student_name"),
        }

    return results


def _quiz_questions_for_session(s: dict) -> list:
    """Resolve the ordered list of full task dicts for the session's active quiz."""
    meta = s.get("quiz_meta")
    if not meta:
        raise HTTPException(400, "No quiz has been sent in this session")
    task_ids = meta.get("task_ids", [])
    questions = [
        t for tid in task_ids
        for t in [next((x for x in s["tasks"] if x["id"] == tid), None)]
        if t
    ]
    if not questions:
        raise HTTPException(400, "Quiz questions not found in session tasks")
    return questions


@app.get("/quiz/report/{code}")
async def get_quiz_report(code: str):
    """Teacher: full class-level quiz report, sorted by score descending."""
    s         = _S(code)
    questions = _quiz_questions_for_session(s)
    report    = evaluate_quiz(s, questions)

    # Build sorted leaderboard-style list for teacher view
    rows = sorted(
        [
            {
                "student_id":   sid,
                "student_name": v["student_name"] or sid,
                "score":        v["score"],
                "total":        v["total"],
                "percentage":   round(v["score"] / v["total"] * 100) if v["total"] else 0,
            }
            for sid, v in report.items()
        ],
        key=lambda r: r["score"],
        reverse=True,
    )

    for i, r in enumerate(rows):
        r["rank"] = i + 1

    return {
        "report":    report,
        "rows":      rows,
        "total_q":   len(questions),
        "submitted": len(report),
    }


@app.get("/quiz/report/{code}/{student_id}")
async def get_student_quiz_report(code: str, student_id: str):
    """Student: personal quiz report with per-question breakdown."""
    s         = _S(code)
    questions = _quiz_questions_for_session(s)
    report    = evaluate_quiz(s, questions)
    result    = report.get(student_id)
    if not result:
        raise HTTPException(404, "No submission found for this student")
    return result


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

    loop    = asyncio.get_event_loop()
    future  = loop.create_future()
    await execution_queue.put((req.code, req.language, future))
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
        await ws.accept()
        await ws_send(ws, {"type": "error", "message": "Session not found"})
        await ws.close()
        return

    await ws.accept()
    s["teacher_ws"] = ws
    log.info("Teacher connected: %s", session_code)

    active  = [st for st in s["students"].values() if st["status"] == "active"]
    waiting = [s["students"][sid] for sid in s["waiting_room"] if sid in s["students"]]
    await ws_send(ws, {
        "type": "connected",
        "role": "teacher",
        "session": {
            "code":       s["code"],
            "status":     s["status"],
            "mode":       s["mode"],
            "tasks":      s["tasks"],
            "groups":     s["groups"],
            "deliveries": [delivery_summary(d) for d in s.get("task_deliveries", {}).values()],
        },
        "analytics": compute_analytics(s),
        "roster":    {"active": active, "waiting": waiting},
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

    except WebSocketDisconnect:
        log.info("Teacher disconnected: %s", session_code)
    finally:
        if s.get("teacher_ws") is ws:
            s["teacher_ws"] = None


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

    await ws.accept()
    s["ws_clients"][student_id] = ws
    student = s["students"].get(student_id, {})
    if student:
        student["last_seen"] = now()
    log.info("Student %s connected: %s", student_id, session_code)

    # Build connected payload
    latest_delivery   = latest_delivery_for_student(s, student_id)
    current           = None
    current_delivery_id = ""
    task_idx          = -1

    if latest_delivery:
        current             = task_payload(s, latest_delivery)["task"]
        current_delivery_id = latest_delivery["id"]
        task_idx            = latest_delivery.get("task_index", -1)
    elif student.get("status") == "active":
        idx     = s["current_task_idx"]
        current = safe_task(s["tasks"][idx]) if 0 <= idx < len(s["tasks"]) else None
        task_idx = idx

    await ws_send(ws, {
        "type":                "connected",
        "role":                "student",
        "student":             student,
        "session_status":      s["status"],
        "current_task":        current,
        "groups":              s["groups"],
        "test_active":         s["test_state"]["active"],
        "current_delivery_id": current_delivery_id,
        "task_index":          task_idx,
        "total_tasks":         len(s["tasks"]),
    })

    if student.get("status") == "active":
        await replay_unacked_tasks(s, student_id)

    await ws_teacher(s, {
        "type":         "student_connected",
        "student_id":   student_id,
        "student_name": student.get("name", "?"),
    })

    try:
        while True:
            raw  = await ws.receive_text()
            data = json.loads(raw)
            cmd  = data.get("type", "")

            if cmd in ("ping", "heartbeat"):
                st = s["students"].get(student_id)
                if st:
                    st["last_seen"] = now()
                await ws_send(ws, {"type": "pong", "ts": now()})

            elif cmd == "quiz_submit":
                # ── Quiz submission handler ───────────────────────────────
                # Answers arrive as { task_id: answer_value, ... } keyed by
                # question id.  Stored under test_state["answers"][student_id]
                # so the teacher dashboard can read them later.
                answers: dict = data.get("answers") or {}
                student = s["students"].get(student_id)

                # Ensure storage bucket exists (safe for old sessions)
                ts = s.setdefault("test_state", {})
                ts.setdefault("answers", {})
                ts.setdefault("submitted", set())
                ts.setdefault("scores", {})

                ts["answers"][student_id] = {
                    "answers":      answers,
                    "submitted_at": now(),
                    "student_name": (student or {}).get("name", student_id),
                }
                ts["submitted"].add(student_id)

                # Basic scoring: compare against task correct_answer
                score = 0
                for task_id_key, ans_val in answers.items():
                    task = next(
                        (t for t in s.get("tasks", []) if t["id"] == task_id_key), None
                    )
                    if task and str(ans_val).strip() == str(task.get("correct_answer", "")).strip():
                        score += score_for(task)

                ts["scores"][student_id] = ts["scores"].get(student_id, 0) + score

                log.info(
                    "Quiz submitted by %s in session %s — %d answers, score %d",
                    student_id, session_code, len(answers), score,
                )

                # Acknowledge back to student
                await ws_send(ws, {
                    "type":    "quiz_submit_ack",
                    "score":   score,
                    "total":   len(answers),
                    "message": "Quiz submitted successfully! Great work.",
                })

                # Notify teacher
                await ws_teacher(s, {
                    "type":         "quiz_submitted",
                    "student_id":   student_id,
                    "student_name": (student or {}).get("name", student_id),
                    "answer_count": len(answers),
                    "score":        score,
                    "submitted_at": now(),
                })

            elif cmd == "task_received":
                delivery_id = data.get("delivery_id")
                if mark_task_ack(s, student_id, delivery_id):
                    await ws_teacher(s, {
                        "type":        "task_delivery_ack",
                        "delivery_id": delivery_id,
                        "task_id":     data.get("task_id", ""),
                        "student_id":  student_id,
                    })

    except WebSocketDisconnect:
        log.info("Student %s disconnected: %s", student_id, session_code)
    finally:
        if s.get("ws_clients", {}).get(student_id) is ws:
            s["ws_clients"].pop(student_id, None)
        await ws_teacher(s, {"type": "student_disconnected", "student_id": student_id})


# ── local dev ──────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
