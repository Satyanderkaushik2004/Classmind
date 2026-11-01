import sys
import os
import traceback

os.chdir(os.path.dirname(os.path.abspath(__file__)))
print("Starting VYOM server on http://0.0.0.0:8000 ...", flush=True)

try:
    import uvicorn
    import main
    print("main imported successfully, starting uvicorn...", flush=True)
    uvicorn.run(main.app, host="0.0.0.0", port=8000, log_level="info")
except Exception as e:
    traceback.print_exc(file=sys.stdout)
    sys.stdout.flush()
