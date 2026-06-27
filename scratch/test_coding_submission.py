import os
import sys
import asyncio
from fastapi.testclient import TestClient

# Add workspace to path
sys.path.append(os.path.abspath(os.path.dirname(__file__) + '/..'))

from main import app, sessions
from store import new_session, new_student

client = TestClient(app)

async def async_test():
    # Let's create a session directly in the in-memory store
    session_code = "123456"
    s = new_session(session_code, "Test Teacher")
    s["status"] = "active"
    sessions[session_code] = s
    
    # Add a student
    student_id = "student1"
    student = new_student("Test Student")
    student["status"] = "active"
    s["students"][student_id] = student
    
    # 1. Create a coding task with:
    # Starter Code:
    # def sum_list(nums):
    #     pass
    # print(sum_list([1, 2, 3]))
    #
    # Reference Solution (correct_answer):
    # def sum_list(nums):
    #     return sum(nums)
    # print(sum_list([1, 2, 3]))
    
    task_payload = {
        "session_code": session_code,
        "question": "Write a function sum_list that sums a list",
        "type": "coding",
        "starter_code": "def sum_list(nums):\n    pass\n\nprint(sum_list([1, 2, 3]))",
        "correct_answer": "def sum_list(nums):\n    return sum(nums)\n\nprint(sum_list([1, 2, 3]))",
        "topic": "Math",
        "difficulty": "easy",
        "language": "python"
    }
    
    print("Creating task...")
    response = client.post("/api/tasks/create", json=task_payload)
    assert response.status_code == 200, f"Task creation failed: {response.text}"
    task = response.json()
    task_id = task["id"]
    print(f"Task created successfully with ID: {task_id}")
    
    # Deliver the task to the student (by adding it to deliveries or setting active)
    # The submission checks if the task was delivered. Let's make sure s["task_deliveries"] exists
    s["task_deliveries"] = {
        "d000001": {
            "id": "d000001",
            "task_id": task_id,
            "target_type": "all",
            "recipients": [student_id],
            "sent_to": [student_id],
            "sequence": 1
        }
    }
    
    # 2. Student submits a correct solution but with a different approach (e.g. using a loop instead of sum()):
    # def sum_list(nums):
    #     total = 0
    #     for x in nums:
    #         total += x
    #     return total
    # print(sum_list([1, 2, 3]))
    #
    # This output matches the reference solution output (6), but approach is different!
    correct_solution = "def sum_list(nums):\n    total = 0\n    for x in nums:\n        total += x\n    return total\n\nprint(sum_list([1, 2, 3]))"
    
    print("\n--- Submitting correct student solution with different approach ---")
    submit_payload = {
        "session_code": session_code,
        "student_id": student_id,
        "task_id": task_id,
        "answer": correct_solution,
        "time_taken": 10.0
    }
    
    response = client.post("/api/responses/submit", json=submit_payload)
    print("Submission response status:", response.status_code)
    print("Submission response JSON:", response.json())
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["correct"] is True, "Student correct solution was marked as WRONG!"
    print("SUCCESS: Student correct solution with different approach was marked CORRECT!")
    
    # 3. Student submits an incorrect solution (wrong output)
    # def sum_list(nums):
    #     return sum(nums) + 1
    # print(sum_list([1, 2, 3]))
    incorrect_solution = "def sum_list(nums):\n    return sum(nums) + 1\n\nprint(sum_list([1, 2, 3]))"
    print("\n--- Submitting incorrect student solution ---")
    submit_payload["answer"] = incorrect_solution
    
    response = client.post("/api/responses/submit", json=submit_payload)
    print("Submission response JSON:", response.json())
    assert response.status_code == 200
    res_data = response.json()
    assert res_data["correct"] is False, "Student incorrect solution was marked as CORRECT!"
    print("SUCCESS: Student incorrect solution was marked INCORRECT!")

if __name__ == "__main__":
    # TestClient context manager handles lifespan
    with TestClient(app) as test_client:
        client = test_client
        # Run async test using loop
        loop = asyncio.get_event_loop()
        loop.run_until_complete(async_test())
