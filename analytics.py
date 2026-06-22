"""
analytics.py  —  VYOM analytics engine
Pure functions only — no FastAPI/WebSocket imports.
"""
from __future__ import annotations
import time
from typing import Dict, List, Optional


# ─────────────────────── HELPERS ─────────────────────────────────

def _effective_type(task: dict) -> str:
    """Return 'mcq', 'short', or 'long' for a task."""
    if task.get("long_answer"):
        return "long"
    return task.get("type", "mcq")  # 'mcq', 'short', 'coding'


def _is_approved(resp: dict, task: dict) -> bool:
    """A response counts toward analytics only when approved (or MCQ/coding)."""
    t = _effective_type(task)
    if t == "mcq" or task.get("type") == "coding":
        return True  # MCQ/coding are always instantly approved
    return resp.get("evaluation_status") == "approved"


# ─────────────────────── LIVE SNAPSHOT ───────────────────────────────

def get_participating_student_ids(session: dict) -> set[str]:
    """Returns a set of IDs of students who actually interacted with the session."""
    ids = set()

    # 1. Answered questions
    for sid, st in session.get("students", {}).items():
        if st.get("total_answered", 0) > 0 or st.get("coding_submitted"):
            ids.add(sid)

    # 2. Sent chat messages
    for msg in session.get("chat_messages", []):
        sid = msg.get("sender_id")
        if sid and sid != "teacher" and sid in session.get("students", {}):
            ids.add(sid)

    # 3. Submitted doubts
    for d in session.get("doubts", []):
        sid = d.get("student_id")
        if sid and sid in session.get("students", {}):
            ids.add(sid)

    return ids


def compute_analytics(
    session: dict,
    include_offline: bool = False,
    question_type: Optional[str] = None,
) -> dict:
    """
    Calculates session metrics.
    question_type: None = all, 'mcq', 'short', 'long'
    Short/Long answers only count AFTER evaluation_status == 'approved'.
    """
    participated_ids = get_participating_student_ids(session)
    students_list = list(session["students"].values())

    if not include_offline:
        students_list = [s for s in students_list if s["status"] == "active"]
    else:
        students_list = [s for s in students_list if s["id"] in participated_ids]

    total = len(students_list)
    if total == 0:
        return {
            "understanding": 0, "participation": 0,
            "at_risk": [], "topic_confusion": {},
            "total_students": 0, "answered": 0,
            "participated_count": 0,
        }

    all_joined_count = len(session.get("students", {}))
    participation = round((len(participated_ids) / all_joined_count) * 100) if all_joined_count > 0 else 0

    if len(participated_ids) == 0:
        participation = 0

    # Filter tasks by question_type
    tasks_in_scope = [
        t for t in session.get("tasks", [])
        if question_type is None or _effective_type(t) == question_type
    ]

    # Calculate understanding from approved answers only
    all_correct = 0
    all_answered = 0
    for task in tasks_in_scope:
        responses = session["responses"].get(task["id"], {})
        for sid, resp in responses.items():
            # Only count student if in scope
            if sid not in {s["id"] for s in students_list}:
                continue
            if not _is_approved(resp, task):
                continue
            all_answered += 1
            if resp.get("correct", False):
                all_correct += 1

    understanding = round((all_correct / all_answered) * 100) if all_answered > 0 else 0

    # At-risk: students with < 40% accuracy on approved answers
    at_risk = []
    for s in students_list:
        correct = 0
        answered = 0
        for task in tasks_in_scope:
            resp = session["responses"].get(task["id"], {}).get(s["id"])
            if resp and _is_approved(resp, task):
                answered += 1
                if resp.get("correct", False):
                    correct += 1
        if answered > 0 and (correct / answered) < 0.40:
            at_risk.append({"id": s["id"], "name": s["name"]})

    return {
        "understanding":   understanding,
        "participation":   participation,
        "at_risk":         at_risk,
        "topic_confusion": _topic_confusion(session, question_type),
        "total_students":  total,
        "answered":        len([s for s in students_list if s.get("total_answered", 0) > 0]),
        "participated_count": len(participated_ids),
    }


