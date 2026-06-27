import urllib.request
import json
import sys

base_url = "http://127.0.0.1:8003"

def make_request(path, method="GET", headers=None, data=None):
    if headers is None:
        headers = {}
    
    # Let's add teacher user headers
    headers["X-User-Email"] = "teacher@classmind.com"
    headers["X-User-Role"] = "teacher"
    
    url = f"{base_url}{path}"
    req = urllib.request.Request(url, headers=headers, method=method)
    
    if data is not None:
        if isinstance(data, dict):
            req.add_header("Content-Type", "application/json")
            data = json.dumps(data).encode("utf-8")
        req.data = data
        
    try:
        with urllib.request.urlopen(req) as response:
            status = response.status
            body = response.read()
            return status, body
    except urllib.error.HTTPError as e:
        return e.code, e.read()
    except Exception as e:
        return 999, str(e).encode("utf-8")

print("--- TESTING DOWNLOADS API ---")

# 1. Fetch current downloads list
status, body = make_request("/api/teacher/downloads")
print(f"GET /api/teacher/downloads: Status {status}")
if status == 200:
    res = json.loads(body.decode("utf-8"))
    print(f"Reports list count: {len(res.get('reports', []))}")
    reports = res.get('reports', [])
    for r in reports[:3]:
        print(f" - Report: ID={r.get('id')}, Name={r.get('name')}, Category={r.get('category')}")
else:
    print(f"Failed: {body.decode('utf-8')}")
    sys.exit(1)

# 2. Let's try downloading the first report if one exists
if reports:
    first_report = reports[0]
    report_id = first_report["id"]
    print(f"\nDownloading PDF for report {report_id}...")
    status, pdf_body = make_request(f"/api/teacher/downloads/{report_id}/download?format=pdf")
    print(f"GET /api/teacher/downloads/{report_id}/download?format=pdf: Status {status}")
    if status == 200:
        print(f"Received PDF, size: {len(pdf_body)} bytes")
        if pdf_body.startswith(b"%PDF"):
            print("Successfully verified PDF header (%PDF)!")
        else:
            print("WARNING: Response does not start with %PDF")
    else:
        print(f"Failed: {pdf_body.decode('utf-8')}")

    print(f"\nDownloading Excel/CSV for report {report_id}...")
    status, excel_body = make_request(f"/api/teacher/downloads/{report_id}/download?format=excel")
    print(f"GET /api/teacher/downloads/{report_id}/download?format=excel: Status {status}")
    if status == 200:
        print(f"Received Excel, size: {len(excel_body)} bytes")
    else:
        print(f"Failed: {excel_body.decode('utf-8')}")

print("\n--- ALL TESTS COMPLETED ---")
