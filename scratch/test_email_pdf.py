import asyncio
import sys
import os

# Ensure project root is in python path
sys.path.append(os.getcwd())

from email_service import send_session_email

mock_report = {
    "teacher_name": "Dr. Rajesh Kumar",
    "session_name": "Machine Learning Basics",
    "session_code": "ML-4587",
    "created_at": 1718870400,
    "duration_mins": 95,
    "total_tasks": 4,
    "analytics": {
        "total_students": 58,
        "understanding": 92,
        "participation": 92,
    },
    "students": [
        {"name": "Aman Sharma"},
        {"name": "Priya Verma"},
        {"name": "Rohit Gupta"}
    ]
}

async def main():
    print("Testing send_session_email...")
    ok, msg = await send_session_email("teacher@vyom.app", mock_report, "Dr. Rajesh Kumar")
    print("Result ok/fail:", ok)
    print("Result message:", msg)

if __name__ == '__main__':
    asyncio.run(main())