def _topic_confusion(session: dict, question_type: Optional[str] = None) -> Dict[str, dict]:
    result: Dict[str, dict] = {}
    for task in session["tasks"]:
        if question_type is not None and _effective_type(task) != question_type:
            continue
        topic       = task.get("topic", "General")
        correct_ans = task.get("correct_answer", "")
        responses   = session["responses"].get(task["id"], {})

        if topic not in result:
            result[topic] = {"wrong": 0, "total": 0}

        for r in responses.values():
            if not _is_approved(r, task):
                continue
            result[topic]["total"] += 1
            is_correct = r.get("correct", False) if _effective_type(task) in ("short", "long") else (r.get("answer") == correct_ans)
            if not is_correct:
                result[topic]["wrong"] += 1
    return result


# ─────────────────────── FULL REPORT ─────────────────────────────

def compute_report(session: dict) -> dict:
    """
    Full report — only called from Reports page, not pushed in real-time.
    Returns analytics broken down by question type (mcq, short, long).
    """
    _students = list(session["students"].values())
    coding_scores = [s.get("coding_score", 0) for s in _students if s.get("coding_submitted")]
    coding_avg = int(sum(coding_scores) / len(coding_scores)) if coding_scores else 0
    top_coder  = max(_students, key=lambda x: x.get("coding_score", 0), default=None)

    return {
        "session_code":   session["code"],
        "teacher_name":   session["teacher_name"],
        "session_name":   session.get("session_name", "Live Class"),
        "created_at":     session.get("created_at"),
        "duration_mins":  session.get("duration_mins", 0),
        "started_at":     session.get("started_at"),
        "analytics":      compute_analytics(session, include_offline=True),
        "analytics_mcq":  compute_analytics(session, include_offline=True, question_type="mcq"),
        "analytics_short": compute_analytics(session, include_offline=True, question_type="short"),
        "analytics_long": compute_analytics(session, include_offline=True, question_type="long"),
        "question_stats": _question_stats(session),
        "question_stats_mcq":   _question_stats(session, question_type="mcq"),
        "question_stats_short": _question_stats(session, question_type="short"),
        "question_stats_long":  _question_stats(session, question_type="long"),
        "group_stats":    _group_stats(session),
        "leaderboard":    session["test_state"].get("leaderboard", []),
        "total_tasks":    len(session["tasks"]),
        "duration_secs":  round(time.time() - (session.get("created_at") or time.time())),
        "status":         session["status"],
        "students":       _student_reports(session),
        "coding_summary": {
            "avg_score":  coding_avg,
            "top_coder":  top_coder,
        },
    }


def _question_stats(session: dict, question_type: Optional[str] = None) -> List[dict]:
    stats = []
    for i, task in enumerate(session["tasks"]):
        if question_type is not None and _effective_type(task) != question_type:
            continue

        responses   = session["responses"].get(task["id"], {})
        t_type      = _effective_type(task)
        is_open     = t_type in ("short", "long")

        # Only count approved responses for short/long
        approved_responses = {
            sid: r for sid, r in responses.items()
            if _is_approved(r, task)
        }

        total_resp  = len(approved_responses) if is_open else len(responses)
        correct_ans = task.get("correct_answer", "")

        if is_open:
            correct_cnt = sum(1 for r in approved_responses.values() if r.get("correct", False))
            # Also report pending count
            pending_cnt = sum(1 for r in responses.values() if r.get("evaluation_status") == "pending")
        else:
            correct_cnt = sum(1 for r in responses.values() if r.get("answer") == correct_ans)
            pending_cnt = 0

        option_freq: Dict[str, int] = {}
        if task.get("type") == "mcq":
            for r in responses.values():
                ans = r.get("answer", "?")
                option_freq[ans] = option_freq.get(ans, 0) + 1

        hint_reqs = sum(s.get("hint_requests", 0) for s in session["students"].values())

        stats.append({
            "index":           i + 1,
            "task_id":         task["id"],
            "question":        task.get("question", ""),
            "type":            t_type,
            "topic":           task.get("topic", ""),
            "difficulty":      task.get("difficulty", ""),
            "total_responses": total_resp,
            "pending_count":   pending_cnt,
            "correct":         correct_cnt,
            "accuracy":        round(correct_cnt / total_resp * 100) if total_resp else 0,
            "option_freq":     option_freq,
            "hint_requests":   hint_reqs,
            "max_marks":       task.get("max_marks"),
        })
    return stats


