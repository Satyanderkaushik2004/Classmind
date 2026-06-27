import requests
import json

base_url = "http://localhost:8003"
session_code = "373241" # Loaded from persistence
test_email = "satyanderkaushik2004@gmail.com"

print(f"Testing reports API endpoints for session {session_code}...")

# 1. Test gradebook API
r = requests.get(f"{base_url}/api/session/{session_code}/reports/gradebook")
print(f"Gradebook API status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"Gradebook keys: {list(data.keys())}")
    print(f"Students count: {len(data.get('gradebook', []))}")
    print(f"Sample student: {data.get('gradebook', [])[0] if data.get('gradebook') else 'None'}")
else:
    print(f"Response: {r.text}")

# 2. Test tests API
r = requests.get(f"{base_url}/api/session/{session_code}/reports/tests")
print(f"Tests API status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"Tests stats: {data.get('stats')}")
    print(f"Tests student reports: {len(data.get('report', []))}")

# 3. Test coding API
r = requests.get(f"{base_url}/api/session/{session_code}/reports/coding")
print(f"Coding API status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"Has coding: {data.get('has_coding')}")
    if data.get('has_coding'):
        print(f"Coding task info: {data.get('task')}")
        print(f"Coding student reports: {len(data.get('report', []))}")

# 4. Test PDF download
r = requests.get(f"{base_url}/api/session/{session_code}/reports/download?type=gradebook&format=pdf")
print(f"Gradebook PDF download status: {r.status_code}")
if r.status_code == 200:
    print(f"Gradebook PDF size: {len(r.content)} bytes")
    # Verify PDF signature
    if r.content.startswith(b"%PDF"):
        print("Gradebook PDF header verification: PASSED")
    else:
        print("Gradebook PDF header verification: FAILED")

# 5. Test Excel download
r = requests.get(f"{base_url}/api/session/{session_code}/reports/download?type=gradebook&format=excel")
print(f"Gradebook Excel download status: {r.status_code}")
if r.status_code == 200:
    print(f"Gradebook Excel size: {len(r.content)} bytes")

# 6. Test CSV download
r = requests.get(f"{base_url}/api/session/{session_code}/reports/download?type=gradebook&format=csv")
print(f"Gradebook CSV download status: {r.status_code}")
if r.status_code == 200:
    print(f"Gradebook CSV size: {len(r.content)} bytes")
    print(f"CSV snippet: {r.text[:200]}")

# 7. Test Save to Google Drive
headers = {
    "X-User-Email": test_email,
    "X-User-Role": "teacher"
}
print(f"Testing Save to Google Drive for {test_email}...")
r = requests.post(f"{base_url}/api/session/{session_code}/reports/save-gdrive?type=gradebook&format=pdf", headers=headers)
print(f"Save to Google Drive status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"Save to GDrive success response: {data}")
else:
    print(f"Save to GDrive failed response: {r.text}")
