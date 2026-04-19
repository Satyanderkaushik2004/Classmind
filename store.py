"""
store.py  —  ClassMind in-memory data store
All session state lives here. Structure is Redis-ready (flat dicts).
"""
import time, uuid, random, string
from typing import Dict

# ── global store ──────────────────────────────────────────────────
sessions: Dict[str, dict] = {}   # session_code -> session dict

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

# ── session factory ───────────────────────────────────────────────
def new_session(code: str, teacher_name: str) -> dict:
    return {
        "code":             code,
        "teacher_name":     teacher_name,
        "status":           "waiting",   # waiting|active|paused|ended
        "mode":             "live",      # live|test
        "created_at":       now(),
        # websockets
        "teacher_ws":       None,
        "ws_clients":       {},          # student_id -> WebSocket
        # roster
        "students":         {},          # student_id -> student dict
        "waiting_room":     [],          # [student_id, ...]
        "kicked":           set(),
        "allowed_students": set(),        # optional CSV admission list
        "active_rolls":     set(),        # duplicate login guard
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
        "raised_hands":     [],
        # content
        "content_files":    {},          # filename -> {name,data,content_type,size}
        "quiz":             None,
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
        "allowed_students": set(),   # (name, roll, class)
        "active_rolls": set(), 
        # prevent duplicate joins
        # ── coding analytics (Feature 1) ──────────────────────────────
        "coding_score":       0,
        "coding_submitted":   False,
        "test_cases_passed":  0,
        "total_test_cases":   0,
        "coding_time_taken":  0,
    }

# ── task factory ──────────────────────────────────────────────────
def new_task(d: dict) -> dict:
    return {
        "id":              gen_id("t"),
        "question":        d.get("question", ""),
        "type":            d.get("type", "mcq"),         # mcq|short|coding
        "options":         d.get("options", []),
        "correct_answer":  d.get("correct_answer", d.get("answer", "")),
        "topic":           d.get("topic", "General"),
        "difficulty":      d.get("difficulty", "medium"),
        "hint":            d.get("hint"),
        "hint_visibility": d.get("hint_visibility", "on_request"),
        "time_limit":      d.get("time_limit"),
        "long_answer":     bool(d.get("long_answer", False)),
        "content_file":    d.get("content_file"),
        "created_at":      now(),
    }

# ── helpers ───────────────────────────────────────────────────────
DIFF_SCORE = {"easy": 5, "medium": 10, "hard": 20}

def score_for(task: dict) -> int:
    return DIFF_SCORE.get(task.get("difficulty", "medium"), 10)

def safe_task(task: dict) -> dict:
    """Strip correct_answer and hide hint unless visibility=always."""
    t = {k: v for k, v in task.items() if k != "correct_answer"}
    t["id"] = str(t.get("id") or "")
    t["question"] = str(t.get("question") or "")
    t["type"] = str(t.get("type") or "mcq")
    t["options"] = t.get("options") or []
    t["topic"] = str(t.get("topic") or "General")
    t["difficulty"] = str(t.get("difficulty") or "medium")
    t["hint_visibility"] = str(t.get("hint_visibility") or "on_request")
    if t.get("hint_visibility") != "always":
        t["hint"] = None
    return t

def get_session(code: str):
    """Return session or None."""
    return sessions.get(code)
