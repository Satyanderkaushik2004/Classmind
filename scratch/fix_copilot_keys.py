vyom_html_path = r"c:\Users\ADMIN\Downloads\Classmind-main\vyom.html"

with open(vyom_html_path, "r", encoding="utf-8") as f:
    content = f.read()

# Target 1: TeacherCopilot api_key retrieval
old_teacher_key_retrieval = """      const api_key = (() => { try { const user = JSON.parse(localStorage.getItem('cm_user')||'{}'); return user.apiKey || ''; } catch { return ''; } })();"""

new_teacher_key_retrieval = """      const api_key = localStorage.getItem('cm_teacher_saved_api_key') || localStorage.getItem('cm_openrouter_key') || localStorage.getItem('cm_gemini_key') || '';"""

# Target 2: StudentCopilotLight api_key retrieval
old_student_key_retrieval = """      const api_key = (() => { try { const user = JSON.parse(localStorage.getItem('cm_user')||'{}'); return user.apiKey || ''; } catch { return ''; } })();"""

new_student_key_retrieval = """      const api_key = localStorage.getItem('cm_teacher_saved_api_key') || localStorage.getItem('cm_openrouter_key') || localStorage.getItem('cm_gemini_key') || '';"""

def replace_exact(old_code, new_code):
    global content
    if old_code in content:
        content = content.replace(old_code, new_code)
        print("Replaced key retrieval block successfully.")
    else:
        # Normalize CRLF and spaces
        norm_old = old_code.replace("\r\n", "\n").strip()
        norm_content = content.replace("\r\n", "\n")
        if norm_old in norm_content:
            content = norm_content.replace(norm_old, new_code.replace("\r\n", "\n"))
            print("Replaced key retrieval block successfully after CRLF normalization.")
        else:
            print("Could not find key retrieval block to replace.")

# We want to replace only the first occurrence for teacher and second for student.
# Since the strings are identical, a simple string.replace() will replace all occurrences.
# Let's replace the identical string directly!
replace_exact(old_teacher_key_retrieval, new_teacher_key_retrieval)

with open(vyom_html_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Copilot API key fixes completed.")
