
import json
import os
from store import sessions

session_code = "451540"
if session_code in sessions:
    s = sessions[session_code]
    # Filter out large fields like 'tasks' content if needed, but let's see counts
    summary = {
        "code": s.get("code"),
        "students_count": len(s.get("students", {})),
        "participating_students": [sid for sid, st in s.get("students", {}).items() if st.get("total_answered", 0) > 0],
        "chat_messages_count": len(s.get("chat_messages", [])),
        "doubts_count": len(s.get("doubts", [])),
        "task_deliveries_count": len(s.get("task_deliveries", {})),
        "tasks_count": len(s.get("tasks", [])),
    }
    print(json.dumps(summary, indent=2))
else:
    print(f"Session {session_code} not found in memory.")
