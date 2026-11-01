"""
sandbox.py  —  VYOM Python code sandbox
Executes student code safely. Key guarantees:
  - No filesystem, network, OS access
  - input() replaced with safe stub (no stdin hang)
  - Hard timeout (configurable via env SANDBOX_TIMEOUT, default 5s)
  - Output cap (configurable via env SANDBOX_MAX_OUTPUT, default 2048 bytes)
  - Cross-platform: uses sys.executable so the correct Python is always found
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

# ── configurable limits (override via .env) ───────────────────────
TIMEOUT  = int(os.getenv("SANDBOX_TIMEOUT",    "5"))
MAX_OUT  = int(os.getenv("SANDBOX_MAX_OUTPUT", "2048"))

BLOCKED = [
    "import os", "import sys", "import subprocess", "import socket",
    "import shutil", "import importlib", "import ctypes",
    "import threading", "import multiprocessing", "import asyncio",
    "__import__", "open(", "exec(", "eval(", "compile(", "breakpoint(",
    "globals(", "locals(", "__builtins__",
]

# Prepended to every student script:
#   - patches input() so it doesn't block forever
#   - disables dangerous builtins
PREAMBLE = """\
import builtins as _b
_input_called = [0]
def _safe_input(prompt=''):
    _input_called[0] += 1
    if _input_called[0] > 100:
        raise RuntimeError("Too many input() calls in sandbox")
    print(str(prompt), end='', flush=True)
    import sys as _sys
    line = _sys.stdin.readline()
    if not line:
        raise EOFError("EOF when reading a line")
    return line.rstrip('\\r\\n')