def _group_stats(session: dict) -> List[dict]:
    students = session["students"]
    stats    = []
    for g in session["groups"]:
        members  = [students[m] for m in g.get("members", []) if m in students]
        scores   = [m["score"]          for m in members]
        corrects = [m["correct"]        for m in members]
        answered = [m["total_answered"] for m in members]
        total_ans = sum(answered)
        stats.append({
            "id":        g["id"],
            "name":      g["name"],
            "members":   g.get("members", []),
            "avg_score": round(sum(scores) / len(scores)) if scores else 0,
            "accuracy":  round(sum(corrects) / total_ans * 100) if total_ans else 0,
            "participation": (
                round(len([m for m in members if m["total_answered"] > 0]) / len(members) * 100)
                if members else 0
            ),
        })
    return stats


def _student_reports(session: dict) -> List[dict]:
    result = []

    for sid, student in session["students"].items():
        mcq_attempts   = []
        short_attempts = []
        long_attempts  = []

        for task in session["tasks"]:
            task_id  = task["id"]
            response = session["responses"].get(task_id, {}).get(sid)
            if not response:
                continue

            t_type = _effective_type(task)
            is_approved = _is_approved(response, task)

            entry = {
                "question":          task.get("question", ""),
                "your_answer":       response.get("answer"),
                "correct_answer":    task.get("correct_answer"),
                "is_correct":        response.get("correct", False),
                "topic":             task.get("topic", ""),
                "evaluation_status": response.get("evaluation_status", "approved"),
                "teacher_score":     response.get("teacher_score"),
                "teacher_feedback":  response.get("teacher_feedback", ""),
                "ai_score":          response.get("ai_score"),
                "max_marks":         task.get("max_marks"),
            }

            if t_type == "mcq":
                mcq_attempts.append(entry)
            elif t_type == "long":
                if is_approved:
                    long_attempts.append(entry)
            else:  # short
                if is_approved:
                    short_attempts.append(entry)

        # MCQ stats (instant)
        mcq_correct = sum(1 for a in mcq_attempts if a["is_correct"])
        # Short stats (approved only)
        short_marks = sum((a["teacher_score"] or 0) for a in short_attempts)
        # Long stats (approved only)
        long_marks  = sum((a["teacher_score"] or 0) for a in long_attempts)

        result.append({
            "student_id":      sid,
            "name":            student.get("name"),
            # Real session-derived metrics passed to PDF
            "score":           student.get("score", 0),
            "joined_at":       student.get("joined_at", 0),
            "total_answered":  student.get("total_answered", 0),
            "warnings":        student.get("warnings", {}),
            # Legacy combined fields (backward compat)
            "total_attempts":  len(mcq_attempts) + len(short_attempts) + len(long_attempts),
            "correct":         mcq_correct,
            "attempts":        mcq_attempts + short_attempts + long_attempts,
            # Type-separated fields
            "mcq": {
                "attempts":   mcq_attempts,
                "correct":    mcq_correct,
                "total":      len(mcq_attempts),
                "accuracy":   round(mcq_correct / len(mcq_attempts) * 100) if mcq_attempts else 0,
            },
            "short": {
                "attempts":     short_attempts,
                "total":        len(short_attempts),
                "marks_earned": round(short_marks, 1),
            },
            "long": {
                "attempts":     long_attempts,
                "total":        len(long_attempts),
                "marks_earned": round(long_marks, 1),
            },
        })

    return result

