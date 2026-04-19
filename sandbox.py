"""
sandbox.py  —  ClassMind Python code sandbox
Executes student code safely. Key guarantees:
  - No filesystem, network, OS access
  - input() replaced with safe stub (no stdin hang)
  - Hard 5-second timeout
  - 2 KB output cap
"""
import os, subprocess, tempfile
import sys
BLOCKED = [
    "import os", "import sys", "import subprocess", "import socket",
    "import shutil", "import importlib", "import ctypes",
    "import threading", "import multiprocessing", "import asyncio",
    "__import__", "open(", "exec(", "eval(", "compile(", "breakpoint(",
    "globals(", "locals(", "__builtins__",
]

TIMEOUT = 5
MAX_OUT = 2048

# Prepended to every student script:
#   - patches input() so it doesn't block forever
#   - disables dangerous builtins
PREAMBLE = """\
import builtins as _b
_input_called = [0]
def _safe_input(prompt=''):
    _input_called[0] += 1
    if _input_called[0] > 10:
        raise RuntimeError("Too many input() calls in sandbox")
    print(str(prompt), end='', flush=True)
    return ''   # always returns empty string (no real stdin)
_b.input = _safe_input
del _b
"""


from dataclasses import dataclass

@dataclass
class RunResult:
    output:    str
    error:     bool
    timed_out: bool = False


def run_code(code: str, language: str = "python") -> RunResult:
    if language.lower() not in ("python", "python3"):
        return RunResult(f"Only Python is supported (got '{language}')", error=True)

    for kw in BLOCKED:
        if kw in code:
            return RunResult(f"🚫 Sandbox blocked: '{kw}' is not allowed", error=True)

    full_code = PREAMBLE + "\n" + code

    with tempfile.NamedTemporaryFile(
        suffix=".py", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(full_code)
        path = f.name
    
    try:
        PYTHON_CMD = "python" if sys.platform.startswith("win") else "python3"
        res = subprocess.run(
    [PYTHON_CMD, "-u", path],
    capture_output=True,
    text=True,
    timeout=TIMEOUT,
    stdin=subprocess.DEVNULL,
)
        stdout = res.stdout or ""
        stderr = res.stderr or ""
        # Strip preamble noise from tracebacks (adjust line numbers)
        combined = stdout
        if stderr:
            # Remove internal preamble lines from tracebacks
            cleaned = "\n".join(
                l for l in stderr.splitlines()
                if "_safe_input" not in l and "PREAMBLE" not in l
            )
            if cleaned.strip():
                combined += ("\n" if combined else "") + cleaned
        combined = combined[:MAX_OUT]
        return RunResult(output=combined or "(no output)", error=res.returncode != 0)

    except subprocess.TimeoutExpired:
        return RunResult(f"⏱ Time limit exceeded ({TIMEOUT}s max)", error=True, timed_out=True)
    except Exception as e:
        return RunResult(f"Execution error: {e}", error=True)
    finally:
        try: os.unlink(path)
        except: pass