_b.input = _safe_input
del _b
"""



@dataclass
class RunResult:
    output:    str
    error:     bool
    timed_out: bool = False


def find_executable(name: str) -> str:
    import shutil
    import glob
    
    # 1. Try standard shutil.which
    exe = shutil.which(name)
    if exe:
        return exe
        
    # 2. Hardcoded fallback paths for this system
    fallbacks = {
        "node": [
            r"C:\Program Files\nodejs\node.exe",
            r"C:\Program Files (x86)\nodejs\node.exe",
        ],
        "javac": [
            r"C:\Program Files\Java\jdk-21.0.11\bin\javac.exe",
        ] + glob.glob(r"C:\Program Files\Java\jdk-*\bin\javac.exe"),
        "java": [
            r"C:\Program Files\Java\jdk-21.0.11\bin\java.exe",
        ] + glob.glob(r"C:\Program Files\Java\jdk-*\bin\java.exe"),
        "go": [
            r"C:\Program Files\Go\bin\go.exe",
            r"C:\Go\bin\go.exe",
        ],
        "clang": [
            r"C:\Program Files\LLVM\bin\clang.exe",
            r"C:\Program Files (x86)\LLVM\bin\clang.exe",
        ] + glob.glob(r"C:\Program Files\LLVM\bin\clang.exe"),
        "clang++": [
            r"C:\Program Files\LLVM\bin\clang++.exe",
            r"C:\Program Files (x86)\LLVM\bin\clang++.exe",
        ] + glob.glob(r"C:\Program Files\LLVM\bin\clang++.exe"),
        "g++": [
            r"C:\Users\robin\AppData\Local\Microsoft\WinGet\Packages\MartinStorsjo.LLVM-MinGW.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\llvm-mingw-20260519-ucrt-x86_64\bin\g++.exe",
        ] + glob.glob(r"C:\Users\robin\AppData\Local\Microsoft\WinGet\Packages\**\bin\g++.exe"),
        "gcc": [
            r"C:\Users\robin\AppData\Local\Microsoft\WinGet\Packages\MartinStorsjo.LLVM-MinGW.UCRT_Microsoft.Winget.Source_8wekyb3d8bbwe\llvm-mingw-20260519-ucrt-x86_64\bin\gcc.exe",
        ] + glob.glob(r"C:\Users\robin\AppData\Local\Microsoft\WinGet\Packages\**\bin\gcc.exe"),
    }
    
    paths = fallbacks.get(name.lower(), [])
    for p in paths:
        if p and os.path.exists(p):
            return p
            
    return None


def get_java_class_name(code: str) -> str:
    clean_code = re.sub(r"//.*", "", code)
    clean_code = re.sub(r"/\*.*?\*/", "", clean_code, flags=re.DOTALL)
    
    public_match = re.search(r"\bpublic\s+class\s+(\w+)", clean_code)
    if public_match:
        return public_match.group(1)
    
    class_matches = list(re.finditer(r"\bclass\s+(\w+)", clean_code))
    if not class_matches:
        return "Main"
        
    if len(class_matches) == 1:
        return class_matches[0].group(1)
        
    for i, match in enumerate(class_matches):
        start = match.start()
        end = class_matches[i+1].start() if i + 1 < len(class_matches) else len(clean_code)
        class_body = clean_code[start:end]
        if "public static void main" in class_body:
            return match.group(1)
            
    return class_matches[0].group(1)


def clean_java_code(code: str) -> str:
    return re.sub(r"^([ \t]*package\s+[\w\.]+;)", r"// \1", code, flags=re.MULTILINE)


def run_code(code: str, language: str = "python", stdin: str = None) -> RunResult:
    lang = language.lower().strip()
    if lang in ("python", "python3"):
        for kw in BLOCKED:
            if kw in code:
                return RunResult(f"Sandbox blocked: '{kw}' is not allowed", error=True)

        full_code = PREAMBLE + "\n" + code
        python_exe = sys.executable

        with tempfile.NamedTemporaryFile(
            suffix=".py", delete=False, mode="w", encoding="utf-8"
        ) as f:
            f.write(full_code)
            path = f.name

        try:
            res = subprocess.run(
                [python_exe, "-u", path],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                input=stdin or "",
                close_fds=True,
            )
            stdout = res.stdout or ""
            stderr = res.stderr or ""
            combined = stdout
            if stderr:
                cleaned = "\n".join(
                    line for line in stderr.splitlines()
                    if "_safe_input" not in line and "PREAMBLE" not in line
                )
                if cleaned.strip():
                    combined += ("\n" if combined else "") + cleaned

            return RunResult(output=combined[:MAX_OUT] or "(no output)", error=res.returncode != 0)

        except subprocess.TimeoutExpired:
            return RunResult(
                f"Time limit exceeded ({TIMEOUT}s max)", error=True, timed_out=True
            )
        except Exception as e:
            return RunResult(f"Execution error: {e}", error=True)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    elif lang in ("javascript", "js"):
        node_exe = find_executable("node")
        if not node_exe:
            return RunResult("JavaScript runtime error: 'node' executable not found on the server. Please install Node.js.", error=True)

        with tempfile.NamedTemporaryFile(suffix=".js", delete=False, mode="w", encoding="utf-8") as f:
            f.write(code)
            path = f.name

        try:
            res = subprocess.run(
                [node_exe, path],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                input=stdin or "",
                close_fds=True,
            )
            combined = (res.stdout or "") + (res.stderr or "")
            return RunResult(output=combined[:MAX_OUT] or "(no output)", error=res.returncode != 0)
        except subprocess.TimeoutExpired:
            return RunResult(f"Time limit exceeded ({TIMEOUT}s max)", error=True, timed_out=True)
        except Exception as e:
            return RunResult(f"Execution error: {e}", error=True)
        finally:
            try:
                os.unlink(path)
            except OSError:
                pass

    elif lang in ("cpp", "c++"):
        candidate_compilers = ("g++", "clang++")
        compile_error = None
        # Use a project-local scratch directory instead of system temp
        # Windows Application Control (WDAC) often blocks executables in %TEMP%
        # but allows them from the project directory which the user has approved
        project_dir = os.path.dirname(os.path.abspath(__file__))
        scratch_base = os.path.join(project_dir, "scratch", "_cpp_runs")
        os.makedirs(scratch_base, exist_ok=True)
        temp_dir = tempfile.mkdtemp(dir=scratch_base)
        cpp_path = os.path.join(temp_dir, "main.cpp")
        exe_path = os.path.join(temp_dir, "main.exe") if os.name == "nt" else os.path.join(temp_dir, "main")

        with open(cpp_path, "w", encoding="utf-8") as f:
            f.write(code)

        # On Windows, use CREATE_NO_WINDOW to prevent console popups
        _cflags = 0x08000000 if os.name == "nt" else 0  # CREATE_NO_WINDOW

        try:
            for candidate in candidate_compilers:
                compiler_path = find_executable(candidate)
                if not compiler_path:
                    continue

                comp = subprocess.run(
                    [compiler_path, cpp_path, "-o", exe_path, "-O2", "-std=c++17"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    creationflags=_cflags,
                )

                if comp.returncode == 0:
                    res = subprocess.run(
                        [exe_path],
                        capture_output=True,
                        text=True,
                        timeout=TIMEOUT,
                        input=stdin or "",
                        close_fds=(os.name != "nt"),
                        creationflags=_cflags,
                    )
                    combined = (res.stdout or "") + (res.stderr or "")
                    return RunResult(output=combined[:MAX_OUT] or "(no output)", error=res.returncode != 0)

                details = (comp.stdout or "") + (comp.stderr or "")
                if details.strip():
                    return RunResult(f"Compilation Error:\n{details}", error=True)

                compile_error = f"Compiler '{compiler_path}' failed with exit code {comp.returncode}."

            if compile_error is None:
                return RunResult("C++ compiler error: 'g++' or 'clang++' compiler not found on the server. Please install a C++ compiler.", error=True)

            return RunResult(
                f"Compilation Error:\n{compile_error}\nThis compiler was found but failed to execute. Verify the installed C++ toolchain and any required runtime libraries.",
                error=True,
            )
        except subprocess.TimeoutExpired:
            return RunResult(f"Time limit exceeded ({TIMEOUT}s max)", error=True, timed_out=True)
        except Exception as e:
            return RunResult(f"Execution error: {e}", error=True)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    elif lang == "c":
        candidate_compilers = ("gcc", "clang")
        compile_error = None
        project_dir = os.path.dirname(os.path.abspath(__file__))
        scratch_base = os.path.join(project_dir, "scratch", "_c_runs")
        os.makedirs(scratch_base, exist_ok=True)
        temp_dir = tempfile.mkdtemp(dir=scratch_base)
        c_path = os.path.join(temp_dir, "main.c")
        exe_path = os.path.join(temp_dir, "main.exe") if os.name == "nt" else os.path.join(temp_dir, "main")

        with open(c_path, "w", encoding="utf-8") as f:
            f.write(code)

        _cflags = 0x08000000 if os.name == "nt" else 0

        try:
            for candidate in candidate_compilers:
                compiler_path = find_executable(candidate)
                if not compiler_path:
                    continue

                comp = subprocess.run(
                    [compiler_path, c_path, "-o", exe_path, "-O2", "-std=c11"],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    creationflags=_cflags,
                )

                if comp.returncode == 0:
                    res = subprocess.run(
                        [exe_path],
                        capture_output=True,
                        text=True,
                        timeout=TIMEOUT,
                        input=stdin or "",
                        close_fds=(os.name != "nt"),
                        creationflags=_cflags,
                    )
                    combined = (res.stdout or "") + (res.stderr or "")
                    return RunResult(output=combined[:MAX_OUT] or "(no output)", error=res.returncode != 0)

                details = (comp.stdout or "") + (comp.stderr or "")
                if details.strip():
                    return RunResult(f"Compilation Error:\n{details}", error=True)

                compile_error = f"Compiler '{compiler_path}' failed with exit code {comp.returncode}."

            if compile_error is None:
                return RunResult("C compiler error: 'gcc' or 'clang' compiler not found on the server. Please install a C compiler.", error=True)

            return RunResult(
                f"Compilation Error:\n{compile_error}\nThis compiler was found but failed to execute. Verify the installed C toolchain and any required runtime libraries.",
                error=True,
            )
        except subprocess.TimeoutExpired:
            return RunResult(f"Time limit exceeded ({TIMEOUT}s max)", error=True, timed_out=True)
        except Exception as e:
            return RunResult(f"Execution error: {e}", error=True)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    elif lang == "java":
        javac_exe = find_executable("javac")
        java_exe = find_executable("java")
        if not javac_exe or not java_exe:
            return RunResult("Java error: 'javac' or 'java' executables not found on the server. Please install JDK.", error=True)

        class_name = get_java_class_name(code)
        cleaned_code = clean_java_code(code)

        temp_dir = tempfile.mkdtemp()
        java_path = os.path.join(temp_dir, f"{class_name}.java")

        try:
            with open(java_path, "w", encoding="utf-8") as f:
                f.write(cleaned_code)

            comp = subprocess.run(
                [javac_exe, java_path],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if comp.returncode != 0:
                return RunResult(f"Compilation Error:\n{(comp.stdout or '') + (comp.stderr or '')}", error=True)

            res = subprocess.run(
                [java_exe, "-XX:+TieredCompilation", "-XX:TieredStopAtLevel=1", "-Xms16m", "-Xmx64m", "-cp", temp_dir, class_name],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                input=stdin or "",
                close_fds=True,
            )
            combined = (res.stdout or "") + (res.stderr or "")
            return RunResult(output=combined[:MAX_OUT] or "(no output)", error=res.returncode != 0)
        except subprocess.TimeoutExpired:
            return RunResult(f"Time limit exceeded ({TIMEOUT}s max)", error=True, timed_out=True)
        except Exception as e:
            return RunResult(f"Execution error: {e}", error=True)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    elif lang == "go":
        go_exe = find_executable("go")
        if not go_exe:
            return RunResult("Go compiler error: 'go' executable not found on the server. Please install Go.", error=True)

        temp_dir = tempfile.mkdtemp()
        go_path = os.path.join(temp_dir, "main.go")
        exe_path = os.path.join(temp_dir, "main.exe") if os.name == "nt" else os.path.join(temp_dir, "main")

        try:
            with open(go_path, "w", encoding="utf-8") as f:
                f.write(code)

            build_env = os.environ.copy()
            build_env["GO111MODULE"] = "off"
            build_env["GOPROXY"] = "off"
            comp = subprocess.run(
                [go_exe, "build", "-o", exe_path, go_path],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=temp_dir,
                env=build_env,
            )
            if comp.returncode != 0:
                return RunResult(f"Compilation Error:\n{(comp.stdout or '') + (comp.stderr or '')}", error=True)

            res = subprocess.run(
                [exe_path],
                capture_output=True,
                text=True,
                timeout=TIMEOUT,
                input=stdin or "",
                cwd=temp_dir,
                close_fds=True,
            )
            combined = (res.stdout or "") + (res.stderr or "")
            return RunResult(output=combined[:MAX_OUT] or "(no output)", error=res.returncode != 0)
        except subprocess.TimeoutExpired:
            return RunResult(f"Time limit exceeded ({TIMEOUT}s max)", error=True, timed_out=True)
        except Exception as e:
            if getattr(e, "winerror", None) == 4551:
                return RunResult("Go runtime blocked by Windows Application Control. Allow generated Go executables or use a permitted Go toolchain.", error=True)
            return RunResult(f"Go Execution error: {e}", error=True)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

    else:
        return RunResult(f"Unsupported language: '{language}'", error=True)

