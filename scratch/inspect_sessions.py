import sys
import os

# Add current dir to path
sys.path.append(os.getcwd())

from store import sessions, load_all_sessions, configure_persistence

# Mock env
os.environ["DATA_DIR"] = "data"
configure_persistence("json", "data")
load_all_sessions()

print(f"Total sessions in store: {len(sessions)}")
for code, s in sessions.items():
    print(f"Code: {code} | TeacherID: {s.get('teacher_id')} | TeacherEmail: {s.get('teacher_email')} | Name: {s.get('teacher_name')}")
