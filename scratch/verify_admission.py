import sys
import os
import json
import csv
from io import BytesIO

# Adjust path to import main and store
sys.path.append(os.path.abspath(os.path.dirname(__file__) + "/.."))

from fastapi.testclient import TestClient
import store
import main

client = TestClient(main.app)

def run_tests():
    print("=== STARTING ADMISSION LOGIC TESTS ===")

    # 1. Create a session
    create_res = client.post("/api/session/create", json={"teacher_name": "Test Teacher", "session_name": "Test Session"})
    assert create_res.status_code == 200, f"Session creation failed: {create_res.text}"
    session_data = create_res.json()
    code = session_data["session_code"]
    print(f"Session created: {code}")

    # 2. Test OPEN ACCESS (no allowed list uploaded yet)
    print("Testing OPEN ACCESS...")
    join_res = client.post(f"/api/session/{code}/join?name=John%20Doe&roll=123&cls=Class%20A")
    assert join_res.status_code == 200, f"Failed to join in open access: {join_res.text}"
    student_id = join_res.json()["student_id"]
    print(f"Student joined in open access: {student_id}")

    # Leave session to clean up active roll / status
    leave_res = client.post(f"/api/session/{code}/student/{student_id}/leave")
    assert leave_res.status_code == 200, f"Leave failed: {leave_res.text}"
    print("Left open access student to reset state.")

    # 3. Upload allowed students CSV (Strict Mode ON)
    # Let's test flexible CSV parser with lowercase column names, spaces, and weird casing
    csv_content = """name,roll no,class
Arjun Mehta,  20BCE1001  ,  Class A  
Priya Sharma,20BCE1002,Class B
"""
    csv_bytes = csv_content.encode("utf-8")
    
    print("Uploading allowed students CSV...")
    upload_res = client.post(
        f"/api/session/{code}/upload_students",
        files={"file": ("students.csv", csv_bytes, "text/csv")}
    )
    assert upload_res.status_code == 200, f"Upload failed: {upload_res.text}"
    print(f"Upload response: {upload_res.json()}")
    assert upload_res.json()["loaded"] == 2

    # Verify session has allowed_students loaded
    s = store.get_session(code)
    assert s is not None
    assert len(s["allowed_students"]) == 2
    print(f"Allowed students set: {s['allowed_students']}")

    # 4. Test CLOSED ACCESS - Unauthorized student
    print("Testing CLOSED ACCESS: Unauthorized student...")
    unauth_res = client.post(f"/api/session/{code}/join?name=Unauthorized%20Student&roll=999&cls=Class%20C")
    assert unauth_res.status_code == 403, f"Expected 403, got {unauth_res.status_code}: {unauth_res.text}"
    assert unauth_res.json()["error"] == "Not allowed for this class"
    print("Blocked unauthorized student successfully.")

    # Ensure no record was created
    assert len(s["waiting_room"]) == 0
    # Wait, the previous open access student is in s["students"] but their status is "left". No new student was added.
    print("Verified no waiting room entries created for unauthorized student.")

    # 5. Test CLOSED ACCESS - Authorized student (matching casing)
    print("Testing CLOSED ACCESS: Authorized student with exact casing...")
    auth_res = client.post(f"/api/session/{code}/join?name=Arjun%20Mehta&roll=20BCE1001&cls=Class%20A")
    assert auth_res.status_code == 200, f"Authorized student failed to join: {auth_res.text}"
    auth_student_id = auth_res.json()["student_id"]
    print(f"Student joined successfully: {auth_student_id}")

    # Leave to reset active state
    client.post(f"/api/session/{code}/student/{auth_student_id}/leave")

    # 6. Test CLOSED ACCESS - Authorized student (different casing/spacing)
    print("Testing CLOSED ACCESS: Authorized student with different casing and spacing...")
    auth_res2 = client.post(f"/api/session/{code}/join?name=%20arjun%20%20mehta%20&roll=20bce1001&cls=class%20a")
    assert auth_res2.status_code == 200, f"Authorized student with different casing/spacing failed to join: {auth_res2.text}"
    auth_student_id2 = auth_res2.json()["student_id"]
    # Check that casing is preserved from CSV ("Arjun Mehta", "20BCE1001", "Class A")
    joined_student = s["students"][auth_student_id2]
    assert joined_student["name"] == "Arjun Mehta"
    assert joined_student["roll"] == "20BCE1001"
    assert joined_student["class"] == "Class A"
    print(f"Student joined with casing/spacing normalization: {auth_student_id2}. Preserved casing: {joined_student['name']}")

    # 7. Test CLOSED ACCESS - Duplicate Join check
    print("Testing CLOSED ACCESS: Duplicate Join check...")
    # Make the student active first (approve them)
    approve_res = client.post(f"/api/session/{code}/approve/{auth_student_id2}")
    assert approve_res.status_code == 200, f"Approve failed: {approve_res.text}"
    
    dup_res = client.post(f"/api/session/{code}/join?name=arjun%20mehta&roll=20bce1001&cls=class%20a")
    assert dup_res.status_code == 400, f"Expected 400, got: {dup_res.text}"
    assert "already joined in this class" in dup_res.json()["error"]
    print("Duplicate join blocked successfully.")

    # 8. Test serialization & deserialization of sets containing tuples (allowed_students)
    print("Testing serialization and deserialization of session state...")
    store.configure_persistence("json", "scratch/test_data")
    store.save_session(code)
    
    # Check that file was created and contains the serialized session
    session_file_path = f"scratch/test_data/session_{code}.json"
    assert os.path.exists(session_file_path), "Session file was not saved!"
    
    # Reload all sessions and verify no crash
    # Clear sessions in memory first to force reload
    store.sessions.clear()
    count = store.load_all_sessions()
    assert count == 1, "Failed to load session from disk!"
    
    reloaded_s = store.get_session(code)
    assert reloaded_s is not None
    assert len(reloaded_s["allowed_students"]) == 2
    # Verify that it is a set of tuples
    allowed_list = list(reloaded_s["allowed_students"])
    assert isinstance(reloaded_s["allowed_students"], set)
    assert isinstance(allowed_list[0], tuple)
    print("Serialization & deserialization worked flawlessly!")

    # Clean up test data files
    store.configure_persistence("none", "data")
    if os.path.exists(session_file_path):
        os.remove(session_file_path)
    if os.path.exists("scratch/test_data"):
        os.rmdir("scratch/test_data")

    print("=== ALL TESTS PASSED SUCCESSFULLY ===")

if __name__ == "__main__":
    run_tests()
