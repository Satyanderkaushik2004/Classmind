"""
email_service.py  ─  VYOM Session Report Email System (SendGrid API Version)
Sends async emails via SendGrid Web API with anti-spam optimizations.
"""
import logging
import os
import re
import asyncio
import time
from datetime import datetime
from typing import Dict, Optional, Tuple, List

from dotenv import load_dotenv

# Load environment variables early
load_dotenv()

# Third-party imports
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content, Header
except ImportError:
    SendGridAPIClient = None
    Mail = None

log = logging.getLogger("vyom.email")

# ── Configuration ─────────────────────────────────────────────────
DEFAULT_FROM_EMAIL = "support@vyom.com"

# ── Email validation ──────────────────────────────────────────────
EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

def is_valid_email(email: str) -> bool:
    """Validate email format."""
    if not email: return False
    return bool(EMAIL_REGEX.match(email.strip()))

def validate_smtp_config() -> bool:
    """Check if SendGrid API key or standard SMTP credentials are configured."""
    has_sendgrid = bool(os.getenv("SENDGRID_API_KEY", "").strip())
    has_smtp = bool(os.getenv("EMAIL_ADDRESS", "").strip()) and bool(os.getenv("EMAIL_PASSWORD", "").strip())
    return has_sendgrid or has_smtp

async def verify_smtp_credentials() -> Tuple[bool, str]:
    """Verify SMTP or SendGrid credentials by logging in or checking key existence."""
    api_key = os.getenv("SENDGRID_API_KEY", "").strip()
    email_address = os.getenv("EMAIL_ADDRESS", "").strip()
    email_password = os.getenv("EMAIL_PASSWORD", "").strip()

    if api_key:
        if SendGridAPIClient is None:
            return False, "SendGrid library not installed"
        try:
            if len(api_key) < 10:
                return False, "SendGrid API Key is too short or invalid"
            return True, "SendGrid configuration verified"
        except Exception as e:
            return False, f"SendGrid validation failed: {str(e)}"

    if email_address and email_password:
        try:
            import aiosmtplib
            SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
            SMTP_PORT = int(os.getenv("SMTP_PORT", "587").strip())

            ports_to_try = [SMTP_PORT]
            if SMTP_PORT == 587:
                ports_to_try.append(465)
            elif SMTP_PORT == 465:
                ports_to_try.append(587)

            last_err = None
            for port in ports_to_try:
                use_ssl = (port == 465)
                log.info("[EMAIL_SERVICE] Verifying SMTP credentials for %s on port %s...", email_address, port)
                try:
                    smtp = aiosmtplib.SMTP(hostname=SMTP_HOST, port=port, use_tls=use_ssl, timeout=5)
                    await smtp.connect()
                    if not use_ssl:
                        try:
                            await smtp.starttls()
                        except aiosmtplib.SMTPException as tls_err:
                            if "already using TLS" not in str(tls_err):
                                raise
                    await smtp.login(email_address, email_password)
                    await smtp.quit()
                    log.info("[EMAIL_SERVICE] SMTP credentials verified successfully on port %s!", port)
                    return True, "SMTP credentials verified successfully"
                except Exception as smtp_err:
                    last_err = smtp_err
                    log.warning("[EMAIL_SERVICE] SMTP Verification failed on port %s: %s", port, smtp_err)

            err_msg = str(last_err)
            log.error("[EMAIL_SERVICE] All SMTP ports failed. Last error: %s", err_msg)
            if "535" in err_msg and email_address.lower().endswith("@gmail.com"):
                err_msg += " (Gmail App Password required. Please generate a 16-character App Password at https://myaccount.google.com/apppasswords instead of using your main Gmail password)"
            return False, f"SMTP Connection/Auth failed: {err_msg}"
        except Exception as outer_err:
            return False, f"SMTP verification unexpected error: {str(outer_err)}"

    return False, "Email service not configured. Please set EMAIL_ADDRESS and EMAIL_PASSWORD or SENDGRID_API_KEY in .env"


def get_sendgrid_key():
    """Fetch SendGrid API Key and show debug info."""
    key = os.getenv("SENDGRID_API_KEY", "").strip()
    if key:
        masked = key[:10] + "..." + key[-4:] if len(key) > 14 else "***"
        log.info("[SENDGRID] Using API Key: %s", masked)
    else:
        log.warning("[SENDGRID] No SendGrid API Key found in environment.")
    return key

# ── API / SMTP CORE SEND ─────────────────────────────────────────

async def send_mail_raw(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: Optional[str] = None,
    pdf_attachment: Optional[Tuple[bytes, str]] = None,
    attachments: Optional[List[Tuple[bytes, str]]] = None
) -> Tuple[bool, str]:
    """
    Core Email sending logic. Tries SendGrid first if SENDGRID_API_KEY is configured,
    and falls back to standard SMTP if EMAIL_ADDRESS and EMAIL_PASSWORD are configured.
    """
    api_key = os.getenv("SENDGRID_API_KEY", "").strip()
    email_address = os.getenv("EMAIL_ADDRESS", "").strip()
    email_password = os.getenv("EMAIL_PASSWORD", "").strip()

    if api_key:
        log.info("[EMAIL_SERVICE] Attempting delivery via SendGrid API Client...")
        if SendGridAPIClient is None:
            log.warning("[EMAIL_SERVICE] SendGrid library not installed. Checking SMTP fallback...")
        else:
            from_email = os.getenv("SENDGRID_FROM_EMAIL") or os.getenv("SENDER_EMAIL") or DEFAULT_FROM_EMAIL
            if not text_content:
                text_content = "Please view this email in an HTML-compatible client for the full report."
            try:
                # 1. Create Message with Display Name
                message = Mail(
                    from_email=Email(from_email, "VYOM AI Classroom"),
                    to_emails=To(to_email),
                    subject=subject,
                    plain_text_content=Content("text/plain", text_content),
                    html_content=Content("text/html", html_content)
                )
                
                # 1.5 Add PDF attachment if provided
                if pdf_attachment:
                    try:
                        from sendgrid.helpers.mail import Attachment, FileContent, FileName, FileType, Disposition
                        import base64
                        pdf_bytes, filename = pdf_attachment
                        encoded_pdf = base64.b64encode(pdf_bytes).decode()
                        
                        attachment = Attachment(
                            FileContent(encoded_pdf),
                            FileName(filename),
                            FileType("application/pdf"),
                            Disposition("attachment")
                        )
                        message.add_attachment(attachment)
                        log.info("[SENDGRID] Attached PDF file: %s", filename)
                    except Exception as att_err:
                        log.error("[SENDGRID] Failed to add PDF attachment: %s", att_err, exc_info=True)

                # Add additional attachments if provided
                if attachments:
                    try:
                        from sendgrid.helpers.mail import Attachment, FileContent, FileName, FileType, Disposition
                        import base64
                        for att_bytes, filename in attachments:
                            encoded_pdf = base64.b64encode(att_bytes).decode()
                            attachment = Attachment(
                                FileContent(encoded_pdf),
                                FileName(filename),
                                FileType("application/pdf"),
                                Disposition("attachment")
                            )
                            message.add_attachment(attachment)
                            log.info("[SENDGRID] Attached file: %s", filename)
                    except Exception as atts_err:
                        log.error("[SENDGRID] Failed to add additional attachments: %s", atts_err, exc_info=True)

                # 2. Add Anti-Spam Headers
                unsubscribe_link = "https://vyom.onrender.com/unsubscribe"
                message.add_header(Header("List-Unsubscribe", f"<{unsubscribe_link}>, <mailto:{from_email}?subject=unsubscribe>"))
                message.add_header(Header("Precedence", "list"))
                message.add_header(Header("X-Auto-Response-Suppress", "All"))
                
                # 3. Set Reply-To
                message.reply_to = Email(from_email, "VYOM AI Classroom Support")

                def _send():
                    sg = SendGridAPIClient(api_key)
                    response = sg.send(message)
                    return response.status_code

                status_code = await asyncio.to_thread(_send)
                if 200 <= status_code < 300:
                    log.info("[SENDGRID] SUCCESS: Email delivered to %s (Status: %s)", to_email, status_code)
                    return True, "Email sent successfully via SendGrid"
                else:
                    log.error("[SENDGRID] FAILED: SendGrid API returned status code %s", status_code)
            except Exception as e:
                log.error("[SENDGRID] UNEXPECTED ERROR: %s. Checking SMTP fallback...", e, exc_info=True)

    # ── Fallback / Primary SMTP (Gmail App Password) ──────────────────────
    if email_address and email_password:
        log.info("[EMAIL_SERVICE] Attempting delivery via SMTP (Gmail App Password)...")
        try:
            import aiosmtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText
            from email.mime.base import MIMEBase
            from email import encoders

            # Setup MIMEMultipart
            message = MIMEMultipart("alternative")
            message["From"] = f"VYOM AI Classroom <{email_address}>"
            message["To"] = to_email
            message["Subject"] = subject

            part1 = MIMEText(text_content or "Please view in HTML client", "plain", "utf-8")
            part2 = MIMEText(html_content, "html", "utf-8")
            message.attach(part1)
            message.attach(part2)

            if pdf_attachment or attachments:
                main_message = MIMEMultipart("mixed")
                main_message["From"] = message["From"]
                main_message["To"] = message["To"]
                main_message["Subject"] = message["Subject"]
                main_message.attach(message)

                if pdf_attachment:
                    pdf_bytes, filename = pdf_attachment
                    part = MIMEBase("application", "octet-stream")
                    part.set_payload(pdf_bytes)
                    encoders.encode_base64(part)
                    part.add_header(
                        "Content-Disposition",
                        f"attachment; filename={filename}",
                    )
                    main_message.attach(part)

                if attachments:
                    for att_bytes, filename in attachments:
                        part = MIMEBase("application", "octet-stream")
                        part.set_payload(att_bytes)
                        encoders.encode_base64(part)
                        part.add_header(
                            "Content-Disposition",
                            f"attachment; filename={filename}",
                        )
                        main_message.attach(part)
                message = main_message

            SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
            SMTP_PORT = int(os.getenv("SMTP_PORT", "587").strip())

            ports_to_try = [SMTP_PORT]
            if SMTP_PORT == 587:
                ports_to_try.append(465)
            elif SMTP_PORT == 465:
                ports_to_try.append(587)

            last_err = None
            for port in ports_to_try:
                use_ssl = (port == 465)
                log.info("[SMTP] Attempting delivery on port %s...", port)
                try:
                    smtp = aiosmtplib.SMTP(hostname=SMTP_HOST, port=port, use_tls=use_ssl, timeout=5)
                    await smtp.connect()
                    if not use_ssl:
                        try:
                            await smtp.starttls()
                        except aiosmtplib.SMTPException as tls_err:
                            if "already using TLS" not in str(tls_err):
                                raise
                    await smtp.login(email_address, email_password)
                    await smtp.send_message(message)
                    await smtp.quit()
                    
                    log.info("[SMTP] SUCCESS: Email sent successfully to %s on port %s", to_email, port)
                    return True, "Email sent successfully via SMTP"
                except Exception as smtp_err:
                    last_err = smtp_err
                    log.warning("[SMTP] Failed to send on port %s: %s", port, smtp_err)

            log.error("[SMTP] ERROR: All ports failed to send via SMTP. Last error: %s", last_err)
            return False, f"SMTP Send Error: {str(last_err)}"
        except ImportError:
            log.error("[SMTP] aiosmtplib not installed")
            return False, "aiosmtplib library not installed"
        except Exception as outer_err:
            log.error("[SMTP] ERROR: Unexpected error during SMTP send: %s", outer_err, exc_info=True)
            return False, f"SMTP unexpected error: {str(outer_err)}"

    return False, "Email service not configured. Please set EMAIL_ADDRESS and EMAIL_PASSWORD or SENDGRID_API_KEY in .env"

# ── Self-Test Mode ────────────────────────────────────────────────

async def verify_email_system() -> Tuple[bool, str]:
    """Diagnostic test on startup."""
    api_key = os.getenv("SENDGRID_API_KEY", "").strip()
    email_address = os.getenv("EMAIL_ADDRESS", "").strip()
    
    if not api_key and not email_address:
        return False, "Neither SENDGRID_API_KEY nor EMAIL_ADDRESS is configured"

    test_html = "<h2>Diagnostic Test</h2><p>Connection Successful. Verification completed.</p>"
    test_text = "Diagnostic Test: Connection Successful."
    
    recipient = os.getenv("SENDGRID_FROM_EMAIL") or os.getenv("SENDER_EMAIL") or email_address or DEFAULT_FROM_EMAIL
    return await send_mail_raw(recipient, "🔬 VYOM Diagnostic Test", test_html, test_text)

# ── Content Generators ───────────────────────────────────────────

def generate_email_text(session_data: dict, teacher_name: str) -> str:
    """Generate plain text version of the session report."""
    analytics = session_data.get("analytics", {})
    session_id = session_data.get("code", "N/A")
    participation = analytics.get("participation", 0)
    understanding = analytics.get("understanding", 0)
    total_students = analytics.get("total_students", 0)

    return f"""
VYOM SESSION REPORT
========================
Session: {session_id}
Teacher: {teacher_name}

ANALYTICS:
- Participation: {participation}%
- Understanding: {understanding}%
- Students: {total_students}

Thank you for using VYOM.
    """.strip()

def generate_email_html(session_data: dict, teacher_name: str) -> str:
    """Generate professional, clean HTML email."""
    analytics = session_data.get("analytics", {})
    start_time = datetime.fromtimestamp(session_data.get("created_at", 0))
    duration_mins = max(1, session_data.get("duration_secs", 0) // 60)
    
    total_students = analytics.get("total_students", 0)
    participation = analytics.get("participation", 0)
    understanding = analytics.get("understanding", 0)
    session_id = session_data.get("code", "N/A")

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #1e293b; background: #f1f5f9; margin: 0; padding: 40px 20px; }}
            .card {{ max-width: 560px; margin: 0 auto; background: #ffffff; border-radius: 12px; border: 1px solid #e2e8f0; overflow: hidden; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1); }}
            .header {{ background: #10b981; color: #ffffff; padding: 32px 24px; text-align: center; }}
            .header h1 {{ margin: 0; font-size: 24px; font-weight: 700; }}
            .content {{ padding: 32px 24px; }}
            .stat-box {{ background: #f8fafc; border: 1px solid #f1f5f9; border-radius: 8px; padding: 16px; margin-bottom: 12px; text-align: center; }}
            .stat-value {{ font-size: 20px; font-weight: 700; color: #059669; }}
            .stat-label {{ font-size: 12px; color: #64748b; text-transform: uppercase; letter-spacing: 0.05em; }}
            .footer {{ padding: 24px; text-align: center; font-size: 12px; color: #94a3b8; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <h1>Session Report</h1>
                <div style="opacity: 0.8; font-size: 14px;">ID: {session_id}</div>
            </div>
            <div class="content">
                <p>Hello <strong>{teacher_name}</strong>,</p>
                <p>Here are the analytics for your recent session:</p>
                <div style="display: table; width: 100%; border-spacing: 8px;">
                    <div style="display: table-row;">
                        <div style="display: table-cell; width: 50%;" class="stat-box">
                            <div class="stat-value">{participation}%</div>
                            <div class="stat-label">Participation</div>
                        </div>
                        <div style="display: table-cell; width: 50%;" class="stat-box">
                            <div class="stat-value">{understanding}%</div>
                            <div class="stat-label">Understanding</div>
                        </div>
                    </div>
                    <div style="display: table-row;">
                        <div style="display: table-cell; width: 50%;" class="stat-box">
                            <div class="stat-value">{total_students}</div>
                            <div class="stat-label">Students</div>
                        </div>
                        <div style="display: table-cell; width: 50%;" class="stat-box">
                            <div class="stat-value">{duration_mins}m</div>
                            <div class="stat-label">Duration</div>
                        </div>
                    </div>
                </div>
                <p style="font-size: 13px; color: #64748b; text-align: center; margin-top: 24px;">
                    Started at {start_time.strftime('%I:%M %p')}
                </p>
            </div>
            <div class="footer">
                ClassMind Intelligence &bull; <a href="https://classmind.onrender.com" style="color: #10b981; text-decoration: none;">Dashboard</a>
            </div>
        </div>
    </body>
    </html>
    """

# ── Wrappers ─────────────────────────────────────────────────────

# ── PDF Generation Helper ──

weasyprint_font_config = None

def create_session_report_pdf(report: dict, teacher_email: str = "teacher@classmind.com") -> bytes:
    """Generate a highly polished, professional PDF report matching the dashboard's layout using WeasyPrint based on premium_report.html."""
    global weasyprint_font_config
    import os
    import sys
    import math
    import time
    import re
    from datetime import datetime

    # 1. Setup DLL paths for WeasyPrint on Windows
    if sys.platform == "win32":
        for path in ["C:\\msys64\\mingw64\\bin", "C:\\Users\\robin\\msys64\\mingw64\\bin", "C:\\Program Files\\Tesseract-OCR"]:
            if os.path.exists(path):
                if hasattr(os, "add_dll_directory"):
                    try:
                        os.add_dll_directory(path)
                    except Exception:
                        pass
                if path not in os.environ["PATH"]:
                    os.environ["PATH"] = path + os.path.pathsep + os.environ["PATH"]

    import weasyprint
    if weasyprint_font_config is None:
        try:
            from weasyprint.text.fonts import FontConfiguration
            weasyprint_font_config = FontConfiguration()
        except Exception:
            pass

    # Extract primary parameters from report
    teacher_name = report.get("teacher_name", "Teacher")
    session_name = report.get("session_name", "Live Class")
    session_code = report.get("session_code", report.get("code", "Session"))
    created_at = report.get("created_at") or time.time()
    duration_mins = report.get("duration_mins") or 0
    
    # 2. Re-implement data extraction to get gradebook and attendance data
    from store import sessions
    s = sessions.get(session_code)
    
    # Re-implementation of compute_attendance_summary(s)
    if s:
        att = s.get("attendance", {})
        records = att.get("records", {})
        students = s.get("students", {})
        attendance_data = {
            "state": att.get("state", "inactive"),
            "started_at": att.get("started_at"),
            "ended_at": att.get("ended_at"),
            "locked_at": att.get("locked_at"),
            "records": {}
        }
        for sid, st in students.items():
            r = records.get(sid, {})
            attendance_data["records"][sid] = {
                "student_id": sid,
                "name": st.get("name", sid),
                "roll": st.get("roll", ""),
                "class": st.get("class", ""),
                "status": r.get("status", "not_marked"),
                "join_at": r.get("join_at"),
                "leave_at": r.get("leave_at"),
                "duration": r.get("duration", 0),
                "interactions": r.get("interactions", 0),
            }
    else:
        attendance_data = {"records": {}}

    # Re-implementation of get_session_gradebook(session_code)
    students_list = report.get("students", [])
    if s:
        gradebook_rows = []
        has_coding = any(t.get("type") == "coding" for t in s.get("tasks", []))
        leaderboard = s.get("test_state", {}).get("leaderboard", [])
        has_test = len(leaderboard) > 0
        total_tasks = len(s.get("tasks", []))

        for idx, st in enumerate(students_list):
            sid = st.get("student_id")
            if not sid:
                sid = next((k for k, v in s.get("students", {}).items() if v.get("name") == st.get("name")), None)
            if not sid:
                sid = st.get("name")
            student_obj = s.get("students", {}).get(sid, {})
            
            roll_no = student_obj.get("roll_no") or f"R-{idx+1:02d}"
            class_name = student_obj.get("class_name") or s.get("session_name", "Live Class")
            
            task_correct = st.get("correct", 0)
            task_attempts = st.get("total_attempts", 0)
            task_score = int((task_correct / max(task_attempts, 1)) * 100) if task_attempts > 0 else 0
            
            test_score = None
            for entry in leaderboard:
                if entry.get("student_id") == sid:
                    test_score = entry.get("score")
                    break
            
            coding_score = student_obj.get("coding_score") if student_obj.get("coding_submitted") else None
            
            scores = []
            if total_tasks > 0:
                scores.append(task_score)
            if test_score is not None:
                scores.append(test_score)
            if coding_score is not None:
                scores.append(coding_score)
                
            overall_percentage = int(sum(scores) / len(scores)) if scores else 0
            
            gradebook_rows.append({
                "student_id": sid,
                "name": st.get("name", "Student"),
                "roll_no": roll_no,
                "class_name": class_name,
                "task_score": task_score,
                "test_score": test_score,
                "coding_score": coding_score,
                "coding_submitted": bool(student_obj.get("coding_submitted")),
                "overall_percentage": overall_percentage,
                "rank": 0
            })
            
        gradebook_rows.sort(key=lambda x: x["overall_percentage"], reverse=True)
        for rank_idx, entry in enumerate(gradebook_rows):
            entry["rank"] = rank_idx + 1
            
        gradebook_data = {
            "session_code": session_code,
            "session_name": s.get("session_name", "Live Class"),
            "teacher_name": s.get("teacher_name", "Teacher"),
            "created_at": s.get("created_at", time.time()),
            "has_test": has_test,
            "has_coding": has_coding,
            "gradebook": gradebook_rows
        }
    else:
        gradebook_rows = []
        for idx, st in enumerate(students_list):
            gradebook_rows.append({
                "student_id": st.get("name"),
                "name": st.get("name", "Student"),
                "roll_no": f"R-{idx+1:02d}",
                "class_name": report.get("session_name", "Live Class"),
                "task_score": 0,
                "test_score": None,
                "coding_score": None,
                "coding_submitted": False,
                "overall_percentage": 0,
                "rank": idx + 1
            })
        gradebook_data = {
            "session_code": session_code,
            "session_name": report.get("session_name", "Live Class"),
            "teacher_name": report.get("teacher_name", "Teacher"),
            "created_at": report.get("created_at", time.time()),
            "has_test": False,
            "has_coding": False,
            "gradebook": gradebook_rows
        }

    # Helpers
    def get_initials(name):
        if not name:
            return "ST"
        parts = name.split()
        if not parts:
            return "ST"
        return "".join(p[0] for p in parts).upper()[:2]

    def calculate_attendance_pct(student_id, attendance_data, session_duration_mins, joined_at, created_at):
        records = (attendance_data or {}).get("records", {})
        record = records.get(student_id)
        if record:
            status = record.get("status")
            duration = record.get("duration", 0)
            if status == 'present':
                if duration > 0 and session_duration_mins > 0:
                    return min(100, max(0, round((duration / 60 / session_duration_mins) * 100)))
                return 100
            if status == 'exited' and duration > 0 and session_duration_mins > 0:
                return min(100, max(0, round((duration / 60 / session_duration_mins) * 100)))
            if status in ('not_marked', 'absent', 'revoked'):
                return 0
        if joined_at and created_at and session_duration_mins > 0:
            elapsed = (created_at + session_duration_mins * 60) - joined_at
            if elapsed > 0:
                return min(100, max(0, round((elapsed / (session_duration_mins * 60)) * 100)))
        return 100

    # 3. Read template HTML file
    template_path = os.path.join(os.path.dirname(__file__), "premium_report.html")
    with open(template_path, "r", encoding="utf-8") as f:
        html_content = f.read()

    # Inject CSS layout overrides into @media print to prevent WeasyPrint infinite layout loops on Windows
    css_override = """
    /* --- CSS Overrides for WeasyPrint Layout Engine --- */
    @media print {
      .rpt-header, .teacher-info-bar {
        display: flex !important;
      }
      body, .report-container, .hero-section, .analytics-grid, .join-panels, 
      .task-grid, .und-summary, .sec-donut-wrap, .tib-meta, .performers-row, 
      .most-active-list, .ai-recs-list {
        display: block !important;
      }
      .tib-meta-item {
        border-right: none !important;
        padding: 4px 0 !important;
        display: block !important;
      }
      .kpi-table {
        display: table !important;
        width: 100% !important;
      }
      .kpi-td {
        display: table-cell !important;
        width: 20% !important;
      }
      .rpt-section {
        border-right: none !important;
        border-bottom: 1px solid var(--gold-border) !important;
        page-break-inside: avoid !important;
        display: block !important;
      }
      .hero-kpi-stack {
        display: block !important;
        padding: 0 !important;
      }
      .hero-kpi-card {
        margin-bottom: 8px !important;
        display: block !important;
      }
      .hero-center {
        margin: 16px 0 !important;
        display: block !important;
        text-align: center !important;
      }
      .join-panel {
        margin-bottom: 8px !important;
        display: block !important;
      }
      .task-completion-panel, .task-performers-panel {
        margin-bottom: 8px !important;
        display: block !important;
      }
      .und-card {
        margin-bottom: 8px !important;
        display: block !important;
      }
      .ai-grid {
        display: block !important;
      }
    }
    """
    html_content = html_content.replace("/* ─── PRINT ─── */", "/* ─── PRINT ─── */" + css_override)

    # 4. Compute all KPIs and elements
    total_students = len(gradebook_rows)
    total_tasks = report.get("total_tasks", 0)
    
    total_alerts = 0
    total_tab_switches = 0
    total_face_missing = 0
    total_multi_face = 0
    total_devtools = 0
    for st in students_list:
        warns = st.get("warnings", {})
        tab = warns.get("tab_switches", 0)
        face = warns.get("face_missing", 0)
        multi = warns.get("multi_face", 0) or warns.get("multiple_faces", 0)
        dev = warns.get("devtools", 0)
        total_tab_switches += tab
        total_face_missing += face
        total_multi_face += multi
        total_devtools += dev
    total_alerts = total_tab_switches + total_face_missing + total_multi_face + total_devtools

    understanding_pct = report.get("analytics", {}).get("understanding", 0)
    participation_pct = report.get("analytics", {}).get("participation", 0)
    
    quality_score = round((understanding_pct * 0.55) + (participation_pct * 0.3) + (max(0, 100 - (total_alerts * 2)) * 0.15))
    quality_score_clamped = max(0, min(100, quality_score))
    
    present_count = 0
    for st in students_list:
        joined_at = st.get("joined_at", 0)
        att_pct = calculate_attendance_pct(
            st.get("student_id") or st.get("name"),
            attendance_data,
            duration_mins,
            joined_at,
            created_at
        )
        if att_pct > 0:
            present_count += 1
    overall_att_pct = round((present_count / total_students) * 100) if total_students > 0 else 0

    # Lists/Tables markup generation
    
    # firstToJoinList
    active_students = [st for st in students_list if st.get("joined_at", 0) > 0]
    active_students.sort(key=lambda st: st["joined_at"])
    first_html_parts = []
    for idx, st in enumerate(active_students[:3]):
        time_str = datetime.fromtimestamp(st["joined_at"]).strftime('%I:%M %p')
        first_html_parts.append(f'''
        <div class="join-item">
          <div class="join-student"><span class="rank-badge rank-{idx+1}">{idx+1}</span> {st.get("name", "Student")}</div>
          <span class="join-time">{time_str}</span>
        </div>''')
    first_html = "".join(first_html_parts)
    if not first_html:
        first_html = '<div class="join-item" style="color:var(--text-dim);justify-content:center;">No join records</div>'

    # lateJoinersList
    session_started_at = report.get("started_at") or report.get("created_at") or 0
    late_joiners = []
    if session_started_at > 0:
        for st in active_students:
            diff_mins = round((st["joined_at"] - session_started_at) / 60)
            if diff_mins > 5:
                late_joiners.append({
                    "name": st.get("name", "Student"),
                    "mins_late": diff_mins
                })
    late_joiners.sort(key=lambda x: x["mins_late"], reverse=True)
    late_html_parts = []
    for st in late_joiners[:3]:
        late_html_parts.append(f'''
        <div class="join-item">
          <div class="join-student">⚠️ {st["name"]}</div>
          <span class="join-time"><span class="late-badge">{st["mins_late"]} min late</span></span>
        </div>''')
    late_html = "".join(late_html_parts)
    if not late_html:
        late_html = '<div class="join-item" style="color:var(--accent-green);justify-content:center;font-weight:500;font-size:11px;">✓ No late joiners detected</div>'

    # topViolatorsList
    violators = []
    for st in students_list:
        warns = st.get("warnings", {})
        total = (warns.get("tab_switches", 0) +
                 warns.get("face_missing", 0) +
                 warns.get("multi_face", 0) +
                 warns.get("multiple_faces", 0) +
                 warns.get("devtools", 0))
        if total > 0:
            violators.append({"name": st.get("name", "Student"), "alerts": total})
    violators.sort(key=lambda x: x["alerts"], reverse=True)
    violators_html_parts = []
    for v in violators[:3]:
        violators_html_parts.append(f'''<div class="sec-violator-item"><span>{v["name"]}</span><span class="alert-count">{v["alerts"]} Alerts</span></div>''')
    violators_html = "".join(violators_html_parts)
    if not violators_html:
        violators_html = '<div class="sec-violator-item" style="color:var(--accent-green);justify-content:center;font-weight:500;">✓ No security alerts triggered</div>'

    # riskLow/riskMed/riskHigh counts
    low_risk_count = 0
    med_risk_count = 0
    high_risk_count = 0
    for st in students_list:
        warns = st.get("warnings", {})
        total = (warns.get("tab_switches", 0) +
                 warns.get("face_missing", 0) +
                 warns.get("multi_face", 0) +
                 warns.get("multiple_faces", 0) +
                 warns.get("devtools", 0))
        if total <= 2:
            low_risk_count += 1
        elif total <= 5:
            med_risk_count += 1
        else:
            high_risk_count += 1
    risk_low_pct = round((low_risk_count / total_students) * 100) if total_students > 0 else 100
    risk_med_pct = round((med_risk_count / total_students) * 100) if total_students > 0 else 0
    risk_high_pct = (100 - risk_low_pct - risk_med_pct) if total_students > 0 else 0

    # taskPerformersRow & topPerformersOverviewContainer
    top_performers = gradebook_rows[:3]
    colors_list = ['#c084fc', '#fb7185', '#60a5fa']
    medals = ['🥇', '🥈', '🥉']
    border_colors = ['#D4AF37', '#94a3b8', '#cd7f32']
    
    performers_html_parts = []
    for idx, st in enumerate(top_performers):
        initials = get_initials(st["name"])
        badge_class = 'p-gold' if idx == 0 else ('p-silver' if idx == 1 else 'p-bronze')
        performers_html_parts.append(f'''
        <div class="performer-avatar-card">
          <div class="performer-avatar-wrapper">
            <div style="width:44px;height:44px;border-radius:50%;background:{colors_list[idx%3]};display:flex;align-items:center;justify-content:center;font-weight:700;color:#FFF;border:2px solid var(--orange);font-family:var(--font-poppins);font-size:14px;">{initials}</div>
            <span class="performer-badge-mini {badge_class}">{idx+1}</span>
          </div>
          <span class="performer-name">{st["name"]}</span>
          <span class="performer-score">{st["overall_percentage"]}%</span>
        </div>''')
    task_performers_row = "".join(performers_html_parts)
    if not task_performers_row:
        task_performers_row = '<div class="performer-avatar-card" style="color:var(--text-dim);">No submissions</div>'

    rank_cards_parts = []
    for idx, st in enumerate(top_performers):
        initials = get_initials(st["name"])
        rank_cards_parts.append(f'''
        <div class="rank-card rank-card-{idx+1}">
          <span class="rank-laurel">{medals[idx]}</span>
          <div style="position:relative;">
            <div class="rank-student-avatar" style="background:{colors_list[idx%3]};display:flex;align-items:center;justify-content:center;font-weight:700;color:#FFF;font-family:var(--font-poppins);font-size:15px;border-color:{border_colors[idx]}">{initials}</div>
          </div>
          <div class="rank-details">
            <span class="rank-name">{st["name"]}</span>
            <span class="rank-lbl">Overall Score</span>
            <span class="rank-score">{st["overall_percentage"]}%</span>
          </div>
        </div>''')
    rank_cards_html = "".join(rank_cards_parts)
    if not rank_cards_html:
        rank_cards_html = '<div class="rank-card" style="color:var(--text-dim);border:none;">No top performer records</div>'

    # topicProgressBars & strongest/weakest topics
    topic_scores = []
    topic_confusion = report.get("analytics", {}).get("topic_confusion", {})
    if topic_confusion:
        for name, d in topic_confusion.items():
            total = d.get("total", 0)
            wrong = d.get("wrong", 0)
            pct = round((1 - (wrong / total)) * 100) if total > 0 else 0
            topic_scores.append({"name": name, "pct": pct})
        topic_scores.sort(key=lambda x: x["pct"], reverse=True)

    if topic_scores:
        strong_topic = topic_scores[0]["name"]
        weak_topic = topic_scores[-1]["name"]
        strongest_topic_val = f"{strong_topic} ({topic_scores[0]['pct']}%)"
        weakest_topic_val = f"{weak_topic} ({topic_scores[-1]['pct']}%)"
        
        topic_html_parts = []
        for t in topic_scores[:4]:
            fill_class = 't-fill-green' if t["pct"] >= 80 else ('t-fill-blue' if t["pct"] >= 60 else 't-fill-orange')
            topic_html_parts.append(f'''<div class="topic-progress-item">
            <div class="topic-info"><span>{t["name"]}</span><span>{t["pct"]}%</span></div>
            <div class="topic-bar-bg"><div class="topic-bar-fill {fill_class}" style="width:{t["pct"]}%;"></div></div>
          </div>''')
        topic_progress_bars = "".join(topic_html_parts)
    else:
        strongest_topic_val = "—"
        weakest_topic_val = "—"
        topic_progress_bars = '<div class="topic-progress-item" style="color:var(--text-dim);padding:8px 0;font-size:11px;">No topic data available</div>'

    # needsAttentionList
    sorted_by_score_asc = sorted(gradebook_rows, key=lambda x: x["overall_percentage"])
    attention_students = sorted_by_score_asc[:4]
    attention_html_parts = []
    for s_row in attention_students:
        attention_html_parts.append(f'''
        <div class="attention-item">
          <div class="attention-student-info"><span>{s_row["name"]}</span><span class="score">{s_row["overall_percentage"]}%</span></div>
          <div class="attention-bar-bg"><div class="attention-bar-fill" style="width:{s_row["overall_percentage"]}%;"></div></div>
        </div>''')
    attention_html = "".join(attention_html_parts)
    if not attention_html:
        attention_html = '<div class="attention-item" style="color:var(--accent-green);font-weight:500;font-size:11px;">✓ All students are performing well!</div>'

    # engagement metrics (engHigh, engMed, engLow)
    high_eng = 0
    med_eng = 0
    low_eng = 0
    for st in students_list:
        answered = st.get("total_answered", 0)
        if total_tasks == 0:
            high_eng += 1
        else:
            ratio = answered / total_tasks
            if ratio >= 0.75:
                high_eng += 1
            elif ratio >= 0.25:
                med_eng += 1
            else:
                low_eng += 1
    total_eng = high_eng + med_eng + low_eng
    
    eng_high_pct = round(high_eng / total_eng * 100) if total_eng > 0 else 0
    eng_med_pct = round(med_eng / total_eng * 100) if total_eng > 0 else 0
    eng_low_pct = (100 - eng_high_pct - eng_med_pct) if total_eng > 0 else 0
    
    eng_high_val = f"{high_eng} ({eng_high_pct}%)"
    eng_med_val = f"{med_eng} ({eng_med_pct}%)"
    eng_low_val = f"{low_eng} ({eng_low_pct}%)"

    # mostActiveList
    active_list = []
    for st in students_list:
        sid = st.get("student_id")
        if not sid and s:
            sid = next((k for k, v in s.get("students", {}).items() if v.get("name") == st.get("name")), None)
        if not sid:
            sid = st.get("name")
        att_rec = attendance_data.get("records", {}).get(sid, {})
        count = att_rec.get("interactions", 0) + st.get("total_answered", 0)
        active_list.append({"name": st.get("name", "Student"), "count": count})
    active_list.sort(key=lambda x: x["count"], reverse=True)
    active_html_parts = []
    for idx, st in enumerate(active_list[:3]):
        active_html_parts.append(f'''
        <div class="most-active-item">
          <span><span class="index">{idx+1}.</span> {st["name"]}</span>
          <span class="val">{st["count"]} Interactions</span>
        </div>''')
    active_html = "".join(active_html_parts)
    if not active_html:
        active_html = '<div class="most-active-item" style="color:var(--text-dim);">No interactions recorded</div>'

    # aiSummaryText and aiRecsList
    if topic_scores:
        ai_summary_text = f"The session maintained high engagement throughout with active participation from most students. {strong_topic} concepts were well understood, while {weak_topic} concepts showed lower confidence. Security alerts were within acceptable limits."
        ai_recs_html = f'''
          <div class="ai-rec-item"><span class="ai-rec-check">✓</span><span>Revise {weak_topic} concepts in next session</span></div>
          <div class="ai-rec-item"><span class="ai-rec-check">✓</span><span>Provide extra practice questions for weak topics</span></div>
          <div class="ai-rec-item"><span class="ai-rec-check">✓</span><span>Follow up with students having low understanding</span></div>
          <div class="ai-rec-item"><span class="ai-rec-check">✓</span><span>Great session! Keep up the excellent engagement</span></div>'''
    else:
        ai_summary_text = f"The session completed with {total_students} students joined. AI insights will populate once questions and tasks are completed."
        ai_recs_html = '''
          <div class="ai-rec-item"><span class="ai-rec-check">✓</span><span>Assign tasks to begin collecting learning metrics</span></div>
          <div class="ai-rec-item"><span class="ai-rec-check">✓</span><span>Monitor student real-time engagement in dashboard</span></div>'''

    # premiumGradebookBody
    gradebook_rows_html = []
    for s_row in gradebook_rows:
        student_obj_in_report = next((st for st in students_list if st.get("student_id") == s_row["student_id"]), None)
        joined_at = student_obj_in_report.get("joined_at", 0) if student_obj_in_report else 0
        att_pct = calculate_attendance_pct(
            s_row["student_id"],
            attendance_data,
            duration_mins,
            joined_at,
            created_at
        )
        test_score_str = f"{s_row['test_score']}%" if s_row['test_score'] is not None else '—'
        coding_score_str = f"{s_row['coding_score']}%" if s_row['coding_submitted'] else '—'
        gradebook_rows_html.append(f'''<tr>
          <td style="text-align:center;font-weight:700;color:var(--gold);">#{s_row["rank"]}</td>
          <td style="font-weight:700;color:var(--text);">{s_row["name"]}</td>
          <td style="font-family:monospace;color:var(--text3);">{s_row["roll_no"]}</td>
          <td>{s_row["class_name"] or "—"}</td>
          <td style="text-align:center;">{s_row["task_score"]}%</td>
          <td style="text-align:center;">{test_score_str}</td>
          <td style="text-align:center;">{coding_score_str}</td>
          <td style="text-align:center;font-weight:600;color:var(--gold);">{att_pct}%</td>
          <td style="text-align:center;font-weight:800;color:var(--accent-green);">{s_row["overall_percentage"]}%</td>
        </tr>''')
    premium_gradebook_body = "".join(gradebook_rows_html)
    if not premium_gradebook_body:
        premium_gradebook_body = '<tr><td colspan="9" style="text-align:center;padding:24px;color:var(--text-dim);">No student marks records found.</td></tr>'

    # responseRateChart (values calculation)
    response_rates = []
    response_rate_labels = []
    question_stats = report.get("question_stats", [])
    for idx, q in enumerate(question_stats):
        response_rate_labels.append(f"Q{q.get('index') or (idx + 1)}")
        rate = round((q.get("total_responses", 0) / total_students) * 100) if total_students > 0 else 0
        response_rates.append(min(100, rate))
    avg_response_rate = round(sum(response_rates) / len(response_rates)) if response_rates else 0

    # SVGs for charts
    
    # 1. Presence horizontal bars SVG
    presence_students_list = []
    for st in students_list:
        sid = st.get("student_id")
        if not sid and s:
            sid = next((k for k, v in s.get("students", {}).items() if v.get("name") == st.get("name")), None)
        if not sid:
            sid = st.get("name")
        att_rec = attendance_data.get("records", {}).get(sid)
        presence_mins = round(att_rec["duration"] / 60) if att_rec else 0
        if presence_mins == 0 and st.get("joined_at", 0) > 0:
            end_time_val = (session_started_at + duration_mins * 60) if session_started_at > 0 else time.time()
            presence_mins = round(max(0, end_time_val - st["joined_at"]) / 60)
        presence_students_list.append({
            "name": st.get("name", "Student"),
            "duration": min(duration_mins, presence_mins)
        })
    presence_students_list.sort(key=lambda x: x["duration"], reverse=True)
    top_presence_students = presence_students_list[:5]
    
    presence_names = [st["name"] for st in top_presence_students]
    presence_durations = [st["duration"] for st in top_presence_students]
    
    def make_presence_bar_chart_svg(names, durations, max_duration):
        if not names:
            return '<svg width="100%" height="140"><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#A0A0A0" font-size="12">No data</text></svg>'
        svg_parts = ['<svg width="100%" height="140" viewBox="0 0 350 140" xmlns="http://www.w3.org/2000/svg">']
        max_val = max(60, max_duration)
        for idx, (name, dur) in enumerate(zip(names, durations)):
            y = 5 + idx * 26
            disp_name = name[:14] + '..' if len(name) > 15 else name
            svg_parts.append(f'<text x="5" y="{y + 15}" fill="#E5E5E5" font-size="10" font-weight="600" font-family="Inter, sans-serif">{disp_name}</text>')
            bar_max_width = 180
            bar_x = 110
            svg_parts.append(f'<rect x="{bar_x}" y="{y + 4}" width="{bar_max_width}" height="14" fill="rgba(255, 255, 255, 0.04)" rx="4" />')
            width_val = int((dur / max_val) * bar_max_width) if max_val > 0 else 0
            width_val = max(2, min(bar_max_width, width_val))
            svg_parts.append(f'<rect x="{bar_x}" y="{y + 4}" width="{width_val}" height="14" fill="rgba(255, 122, 0, 0.35)" stroke="#FF7A00" stroke-width="1" rx="4" />')
            svg_parts.append(f'<text x="{bar_x + width_val + 6}" y="{y + 15}" fill="#FF7A00" font-size="9" font-weight="700" font-family="Inter, sans-serif">{dur}m</text>')
        svg_parts.append('</svg>')
        return "".join(svg_parts)
        
    presence_chart_svg = make_presence_bar_chart_svg(presence_names, presence_durations, duration_mins)

    # 2. Security Alerts Donut SVG
    def _make_donut_svg(segments, colors, size=70, stroke_width=7):
        total = sum(segments)
        r = (size - stroke_width) / 2
        if total == 0:
            return f'<svg width="{size}" height="{size}"><circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="{stroke_width}" /></svg>'
        svg = f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" xmlns="http://www.w3.org/2000/svg" style="display: block; margin: auto;">'
        accum = 0.0
        for val, color in zip(segments, colors):
            if val <= 0:
                continue
            pct = val / total
            dash_len = pct * 100
            space_len = 100 - dash_len
            offset = -accum * 100
            svg += f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{color}" stroke-width="{stroke_width}" pathLength="100" stroke-dasharray="{dash_len} {space_len}" stroke-dashoffset="{offset}" transform="rotate(-90 {size/2} {size/2})" />'
            accum += pct
        svg += '</svg>'
        return svg

    security_donut_svg = _make_donut_svg(
        segments=[total_tab_switches, total_face_missing, total_multi_face, total_devtools],
        colors=['#3b82f6', '#FF7A00', '#D4AF37', '#22c55e'],
        size=130,
        stroke_width=14
    )

    # 3. Task Completion Circular SVG
    def make_completion_circular_svg(pct):
        return f'''
        <svg width="90" height="90" viewBox="0 0 96 96" xmlns="http://www.w3.org/2000/svg" style="display: block; margin: auto;">
          <circle cx="48" cy="48" r="42" fill="none" stroke="rgba(255, 255, 255, 0.04)" stroke-width="7" />
          <circle cx="48" cy="48" r="42" fill="none" stroke="#FF7A00" stroke-width="7" stroke-linecap="round"
                  pathLength="100" stroke-dasharray="{pct} {100 - pct}" transform="rotate(-90 48 48)" />
        </svg>
        '''
    completion_circular_svg = make_completion_circular_svg(participation_pct)

    # 4. Engagement Pie Chart SVG
    engagement_pie_svg = _make_donut_svg(
        segments=[high_eng, med_eng, low_eng],
        colors=['#22c55e', '#D4AF37', '#ef4444'],
        size=80,
        stroke_width=40
    )

    # 5. Response Rate Area Line Chart SVG
    def make_response_rate_line_chart_svg(labels, values, width=350, height=100):
        if not values:
            return f'''<svg width="100%" height="{height}"><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="#A0A0A0" font-size="10">No data</text></svg>'''
        
        n = len(values)
        if n == 1:
            values = [values[0], values[0]]
            labels = [labels[0], labels[0]]
            n = 2
            
        min_v = 0
        max_v = 100
        coords = []
        for i, v in enumerate(values):
            x = 20 + i * (width - 40) / (n - 1)
            y = height - 20 - (v - min_v) * (height - 35) / (max_v - min_v)
            coords.append((x, y))
            
        line_path = "M " + " L ".join(f"{x},{y}" for x, y in coords)
        area_path = f"M {coords[0][0]},{height - 18} " + " ".join(f"L {x},{y}" for x, y in coords) + f" L {coords[-1][0]},{height - 18} Z"
        
        grid_elements = []
        for pct_val in [0, 50, 100]:
            grid_y = height - 20 - (pct_val - min_v) * (height - 35) / (max_v - min_v)
            grid_elements.append(f'<line x1="20" y1="{grid_y}" x2="{width-20}" y2="{grid_y}" stroke="rgba(212, 175, 55, 0.06)" stroke-width="1" />')
            
        for i, lbl in enumerate(labels):
            x = 20 + i * (width - 40) / (n - 1)
            grid_elements.append(f'<text x="{x}" y="{height - 5}" fill="#A0A0A0" font-size="8" font-family="Inter, sans-serif" text-anchor="middle">{lbl}</text>')

        gradient_def = f'''
            <linearGradient id="rrLineGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="rgba(212, 175, 55, 0.28)" />
              <stop offset="100%" stop-color="rgba(212, 175, 55, 0.0)" />
            </linearGradient>
        '''
        
        svg = f'''
        <svg width="100%" height="{height}" viewBox="0 0 {width} {height}" xmlns="http://www.w3.org/2000/svg">
          <defs>{gradient_def}</defs>
          {"".join(grid_elements)}
          <path d="{area_path}" fill="url(#rrLineGrad)" />
          <path d="{line_path}" fill="none" stroke="#D4AF37" stroke-width="2" />
          {" ".join(f'<circle cx="{x}" cy="{y}" r="2.5" fill="#D4AF37" />' for x, y in coords)}
        </svg>
        '''
        return svg
    
    response_rate_chart_svg = make_response_rate_line_chart_svg(response_rate_labels, response_rates)

    # QR Code Image Tag generated offline locally using qrcode to avoid external HTTP requests
    target_url = f"https://vyom.onrender.com/session/{session_code}/premium-report"
    try:
        import qrcode
        import io
        import base64
        qr = qrcode.QRCode(version=1, box_size=10, border=1)
        qr.add_data(target_url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        qr_buf = io.BytesIO()
        img.save(qr_buf, format="PNG")
        qr_base64 = "data:image/png;base64," + base64.b64encode(qr_buf.getvalue()).decode()
        qr_img_tag = f'<img src="{qr_base64}" style="width: 60px !important; height: 60px !important; display: block; border-radius: 6px;" />'
    except Exception as qr_err:
        log.warning("[PDF_GENERATOR] Failed to generate QR code offline, using fallback URL: %s", qr_err)
        qr_img_tag = f'<img src="https://api.qrserver.com/v1/create-qr-code/?size=60x60&amp;data={target_url}" style="width: 60px !important; height: 60px !important; display: block; border-radius: 6px;" />'

    # 5. Inject everything into HTML template using regex replacements
    def replace_tag_content(html, element_id, new_content):
        pattern = r'(<[^>]*\bid="' + re.escape(element_id) + r'"\b[^>]*>).*?(</[^>]*>)'
        return re.sub(pattern, lambda m: m.group(1) + str(new_content) + m.group(2), html, flags=re.DOTALL)

    def replace_style_width(html, element_id, new_width):
        pattern = r'(<[^>]*\bid="' + re.escape(element_id) + r'"\b[^>]*\bstyle="width:\s*)[^;"]*(;?\s*")'
        return re.sub(pattern, lambda m: m.group(1) + str(new_width) + m.group(2), html, flags=re.DOTALL)

    # Simple text replacements
    html_content = replace_tag_content(html_content, "teacherFullName", teacher_name)
    html_content = replace_tag_content(html_content, "teacherEmail", teacher_email)
    html_content = replace_tag_content(html_content, "heroTeacherName", teacher_name)
    html_content = replace_tag_content(html_content, "heroTeacherEmail", teacher_email)
    
    html_content = replace_tag_content(html_content, "infoSessionCode", session_code)
    html_content = replace_tag_content(html_content, "infoSessionName", session_name)
    
    report_date = datetime.fromtimestamp(created_at).strftime('%d %b %Y')
    gen_time_str = datetime.now().strftime('%d %b %Y | %I:%M %p')
    html_content = replace_tag_content(html_content, "infoReportDate", report_date)
    html_content = replace_tag_content(html_content, "reportGenTime", gen_time_str)
    html_content = replace_tag_content(html_content, "infoSessionDuration", f"{duration_mins} min")
    
    # KPIs
    html_content = replace_tag_content(html_content, "kpiStudents", total_students)
    html_content = replace_tag_content(html_content, "kpiDuration", f"{duration_mins} min")
    html_content = replace_tag_content(html_content, "kpiTasks", total_tasks)
    html_content = replace_tag_content(html_content, "kpiAlerts", total_alerts)
    html_content = replace_tag_content(html_content, "donutTotalAlerts", total_alerts)
    
    # Alert Details
    html_content = replace_tag_content(html_content, "alertTabSwitches", total_tab_switches)
    html_content = replace_tag_content(html_content, "alertFaceMissing", total_face_missing)
    html_content = replace_tag_content(html_content, "alertMultiFace", total_multi_face)
    html_content = replace_tag_content(html_content, "alertDevTools", total_devtools)

    # Quality KPI and Subtext
    html_content = replace_tag_content(html_content, "kpiQuality", f"{quality_score_clamped}%")
    if quality_score_clamped >= 90:
        quality_text, quality_color = "Excellent", "var(--accent-green)"
    elif quality_score_clamped >= 75:
        quality_text, quality_color = "Good", "var(--gold)"
    else:
        quality_text, quality_color = "Fair", "var(--orange)"
    
    html_content = re.sub(
        r'(<div[^>]*\bid="kpiQualitySub"[^>]*>).*?(</div>)',
        lambda m: f'<div class="hero-kpi-sub" id="kpiQualitySub" style="color: {quality_color};">{quality_text}</div>',
        html_content,
        flags=re.DOTALL
    )

    # Attendance KPI
    html_content = replace_tag_content(html_content, "kpiAttendance", f"{overall_att_pct}%")
    html_content = replace_tag_content(html_content, "kpiAttendanceSub", f"{present_count} / {total_students} Students")

    # Risk counts
    html_content = replace_tag_content(html_content, "riskLow", f"{low_risk_count} ({risk_low_pct}%)")
    html_content = replace_tag_content(html_content, "riskMed", f"{med_risk_count} ({risk_med_pct}%)")
    html_content = replace_tag_content(html_content, "riskHigh", f"{high_risk_count} ({risk_high_pct}%)")
    
    html_content = replace_style_width(html_content, "riskBarLow", f"{risk_low_pct}%")
    html_content = replace_style_width(html_content, "riskBarMed", f"{risk_med_pct}%")
    html_content = replace_style_width(html_content, "riskBarHigh", f"{risk_high_pct}%")

    # Tasks Summary
    html_content = replace_tag_content(html_content, "taskPercent", f"{participation_pct}%")
    
    # Calculate completed, pending, not submitted tasks
    completed_submissions = 0
    for st in students_list:
        completed_submissions += st.get("total_answered", 0)
    pending_submissions = max(0, total_tasks * total_students - completed_submissions)
    not_submitted_submissions = sum(total_tasks for st in students_list if st.get("total_answered", 0) == 0)
    
    html_content = replace_tag_content(html_content, "summaryAssigned", total_tasks)
    html_content = replace_tag_content(html_content, "summaryCompleted", completed_submissions)
    html_content = replace_tag_content(html_content, "summaryPending", pending_submissions)
    html_content = replace_tag_content(html_content, "summaryNotSubmitted", not_submitted_submissions)

    # Topic Understanding
    html_content = replace_tag_content(html_content, "strongestTopicVal", strongest_topic_val)
    html_content = replace_tag_content(html_content, "weakestTopicVal", weakest_topic_val)

    # Engagement KPIs
    html_content = replace_tag_content(html_content, "engHigh", eng_high_val)
    html_content = replace_tag_content(html_content, "engMed", eng_med_val)
    html_content = replace_tag_content(html_content, "engLow", eng_low_val)
    html_content = replace_tag_content(html_content, "responseRateVal", f"{avg_response_rate}%")

    # HTML lists/tables replacements
    html_content = replace_tag_content(html_content, "firstToJoinList", first_html)
    html_content = replace_tag_content(html_content, "lateJoinersList", late_html)
    html_content = replace_tag_content(html_content, "topViolatorsList", violators_html)
    html_content = replace_tag_content(html_content, "needsAttentionList", attention_html)
    html_content = replace_tag_content(html_content, "mostActiveList", active_html)
    html_content = replace_tag_content(html_content, "aiSummaryText", ai_summary_text)
    html_content = replace_tag_content(html_content, "aiRecsList", ai_recs_html)
    html_content = replace_tag_content(html_content, "premiumGradebookBody", premium_gradebook_body)
    html_content = replace_tag_content(html_content, "topicProgressBars", topic_progress_bars)
    html_content = replace_tag_content(html_content, "taskPerformersRow", task_performers_row)
    html_content = replace_tag_content(html_content, "topPerformersOverviewContainer", rank_cards_html)

    # Set teacher initials in avatars
    initials_text = get_initials(teacher_name)
    html_content = replace_tag_content(html_content, "teacherAvatar", initials_text)
    html_content = replace_tag_content(html_content, "heroTeacherPhoto", initials_text)

    # Replace canvases with SVGs/Image
    html_content = re.sub(
        r'<canvas\s+id="presenceChart"[^>]*>.*?</canvas>',
        presence_chart_svg,
        html_content,
        flags=re.DOTALL
    )
    html_content = re.sub(
        r'<canvas\s+id="securityDonutChart"[^>]*>.*?</canvas>',
        security_donut_svg,
        html_content,
        flags=re.DOTALL
    )
    html_content = re.sub(
        r'<canvas\s+id="completionCircularChart"[^>]*>.*?</canvas>',
        completion_circular_svg,
        html_content,
        flags=re.DOTALL
    )
    html_content = re.sub(
        r'<canvas\s+id="engagementPieChart"[^>]*>.*?</canvas>',
        engagement_pie_svg,
        html_content,
        flags=re.DOTALL
    )
    html_content = re.sub(
        r'<canvas\s+id="responseRateChart"[^>]*>.*?</canvas>',
        response_rate_chart_svg,
        html_content,
        flags=re.DOTALL
    )
    html_content = re.sub(
        r'<canvas\s+id="qrCanvas"[^>]*>.*?</canvas>',
        qr_img_tag,
        html_content,
        flags=re.DOTALL
    )

    # 6. WeasyPrint rendering & Fallback
    # Write debug HTML to disk for verification screenshots
    try:
        debug_html_path = "C:\\Users\\robin\\.gemini\\antigravity\\brain\\f96eef2a-3c48-4fc0-9f72-5fdc252dccd8\\sample_report.html"
        os.makedirs(os.path.dirname(debug_html_path), exist_ok=True)
        with open(debug_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
    except Exception:
        pass

    # Define custom url_fetcher to block remote network calls in WeasyPrint (preventing hangs)
    def blocked_fetcher(url, timeout=1, ssl_context=None):
        if url.startswith("http://") or url.startswith("https://"):
            raise ValueError(f"Blocked network request: {url}")
        return weasyprint.default_url_fetcher(url, timeout, ssl_context)

    # Compile HTML to PDF using WeasyPrint with a 30.0s thread timeout
    def run_weasyprint():
        return weasyprint.HTML(string=html_content, url_fetcher=blocked_fetcher).write_pdf(font_config=weasyprint_font_config)

    import threading
    import queue
    q = queue.Queue()

    def worker():
        try:
            res = run_weasyprint()
            q.put((True, res))
        except Exception as err:
            q.put((False, err))

    t = threading.Thread(target=worker)
    t.daemon = True
    t.start()
    t.join(timeout=30.0)

    if not t.is_alive():
        ok, res = q.get()
        if ok:
            log.info("[PDF_GENERATOR] WeasyPrint generated PDF successfully!")
            return res
        else:
            log.warning("[PDF_GENERATOR] WeasyPrint failed: %s. Falling back to ReportLab...", res)
    else:
        log.warning("[PDF_GENERATOR] WeasyPrint timed out (took >30s). Falling back to ReportLab...")

    # ReportLab Fallback PDF Generator (guaranteed to generate in milliseconds)
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        import io

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        story = []
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=22,
            leading=26,
            textColor=colors.HexColor('#ffffff'),
            spaceAfter=15
        )

        h2_style = ParagraphStyle(
            'Heading2',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=13,
            leading=17,
            textColor=colors.HexColor('#D4AF37'), # Gold
            spaceBefore=12,
            spaceAfter=6
        )

        body_style = ParagraphStyle(
            'BodyText',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor('#f3f4f6') # Light white text
        )

        story.append(Paragraph(f"VYOM Session Intelligence Report", title_style))
        story.append(Spacer(1, 10))

        story.append(Paragraph(f"<b>Session Code:</b> {session_code}", body_style))
        story.append(Paragraph(f"<b>Teacher Name:</b> {teacher_name}", body_style))
        story.append(Paragraph(f"<b>Session Name:</b> {session_name}", body_style))
        story.append(Paragraph(f"<b>Date:</b> {report_date}", body_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("Classroom Performance Analytics", h2_style))
        story.append(Paragraph(f"<b>Average Understanding:</b> {understanding_pct}%", body_style))
        story.append(Paragraph(f"<b>Student Participation:</b> {participation_pct}%", body_style))
        story.append(Paragraph(f"<b>Total Connected Students:</b> {total_students}", body_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("Student Performance Details", h2_style))
        if students_list:
            data = [["Student Name", "Score", "Correct Answers", "Total Answered"]]
            for st in students_list:
                data.append([
                    st.get("name", "Student"),
                    f"{st.get('score', 0)}",
                    f"{st.get('correct', 0)}",
                    f"{st.get('total_answered', 0)}"
                ])
            t_table = Table(data, colWidths=[200, 100, 100, 100])
            t_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1f2937')), # Dark grey header
                ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#D4AF37')), # Gold text header
                ('TEXTCOLOR', (0,1), (-1,-1), colors.HexColor('#f3f4f6')), # Light text rows
                ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#111827')), # Dark cell background
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#374151')), # Subtle dark border
            ]))
            story.append(t_table)
        else:
            story.append(Paragraph("No student data recorded in this session.", body_style))

        # Background callback to paint the entire page dark
        def draw_background(canvas, doc):
            canvas.saveState()
            canvas.setFillColor(colors.HexColor('#05070f')) # Dark background
            canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=True, stroke=False)
            canvas.setFillColor(colors.HexColor('#D4AF37'))
            canvas.rect(0, doc.pagesize[1] - 8, doc.pagesize[0], 8, fill=True, stroke=False)
            canvas.restoreState()

        doc.build(story, onFirstPage=draw_background, onLaterPages=draw_background)
        buffer.seek(0)
        log.info("[PDF_GENERATOR] Successfully generated premium ReportLab fallback PDF!")
        return buffer.getvalue()
    except Exception as fallback_err:
        log.critical("[PDF_GENERATOR] CRITICAL ERROR: Both WeasyPrint and ReportLab failed: %s", fallback_err, exc_info=True)
        raise fallback_err

def create_session_report_pdf_old(report: dict) -> bytes:
    """Generate a highly polished, professional PDF report matching the dashboard's layout using WeasyPrint."""
    global weasyprint_font_config
    import os
    import sys
    import math
    import time
    from datetime import datetime

    # 1. Setup DLL paths for WeasyPrint on Windows
    if sys.platform == "win32":
        for path in ["C:\\msys64\\mingw64\\bin", "C:\\Users\\robin\\msys64\\mingw64\\bin", "C:\\Program Files\\Tesseract-OCR"]:
            if os.path.exists(path):
                if hasattr(os, "add_dll_directory"):
                    try:
                        os.add_dll_directory(path)
                    except Exception:
                        pass
                if path not in os.environ["PATH"]:
                    os.environ["PATH"] = path + os.path.pathsep + os.environ["PATH"]

    import weasyprint
    if weasyprint_font_config is None:
        try:
            from weasyprint.text.fonts import FontConfiguration
            weasyprint_font_config = FontConfiguration()
        except Exception:
            pass

    brand_name = report.get("brand_name", "ClassMind")
    teacher_name = report.get("teacher_name", "Dr. Rajesh Kumar")
    session_name = report.get("session_name", "Machine Learning Basics")
    session_code = report.get("session_code", report.get("code", "ML-4587"))
    created_at = report.get("created_at") or time.time()
    duration_mins = report.get("duration_mins") or 0
    date_str = datetime.fromtimestamp(created_at).strftime('%d %B %Y')
    
    started_at = report.get("started_at") or created_at
    start_time = datetime.fromtimestamp(started_at)
    end_time = datetime.fromtimestamp(started_at + duration_mins * 60)
    time_range = f"{start_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}"

    analytics = report.get("analytics", {})
    students_list = report.get("students", [])
    total_students = len(students_list) if students_list else analytics.get("total_students", 0)
    understanding = analytics.get("understanding", 0)
    participation = analytics.get("participation", 0)

    # 1. Join Analytics
    sorted_students = sorted(students_list, key=lambda x: x.get("joined_at", 0))
    first_joiners_html = ""
    late_joiners_html = ""
    presence_html = ""
    
    if not students_list:
        first_joiners_html = '<div style="font-size: 9px; color: var(--text-muted); padding: 5px 0;">Data not available</div>'
        late_joiners_html = '<div style="font-size: 9px; color: var(--text-muted); padding: 5px 0;">Data not available</div>'
        presence_html = '<div style="font-size: 9px; color: var(--text-muted); padding: 5px 0;">Data not available</div>'
    else:
        for idx, s in enumerate(sorted_students[:3]):
            join_t = s.get("joined_at") or started_at
            join_time_str = datetime.fromtimestamp(join_t).strftime('%I:%M %p')
            rank_class = f"rank-{idx+1}"
            first_joiners_html += f'''
            <div class="join-item">
              <div class="join-student"><span class="rank-badge {rank_class}">{idx+1}</span> {s.get("name", "Student")}</div>
              <span class="join-time">{join_time_str}</span>
            </div>
            '''
            
        late_joiners_list = []
        for s in students_list:
            join_t = s.get("joined_at") or started_at
            diff_mins = int((join_t - started_at) / 60)
            if diff_mins > 0:
                late_joiners_list.append((s.get("name", "Student"), diff_mins))
        
        late_joiners_list.sort(key=lambda x: x[1], reverse=True)
        for name, mins in late_joiners_list[:3]:
            late_joiners_html += f'''
            <div class="join-item">
              <div class="join-student">⚠️ {name}</div>
              <span class="join-time"><span class="late-badge">{mins}m late</span></span>
            </div>
            '''
        if not late_joiners_html:
            late_joiners_html = '<div style="font-size: 9px; color: var(--accent-green); padding: 3px 0; font-weight: 600;">No late joiners.</div>'

        for s in sorted_students[:5]:
            student_join = s.get("joined_at") or started_at
            student_dur_mins = min(duration_mins, max(0, duration_mins - int((student_join - started_at) / 60)))
            pct = min(100, max(0, int((student_dur_mins / duration_mins) * 100))) if duration_mins > 0 else 100
            presence_html += f'''
            <div style="margin-bottom: 6px;">
              <div style="display: flex; justify-content: space-between; font-size: 8px; font-weight: 600; margin-bottom: 2px;">
                <span>{s.get("name", "Student")}</span>
                <span style="color: var(--accent-blue);">{student_dur_mins}m</span>
              </div>
              <div style="height: 4px; background: rgba(255, 255, 255, 0.03); border-radius: 2px; overflow: hidden;">
                <div style="height: 100%; background: linear-gradient(90deg, #3b82f6, #60a5fa); border-radius: 2px; width: {pct}%;"></div>
              </div>
            </div>
            '''

    # 2. Security Warnings
    tab_switches = sum(s.get("warnings", {}).get("tab_switches", 0) for s in students_list)
    face_missing = sum(s.get("warnings", {}).get("face_missing", 0) for s in students_list)
    multi_face = sum(s.get("warnings", {}).get("multi_face", 0) for s in students_list)
    devtools = sum(s.get("warnings", {}).get("devtools", 0) for s in students_list)
    total_alerts = tab_switches + face_missing + multi_face + devtools

    low_risk, med_risk, high_risk = 0, 0, 0
    for s in students_list:
        warns = s.get("warnings", {})
        total_w = sum(warns.values()) if isinstance(warns, dict) else 0
        if total_w == 0:
            low_risk += 1
        elif total_w <= 2:
            med_risk += 1
        else:
            high_risk += 1

    # 3. Task Summary
    tasks_assigned = report.get("total_tasks", 0) or len(report.get("tasks", []))
    completed_cnt = sum(s.get("total_answered", 0) for s in students_list)
    
    pending_cnt = 0
    for s in students_list:
        short_attempts = s.get("short", {})
        long_attempts = s.get("long", {})
        short_list = short_attempts.get("attempts", []) if isinstance(short_attempts, dict) else []
        long_list = long_attempts.get("attempts", []) if isinstance(long_attempts, dict) else []
        for attempt in short_list + long_list:
            if attempt.get("evaluation_status") == "pending":
                pending_cnt += 1
                
    total_assigned = total_students * tasks_assigned
    not_sub_cnt = max(0, total_assigned - completed_cnt - pending_cnt)
    completion_pct = round((completed_cnt / total_assigned) * 100) if total_assigned > 0 else 0

    top_performers_cards_html = ""
    top_perf_html = ""
    top_performers_list = []
    
    if not students_list:
        top_performers_cards_html = '<div style="font-size: 8.5px; color: var(--text-muted); text-align: center; width: 100%;">Data not available</div>'
        top_perf_html = '<div style="font-size: 8.5px; color: var(--text-muted);">Data not available</div>'
    else:
        for s in students_list:
            score_val = s.get("score", 0)
            max_possible = tasks_assigned * 10
            pct_score = round((score_val / max_possible) * 100) if max_possible > 0 else 0
            top_performers_list.append({"name": s.get("name", "Student"), "score": pct_score})
        top_performers_list.sort(key=lambda x: x["score"], reverse=True)
        
        badges = ["rank-1", "rank-2", "rank-3"]
        for idx, tp in enumerate(top_performers_list[:3]):
            avatar_initials = tp["name"][:2].upper()
            top_performers_cards_html += f'''
            <div style="display: flex; flex-direction: column; align-items: center; width: 30%;">
              <div style="width: 22px; height: 22px; border-radius: 50%; background: #1e293b; border: 1.5px solid; display: flex; align-items: center; justify-content: center; font-size: 8px; font-weight: 700; color: #FFF;" class="{badges[idx]}">{avatar_initials}</div>
              <span style="font-size: 7.5px; margin-top: 2px; font-weight: 600; text-align: center; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 60px;">{tp["name"]}</span>
              <span style="font-size: 7.5px; color: var(--accent-green); font-weight: 700;">{tp["score"]}%</span>
            </div>
            '''
            
            rank_laurel = ["🥇", "🥈", "🥉"][idx]
            avatar_bg = ["#c084fc", "#fb7185", "#60a5fa"][idx]
            top_perf_html += f'''
            <div class="rank-card rank-card-{idx+1}">
              <span class="rank-laurel">{rank_laurel}</span>
              <div class="rank-avatar" style="background: {avatar_bg}; color: #FFF;">{avatar_initials}</div>
              <div class="rank-details">
                <span class="rank-name">{tp["name"]}</span>
                <span class="rank-score">{tp["score"]}% Score</span>
              </div>
            </div>
            '''

    # 4. Topic wise Understanding
    topic_confusion = analytics.get("topic_confusion", {})
    topic_scores = []
    for topic, stats in topic_confusion.items():
        total = stats.get("total", 0)
        if total > 0:
            wrong = stats.get("wrong", 0)
            pct = int((1 - (wrong / total)) * 100)
            topic_scores.append((topic, pct))
    topic_scores.sort(key=lambda x: x[1], reverse=True)

    topics_html = ""
    strongest_topic = "Data not available"
    weakest_topic = "Data not available"
    
    if not topic_scores:
        topics_html = '<div style="font-size: 8.5px; color: var(--text-muted);">Data not available</div>'
    else:
        for topic, pct in topic_scores[:3]:
            fill_class = "t-fill-green" if pct >= 80 else ("t-fill-blue" if pct >= 60 else "t-fill-orange")
            topics_html += f'''
            <div class="topic-progress-item">
              <div class="topic-info"><span>{topic}</span> <span>{pct}%</span></div>
              <div class="topic-bar-bg"><div class="topic-bar-fill {fill_class}" style="width: {pct}%;"></div></div>
            </div>
            '''
        strongest_topic = f"{topic_scores[0][0]} ({topic_scores[0][1]}%)"
        weakest_topic = f"{topic_scores[-1][0]} ({topic_scores[-1][1]}%)"

    attention_html = ""
    if not students_list:
        attention_html = '<div style="font-size: 8.5px; color: var(--text-muted);">Data not available</div>'
    else:
        sorted_for_attention = []
        for st in students_list:
            score_val = st.get("score", 0)
            ans_val = st.get("total_answered", 0)
            max_possible = ans_val * 10
            pct = round((score_val / max_possible) * 100) if max_possible > 0 else 0
            sorted_for_attention.append((st.get("name", "Student"), pct))
        sorted_for_attention.sort(key=lambda x: x[1])
        
        for name, pct in sorted_for_attention[:2]:
            attention_html += f'''
            <div class="topic-progress-item">
              <div class="topic-info"><span>{name}</span> <span style="color: var(--accent-red);">{pct}%</span></div>
              <div class="topic-bar-bg" style="height: 4px;"><div class="topic-bar-fill" style="width: {pct}%; background: var(--accent-red);"></div></div>
            </div>
            '''

    # 5. Engagement Donut & Trend
    eng_high, eng_med, eng_low = 0, 0, 0
    for s in students_list:
        ans = s.get("total_answered", 0)
        if tasks_assigned > 0:
            ratio = ans / tasks_assigned
            if ratio >= 0.75:
                eng_high += 1
            elif ratio >= 0.25:
                eng_med += 1
            else:
                eng_low += 1
        else:
            eng_high += 1

    most_active_html = ""
    if not students_list:
        most_active_html = '<div style="font-size: 8.5px; color: var(--text-muted);">Data not available</div>'
    else:
        most_active_list = [{"name": s.get("name", "Student"), "count": s.get("total_answered", 0)} for s in students_list]
        most_active_list.sort(key=lambda x: x["count"], reverse=True)
        for idx, ma in enumerate(most_active_list[:2]):
            most_active_html += f'''
            <div style="font-size: 8px; font-weight: 600; display: flex; justify-content: space-between; padding: 2px 0; color: #fff;">
              <span>{idx+1}. {ma["name"]}</span>
              <span style="color: var(--text-muted);">{ma["count"]} act</span>
            </div>
            '''

    participation_score = participation
    engagement_score = round(completed_cnt / total_assigned * 100) if total_assigned > 0 else 0
    discipline_score = max(0, 100 - total_alerts * 5) if total_students > 0 else 100
    understanding_score = understanding
    
    quality_score = round(participation_score * 0.2 + engagement_score * 0.3 + discipline_score * 0.2 + understanding_score * 0.3)
    if total_students == 0:
        quality_score = 0

    if total_students == 0:
        verdict_class = "verdict-neutral"
        verdict_title = "NO STUDENT DATA"
        verdict_desc = "No student activities were recorded in this session."
    elif quality_score >= 85:
        verdict_class = "verdict-excellent"
        verdict_title = "🏆 EXCELLENT SESSION STATUS"
        verdict_desc = f"Outstanding engagement, conceptual understanding of {understanding_score}%, and perfect discipline observed throughout the class."
    elif quality_score >= 70:
        verdict_class = "verdict-good"
        verdict_title = "📈 CONSTRUCTIVE SESSION STATUS"
        verdict_desc = f"Good conceptual participation. Students responded well, with moderate warning flags and {understanding_score}% average accuracy."
    else:
        verdict_class = "verdict-review"
        verdict_title = "⚠️ FOLLOW-UP REQUIRED"
        verdict_desc = f"High warning rates or low task scores ({understanding_score}% accuracy) indicate that additional conceptual revision is highly recommended."

    follow_up_students = []
    for s in students_list:
        score_val = s.get("score", 0)
        ans_val = s.get("total_answered", 0)
        max_possible = ans_val * 10
        pct = round((score_val / max_possible) * 100) if max_possible > 0 else 0
        warns = s.get("warnings", {})
        total_w = sum(warns.values()) if isinstance(warns, dict) else 0
        if pct < 60 or total_w > 0:
            follow_up_students.append({
                "name": s.get("name", "Student"),
                "accuracy": pct,
                "warnings": total_w,
                "reason": "Concept struggles" if pct < 60 and total_w == 0 else ("Engagement issues" if total_w > 0 and pct >= 60 else "Concept & Engagement")
            })
    follow_up_students.sort(key=lambda x: (x["accuracy"], -x["warnings"]))

    follow_up_html = ""
    if total_students == 0:
        follow_up_html = '<div style="font-size: 8.5px; color: var(--text-muted);">Data not available</div>'
    else:
        for f in follow_up_students[:2]:
            follow_up_html += f'''
            <div style="font-size: 8px; padding: 3px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.03); display: flex; justify-content: space-between; align-items: center; color: #fff;">
              <span>⚠️ <strong>{f["name"]}</strong> ({f["reason"]})</span>
              <span style="color: var(--accent-red); font-weight: 700;">{f["accuracy"]}% acc | {f["warnings"]} alerts</span>
            </div>
            '''
        if not follow_up_html:
            follow_up_html = '<div style="font-size: 8.5px; color: var(--accent-green); padding: 3px 0; font-weight: 600;">No follow-up required.</div>'

    improved_students = []
    tasks_list = report.get("tasks", [])
    has_sufficient_history = False
    
    if len(tasks_list) >= 2:
        for s in students_list:
            sid = s.get("id") or s.get("student_id")
            if not sid:
                continue
            attempts_correctness = []
            for t in tasks_list:
                tid = t.get("id")
                resp = report.get("responses", {}).get(tid, {}).get(sid)
                if resp and resp.get("evaluation_status") in ("approved", "evaluated"):
                    attempts_correctness.append(1 if resp.get("correct", False) else 0)
            if len(attempts_correctness) >= 2:
                has_sufficient_history = True
                mid = len(attempts_correctness) // 2
                first_half = attempts_correctness[:mid]
                second_half = attempts_correctness[mid:]
                acc1 = sum(first_half) / len(first_half)
                acc2 = sum(second_half) / len(second_half)
                if acc2 > acc1:
                    diff_pct = round((acc2 - acc1) * 100)
                    improved_students.append((s.get("name"), diff_pct))
        improved_students.sort(key=lambda x: x[1], reverse=True)

    improved_html = ""
    if total_students == 0:
        improved_html = '<div style="font-size: 8.5px; color: var(--text-muted);">Data not available</div>'
    elif not has_sufficient_history:
        improved_html = '<div style="font-size: 8px; color: var(--text-muted); line-height: 1.3;">Needs 2+ tasks history.</div>'
    else:
        for name, diff in improved_students[:2]:
            improved_html += f'''
            <div style="font-size: 8px; padding: 3px 0; border-bottom: 1px solid rgba(255, 255, 255, 0.03); display: flex; justify-content: space-between; align-items: center; color: #fff;">
              <span>📈 <strong>{name}</strong></span>
              <span style="color: var(--accent-green); font-weight: 700;">+{diff}% progression</span>
            </div>
            '''
        if not improved_html:
            improved_html = '<div style="font-size: 8.5px; color: var(--text-muted); padding: 3px 0;">No progression detected.</div>'

    recs = []
    if total_students > 0:
        struggling = [f for f in follow_up_students if "Concept" in f["reason"]]
        if struggling:
            struggling_names = ", ".join([f["name"] for f in struggling[:2]])
            recs.append(f"Schedule a focused concept review for <strong>{struggling_names}</strong> to clarify topic weak spots.")
        
        distracted = [f for f in follow_up_students if "Engagement" in f["reason"] or "Concept & Engagement" in f["reason"]]
        if distracted:
            distracted_names = ", ".join([f["name"] for f in distracted[:2]])
            recs.append(f"Conduct checks on tab-switches or warning counts for <strong>{distracted_names}</strong>.")

        if topic_scores:
            weakest = topic_scores[-1]
            if weakest[1] < 70:
                recs.append(f"Review student mistakes in <strong>{weakest[0]}</strong> ({weakest[1]}% accuracy) before launching next topic.")
    
    if not recs:
        if total_students == 0:
            recs.append("Data not available for this session")
        else:
            recs.append("All students performed exceptionally. Introduce advanced challenge concepts in next session.")

    summary_parts = []
    if total_students == 0:
        ai_summary_txt = "Data not available for this session"
    else:
        if participation_score >= 85:
            summary_parts.append(f"The session had highly active participation at {participation_score}%.")
        else:
            summary_parts.append(f"Participation was moderate at {participation_score}%, indicating room for additional attendance follow-ups.")
            
        if understanding_score >= 80:
            summary_parts.append(f"Class understanding was strong overall, averaging {understanding_score}% concept accuracy.")
        else:
            summary_parts.append(f"The class conceptual understanding averaged {understanding_score}%, suggesting reinforcement in key areas.")
            
        if total_alerts > 0:
            summary_parts.append(f"Class discipline was impacted by {total_alerts} security alerts.")
        else:
            summary_parts.append("Perfect class discipline was maintained with zero warnings.")
            
        if topic_scores:
            summary_parts.append(f"Students excelled in {strongest_topic}, while showing confusion on {weakest_topic}.")
        
        ai_summary_txt = " ".join(summary_parts)

    def _make_circular_progress_svg(pct):
        return f'''
        <svg width="45" height="45" viewBox="0 0 36 36" style="display: block; margin: auto;">
          <circle cx="18" cy="18" r="15" fill="none" stroke="rgba(255, 255, 255, 0.04)" stroke-width="3.5" />
          <circle cx="18" cy="18" r="15" fill="none" stroke="#10b981" stroke-width="3.5" stroke-linecap="round"
                  pathLength="100" stroke-dasharray="{pct} {100 - pct}" transform="rotate(-90 18 18)" />
        </svg>
        '''

    def _make_donut_svg(segments, colors, size=70, stroke_width=7):
        total = sum(segments)
        r = (size - stroke_width) / 2
        if total == 0:
            return f'<svg width="{size}" height="{size}"><circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="rgba(255,255,255,0.04)" stroke-width="{stroke_width}" /></svg>'
        svg = f'<svg width="{size}" height="{size}" viewBox="0 0 {size} {size}" style="display: block; margin: auto;">'
        accum = 0.0
        for val, color in zip(segments, colors):
            if val <= 0:
                continue
            pct = val / total
            dash_len = pct * 100
            space_len = 100 - dash_len
            offset = -accum * 100
            svg += f'<circle cx="{size/2}" cy="{size/2}" r="{r}" fill="none" stroke="{color}" stroke-width="{stroke_width}" pathLength="100" stroke-dasharray="{dash_len} {space_len}" stroke-dashoffset="{offset}" transform="rotate(-90 {size/2} {size/2})" />'
            accum += pct
        svg += '</svg>'
        return svg

    def _make_line_chart_svg(values, width=130, height=36):
        if not values:
            return f'''<svg width="100%" height="100%" viewBox="0 0 {width} {height}" style="display: flex; align-items: center; justify-content: center;"><text x="50%" y="50%" dominant-baseline="middle" text-anchor="middle" fill="var(--text-muted)" font-size="8">N/A</text></svg>'''
        
        n = len(values)
        if n == 1:
            values = [values[0], values[0]]
            n = 2
            
        min_v = min(values)
        max_v = max(values)
        if min_v == max_v:
            min_v = max(0, min_v - 10)
            max_v = min(100, max_v + 10)
            
        coords = []
        for i, v in enumerate(values):
            x = 5 + i * (width - 10) / (n - 1)
            y = height - 5 - (v - min_v) * (height - 10) / (max_v - min_v)
            coords.append((x, y))
        line_path = "M " + " L ".join(f"{x},{y}" for x, y in coords)
        area_path = f"M {coords[0][0]},{height - 2} " + " ".join(f"L {x},{y}" for x, y in coords) + f" L {coords[-1][0]},{height - 2} Z"
        svg = f'''
        <svg width="100%" height="100%" viewBox="0 0 {width} {height}" style="display: block;">
          <defs>
            <linearGradient id="lineGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stop-color="rgba(16, 185, 129, 0.25)" />
              <stop offset="100%" stop-color="rgba(16, 185, 129, 0.0)" />
            </linearGradient>
          </defs>
          <path d="{area_path}" fill="url(#lineGrad)" />
          <path d="{line_path}" fill="none" stroke="#10b981" stroke-width="1.5" />
          {" ".join(f'<circle cx="{x}" cy="{y}" r="1.5" fill="#10b981" stroke="#050B1A" stroke-width="0.5" />' for x, y in coords)}
        </svg>
        '''
        return svg

    completion_svg_str = _make_circular_progress_svg(completion_pct)
    security_donut_svg_str = _make_donut_svg(
        [tab_switches, face_missing, multi_face, devtools],
        ["#ef4444", "#f59e0b", "#3b82f6", "#10b981"],
        size=60, stroke_width=6
    )
    engagement_donut_svg_str = _make_donut_svg([eng_high, eng_med, eng_low], ["#10b981", "#3b82f6", "#ef4444"], size=45, stroke_width=4.5)
    
    task_accuracies = [t["accuracy"] for t in report.get("question_stats", [])]
    line_chart_svg_str = _make_line_chart_svg(task_accuracies)


    # --- Start Premium Gradebook & AI Recs Computation ---
    ai_recs_html = ""
    for r in recs:
        ai_recs_html += f'''
        <div class="ai-rec-item">
          <span class="ai-rec-check">✓</span>
          <span class="ai-text">{r}</span>
        </div>
        '''

    # Calculate overall attendance percentage
    att = s.get("attendance", {}) if (s := (locals().get("s") or (globals().get("sessions", {}).get(session_code) if "sessions" in globals() else None))) else {}
    records = att.get("records", {}) if att else {}
    total_active_students = len([st for st in s.get("students", {}).values() if st.get("status") == "active"]) if s else 0
    present_count = sum(1 for r in records.values() if r.get("status") in ("present", "exited"))
    attendance_percentage = round((present_count / max(1, total_active_students)) * 100) if total_active_students > 0 else 0

    # Calculate overall quality score
    quality_score = round((understanding * 0.55) + (participation * 0.3) + (max(0, 100 - total_alerts * 2) * 0.15))
    quality_score = max(0, min(100, quality_score))

    # Calculate teacher initials
    teacher_initials = "".join([w[0].upper() for w in teacher_name.split()[:2]]) if teacher_name else "T"

    # Compute student gradebook rows for Page 3
    gradebook_rows_html = ""
    students_gradebook = []
    
    leaderboard = report.get("leaderboard", [])
    total_tasks = report.get("total_tasks", 0)
    
    from store import sessions
    raw_s = sessions.get(session_code)
    
    for idx, st in enumerate(students_list):
        sid = st["student_id"]
        student_obj = raw_s["students"].get(sid, {}) if raw_s and "students" in raw_s else {}
        
        roll_no = student_obj.get("roll_no") or student_obj.get("roll") or f"R-{idx+1:02d}"
        class_name = student_obj.get("class_name") or student_obj.get("class") or session_name
        
        task_correct = st.get("correct", 0)
        task_attempts = st.get("total_attempts", 0)
        task_score = int((task_correct / max(task_attempts, 1)) * 100) if task_attempts > 0 else 0
        
        test_score = None
        for entry in leaderboard:
            if entry.get("student_id") == sid:
                test_score = entry.get("score")
                break
        
        coding_score = student_obj.get("coding_score") if student_obj.get("coding_submitted") else None
        
        scores = []
        if total_tasks > 0:
            scores.append(task_score)
        if test_score is not None:
            scores.append(test_score)
        if coding_score is not None:
            scores.append(coding_score)
            
        overall_percentage = int(sum(scores) / len(scores)) if scores else 0
        
        # Attendance calculation
        att_rec = raw_s.get("attendance", {}).get("records", {}).get(sid, {}) if raw_s else {}
        att_pct = 100
        if att_rec:
            status = att_rec.get("status", "not_marked")
            duration = att_rec.get("duration", 0)
            if status == "present":
                if duration > 0 and duration_mins > 0:
                    att_pct = min(100, max(0, round((duration / 60 / duration_mins) * 100)))
                else:
                    att_pct = 100
            elif status == "exited" and duration > 0 and duration_mins > 0:
                att_pct = min(100, max(0, round((duration / 60 / duration_mins) * 100)))
            elif status in ("not_marked", "absent", "revoked"):
                att_pct = 0
        else:
            joined_at = st.get("joined_at", 0)
            created_at = report.get("created_at") or time.time()
            started_at = report.get("started_at") or created_at
            session_started_at = started_at
            if joined_at > 0 and session_started_at > 0 and duration_mins > 0:
                elapsed = (session_started_at + duration_mins * 60) - joined_at
                if elapsed > 0:
                    att_pct = min(100, max(0, round((elapsed / (duration_mins * 60)) * 100)))
        
        students_gradebook.append({
            "name": st.get("name", "Student"),
            "roll_no": roll_no,
            "class_name": class_name,
            "task_score": task_score,
            "test_score": test_score,
            "coding_score": coding_score,
            "attendance": att_pct,
            "overall_percentage": overall_percentage
        })
        
    students_gradebook.sort(key=lambda x: x["overall_percentage"], reverse=True)
    
    for idx, row in enumerate(students_gradebook):
        rank = idx + 1
        test_score_str = f"{row['test_score']}%" if row['test_score'] is not None else "—"
        coding_score_str = f"{row['coding_score']}%" if row['coding_score'] is not None else "—"
        gradebook_rows_html += f'''
        <tr>
          <td style="text-align: center; font-weight: bold; color: #D4AF37;">#{rank}</td>
          <td style="font-weight: bold; color: #FFFFFF;">{row['name']}</td>
          <td style="font-family: monospace; color: #A0A0A0;">{row['roll_no']}</td>
          <td>{row['class_name']}</td>
          <td style="text-align: center;">{row['task_score']}%</td>
          <td style="text-align: center;">{test_score_str}</td>
          <td style="text-align: center;">{coding_score_str}</td>
          <td style="text-align: center; font-weight: bold; color: #D4AF37;">{row['attendance']}%</td>
          <td style="text-align: center; font-weight: 800; color: #22c55e;">{row['overall_percentage']}%</td>
        </tr>
        '''
        
    if not gradebook_rows_html:
        gradebook_rows_html = '<tr><td colspan="9" style="text-align: center; padding: 24px; color: #A0A0A0;">No student marks records found.</td></tr>'
    # --- End Premium Gradebook & AI Recs Computation ---

    engagement_badge_html = ""
    if total_assigned == 0:
        engagement_badge_html = '<span style="font-size: 6px; background: rgba(255, 255, 255, 0.05); color: var(--text-muted); padding: 1px 3px; border-radius: 2px; font-weight: bold; text-transform: uppercase;">N/A</span>'
    elif engagement_score >= 80:
        engagement_badge_html = '<span style="font-size: 6px; background: rgba(16, 185, 129, 0.1); color: var(--accent-green); padding: 1px 3px; border-radius: 2px; font-weight: bold; text-transform: uppercase;">Excellent</span>'
    elif engagement_score >= 60:
        engagement_badge_html = '<span style="font-size: 6px; background: rgba(59, 130, 246, 0.1); color: var(--accent-blue); padding: 1px 3px; border-radius: 2px; font-weight: bold; text-transform: uppercase;">Good</span>'
    else:
        engagement_badge_html = '<span style="font-size: 6px; background: rgba(239, 68, 68, 0.1); color: var(--accent-red); padding: 1px 3px; border-radius: 2px; font-weight: bold; text-transform: uppercase;">Low</span>'

    # Auto-detect brand
    current_filepath = os.path.abspath(__file__)
    is_classmind = "Classmind-main\\Classmind-main" in current_filepath or "Classmind-main/Classmind-main" in current_filepath
    default_brand = "ClassMind" if is_classmind else "VYOM"
    brand_name = report.get("brand_name", default_brand)

    html_content = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{brand_name} Session Intelligence Report</title>
  <style>
    :root {{
      --bg: #050505;
      --card: #111111;
      --card2: #151515;
      --orange: #FF7A00;
      --orange2: #FF9A1F;
      --gold: #D4AF37;
      --gold-border: rgba(212,175,55,0.22);
      --text: #FFFFFF;
      --text-muted: #A0A0A0;
      --accent-green: #22c55e;
      --accent-red: #ef4444;
    }}
    
    @page {{
      size: A4 portrait;
      margin: 8mm;
    }}
    
    * {{
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    
    body {{
      background-color: #050505;
      color: #FFFFFF;
      font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
      font-size: 8.5pt;
      line-height: 1.35;
    }}
    
    .page {{
      width: 100%;
      height: 280mm;
      page-break-after: always;
      box-sizing: border-box;
    }}
    
    .page:last-child {{
      page-break-after: avoid;
    }}
    
    /* Layout Tables */
    .table-layout {{
      width: 100%;
      border-collapse: collapse;
      border: none;
    }}
    
    /* Header Table */
    .header-table {{
      width: 100%;
      border-collapse: collapse;
      border-bottom: 1px solid rgba(212,175,55,0.22);
      margin-bottom: 8px;
    }}
    .logo-td {{
      width: 30%;
      padding-bottom: 6px;
    }}
    .title-td {{
      width: 45%;
      text-align: center;
      padding-bottom: 6px;
    }}
    .title-text {{
      font-size: 13pt;
      font-weight: 800;
      color: #FFFFFF;
      letter-spacing: 0.5px;
    }}
    .title-sub {{
      font-size: 6.5pt;
      color: #D4AF37;
      text-transform: uppercase;
      letter-spacing: 1px;
    }}
    .id-td {{
      width: 25%;
      text-align: right;
      padding-bottom: 6px;
    }}
    .id-box {{
      background: #111111;
      border: 1px solid rgba(212,175,55,0.22);
      border-radius: 6px;
      padding: 4px 8px;
      display: inline-block;
      text-align: right;
    }}
    .id-lbl {{
      font-size: 6pt;
      color: #A0A0A0;
      text-transform: uppercase;
      display: block;
    }}
    .id-val {{
      font-size: 9pt;
      font-weight: 700;
      color: #D4AF37;
    }}
    
    /* Verdict Card */
    .verdict-table {{
      width: 100%;
      border-collapse: collapse;
      border-radius: 6px;
      margin-bottom: 8px;
    }}
    .verdict-td {{
      padding: 8px 12px;
      border-left: 4px solid #22c55e;
    }}
    .verdict-excellent {{
      background: rgba(34, 197, 94, 0.06);
      border: 1px solid rgba(34, 197, 94, 0.15);
    }}
    .verdict-excellent .verdict-td {{ border-left-color: #22c55e; }}
    .verdict-excellent h3 {{ color: #22c55e; }}
    
    .verdict-good {{
      background: rgba(212, 175, 55, 0.06);
      border: 1px solid rgba(212, 175, 55, 0.15);
    }}
    .verdict-good .verdict-td {{ border-left-color: #D4AF37; }}
    .verdict-good h3 {{ color: #D4AF37; }}
    
    .verdict-review {{
      background: rgba(239, 68, 68, 0.06);
      border: 1px solid rgba(239, 68, 68, 0.15);
    }}
    .verdict-review .verdict-td {{ border-left-color: #ef4444; }}
    .verdict-review h3 {{ color: #ef4444; }}
    
    .verdict-neutral {{
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid rgba(212,175,55,0.22);
    }}
    .verdict-neutral .verdict-td {{ border-left-color: #A0A0A0; }}
    .verdict-neutral h3 {{ color: #A0A0A0; }}
    
    .verdict-title {{
      font-size: 9.5pt;
      font-weight: bold;
      margin-bottom: 2px;
    }}
    .verdict-desc {{
      font-size: 8pt;
      color: #FFFFFF;
    }}
    
    /* Info Bar Table */
    .info-bar-table {{
      width: 100%;
      border-collapse: collapse;
      background: #111111;
      border: 1px solid rgba(212,175,55,0.22);
      border-radius: 8px;
      margin-bottom: 8px;
    }}
    .info-item-td {{
      width: 16.66%;
      padding: 6px 8px;
      border-right: 1px solid rgba(212,175,55,0.08);
    }}
    .info-item-td:last-child {{
      border-right: none;
    }}
    .info-val {{
      font-size: 8pt;
      font-weight: bold;
      color: #FFFFFF;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 90px;
    }}
    .info-lbl {{
      font-size: 6.5pt;
      color: #A0A0A0;
      text-transform: uppercase;
    }}
    
    /* KPI Cards */
    .kpi-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 6px 0;
      margin-left: -6px;
      margin-right: -6px;
      margin-bottom: 8px;
    }}
    .kpi-td {{
      width: 20%;
      vertical-align: top;
    }}
    .kpi-card {{
      background: #111111;
      border: 1px solid rgba(212,175,55,0.22);
      border-radius: 8px;
      padding: 8px;
    }}
    .kpi-val {{
      font-size: 13pt;
      font-weight: 800;
      display: block;
      color: #D4AF37;
    }}
    .kpi-lbl {{
      font-size: 6.5pt;
      color: #A0A0A0;
      text-transform: uppercase;
      display: block;
    }}
    
    /* Section Cards */
    .section-td {{
      width: 50%;
      padding: 4px;
      vertical-align: top;
    }}
    .section-card {{
      background: #111111;
      border: 1px solid rgba(212,175,55,0.22);
      border-radius: 8px;
      padding: 10px;
      height: 175mm;
    }}
    .section-header {{
      border-bottom: 1px solid rgba(212,175,55,0.08);
      padding-bottom: 4px;
      margin-bottom: 8px;
    }}
    .section-title {{
      font-size: 8.5pt;
      font-weight: bold;
      color: #FFFFFF;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    
    /* Sub Panels inside Sections */
    .panel-table {{
      width: 100%;
      border-collapse: separate;
      border-spacing: 4px 0;
      margin-bottom: 8px;
    }}
    .panel-td {{
      width: 50%;
      vertical-align: top;
    }}
    .inner-panel {{
      background: #151515;
      border: 1px solid rgba(212,175,55,0.08);
      border-radius: 6px;
      padding: 6px;
    }}
    .panel-title {{
      font-size: 7.5pt;
      font-weight: bold;
      text-transform: uppercase;
      margin-bottom: 4px;
    }}
    
    /* Lists and items */
    .list-item {{
      font-size: 8pt;
      padding: 2.5px 0;
      border-bottom: 1px solid rgba(212,175,55,0.06);
    }}
    .list-item:last-child {{
      border-bottom: none;
    }}
    
    /* Join List item styles */
    .join-item {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 0;
      border-bottom: 1px solid rgba(212,175,55,0.06);
      font-size: 8pt;
    }}
    .join-item:last-child {{
      border-bottom: none;
    }}
    .join-student {{
      display: flex;
      align-items: center;
      gap: 4px;
      font-weight: 600;
      color: #FFFFFF;
    }}
    .rank-badge {{
      display: inline-block;
      width: 14px;
      height: 14px;
      border-radius: 50%;
      text-align: center;
      line-height: 14px;
      font-size: 7pt;
      font-weight: 700;
      margin-right: 4px;
    }}
    .rank-1 {{ background: rgba(212,175,55,0.2); color: #D4AF37; border: 1px solid #D4AF37; }}
    .rank-2 {{ background: rgba(160,160,160,0.15); color: #bbb; border: 1px solid #888; }}
    .rank-3 {{ background: rgba(180,100,20,0.2); color: #cd7f32; border: 1px solid #cd7f32; }}
    .join-time {{
      font-size: 7.5pt;
      color: #A0A0A0;
    }}
    .late-badge {{
      background: rgba(239,68,68,0.1);
      color: #ef4444;
      font-size: 6.5pt;
      padding: 1px 4px;
      border-radius: 3px;
      border: 1px solid rgba(239,68,68,0.2);
    }}
    
    /* Conic Ring Teacher avatar */
    .hero-photo-ring {{
      width: 60px;
      height: 60px;
      border-radius: 50%;
      background: conic-gradient(#FF7A00 0deg, #D4AF37 90deg, #FF9A1F 180deg, #D4AF37 270deg, #FF7A00 360deg);
      padding: 2.5px;
      margin: auto;
    }}
    .hero-photo-ring-inner {{
      width: 100%;
      height: 100%;
      border-radius: 50%;
      background: #111111;
      display: flex;
      align-items: center;
      justify-content: center;
      font-weight: 800;
      color: #FFFFFF;
      font-size: 14pt;
    }}
    
    /* Circular Progress */
    .circular-progress-wrapper {{
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
    }}
    
    /* AI Boxes */
    .ai-summary-box {{
      background: rgba(212, 175, 55, 0.03);
      border: 1px solid rgba(212, 175, 55, 0.15);
      border-left: 3px solid #D4AF37;
      border-radius: 8px;
      padding: 8px 10px;
      margin-bottom: 8px;
    }}
    .ai-title {{
      font-size: 7.5pt;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 4px;
    }}
    .ai-title.summary {{ color: #D4AF37; }}
    .ai-title.recs {{ color: #FF7A00; }}
    
    .ai-text {{
      font-size: 8pt;
      line-height: 1.35;
      color: #FFFFFF;
    }}
    .ai-recs-box {{
      background: rgba(255, 122, 0, 0.03);
      border: 1px solid rgba(255, 122, 0, 0.15);
      border-radius: 8px;
      padding: 8px 10px;
    }}
    .ai-rec-item {{
      display: flex;
      align-items: flex-start;
      gap: 5px;
      font-size: 8pt;
      margin-bottom: 4px;
    }}
    .ai-rec-item:last-child {{
      margin-bottom: 0;
    }}
    .ai-rec-check {{
      color: #D4AF37;
      font-weight: bold;
      font-size: 8pt;
    }}
    
    /* Rank cards for top performers */
    .rank-card {{
      background: #151515;
      border: 1px solid rgba(212,175,55,0.08);
      border-radius: 6px;
      padding: 4px 8px;
      display: flex;
      align-items: center;
      margin-bottom: 4px;
    }}
    .rank-laurel {{
      font-size: 11pt;
      margin-right: 6px;
    }}
    .rank-avatar {{
      width: 18px;
      height: 18px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 7pt;
      font-weight: 700;
      margin-right: 8px;
      border: 1px solid rgba(212,175,55,0.22);
    }}
    .rank-details {{
      flex: 1;
    }}
    .rank-name {{
      font-size: 8pt;
      font-weight: bold;
      color: #FFFFFF;
      display: block;
    }}
    .rank-score {{
      font-size: 7pt;
      color: #FF7A00;
      font-weight: 600;
    }}
    
    /* Topic bars */
    .topic-progress-item {{
      margin-bottom: 5px;
    }}
    .topic-info {{
      display: flex;
      justify-content: space-between;
      font-size: 7.5pt;
      font-weight: 600;
      color: #FFFFFF;
      margin-bottom: 2px;
    }}
    .topic-bar-bg {{
      height: 4px;
      background: rgba(255, 255, 255, 0.03);
      border-radius: 2px;
      overflow: hidden;
    }}
    .topic-bar-fill {{
      height: 100%;
      border-radius: 2px;
    }}
    .t-fill-green {{ background: linear-gradient(90deg, #22c55e, #4ade80); }}
    .t-fill-blue {{ background: linear-gradient(90deg, #D4AF37, #F2D16B); }}
    .t-fill-orange {{ background: linear-gradient(90deg, #FF7A00, #FF9A1F); }}
    
    /* Footer Box */
    .gen-box-table {{
      width: 100%;
      border-collapse: collapse;
      background: #111111;
      border: 1px solid rgba(212,175,55,0.22);
      border-radius: 6px;
      margin-top: 6px;
      margin-bottom: 4px;
    }}
    .gen-box-td {{
      padding: 6px 12px;
      vertical-align: middle;
    }}
    .gen-logo-text {{
      font-size: 9pt;
      font-weight: bold;
      color: #FFFFFF;
    }}
    .gen-engine {{
      font-size: 7pt;
      color: #A0A0A0;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .gen-time {{
      font-size: 7.5pt;
      color: #A0A0A0;
    }}
    
    footer {{
      border-top: 1px solid rgba(255, 255, 255, 0.04);
      padding-top: 4px;
      text-align: center;
    }}
    .footer-tagline {{
      font-size: 7pt;
      color: #D4AF37;
      text-transform: uppercase;
      font-weight: bold;
      letter-spacing: 0.5px;
    }}
    
    /* Gradebook Table Styling */
    .gradebook-card {{
      background: #111111;
      border: 1px solid rgba(212,175,55,0.22);
      border-radius: 8px;
      padding: 12px;
      min-height: 235mm;
    }}
    .gradebook-table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 8px;
      font-size: 7.5pt;
    }}
    .gradebook-table th {{
      background: #151515;
      border-bottom: 2px solid rgba(212,175,55,0.22);
      color: #D4AF37;
      text-transform: uppercase;
      font-weight: bold;
      padding: 6px 4px;
      font-size: 7pt;
      letter-spacing: 0.5px;
    }}
    .gradebook-table td {{
      padding: 6px 4px;
      border-bottom: 1px solid rgba(212,175,55,0.06);
      color: #FFFFFF;
    }}
    .gradebook-table tr:nth-child(even) td {{
      background: rgba(255, 255, 255, 0.01);
    }}
  </style>
</head>
<body>
  
  <!-- PAGE 1 -->
  <div class="page">
    <table class="header-table">
      <tr>
        <td class="logo-td" style="vertical-align: middle;">
          <table style="border-collapse: collapse; border: none;">
            <tr>
              <td style="padding-right: 8px; vertical-align: middle;">
                <svg width="24" height="24" viewBox="0 0 44 44" fill="none">
                  <path d="M22 2C10.95 2 2 10.95 2 22s8.95 20 20 20 20-8.95 20-20S33.05 2 22 2zm0 36c-8.82 0-16-7.18-16-16S13.18 6 22 6s16 7.18 16 16-7.18 16-16 16z" fill="#FF7A00"/>
                  <circle cx="22" cy="22" r="8" fill="#D4AF37"/>
                </svg>
              </td>
              <td style="vertical-align: middle; line-height: 1;">
                <div style="font-family: 'Poppins', sans-serif; font-size: 15pt; font-weight: 900; letter-spacing: 2px; color: #FFF; margin: 0; line-height: 1;">{brand_name.upper()}</div>
                <div style="font-size: 5.5pt; font-weight: 700; letter-spacing: 1.5px; color: #D4AF37; text-transform: uppercase; margin-top: 1px;">AI Classroom</div>
              </td>
            </tr>
          </table>
        </td>
        <td class="title-td" style="vertical-align: middle;">
          <div class="title-text">SESSION INTELLIGENCE REPORT</div>
          <div class="title-sub">AI Powered Classroom Analytics</div>
        </td>
        <td class="id-td" style="vertical-align: middle;">
          <div class="id-box">
            <span class="id-lbl">Report ID</span>
            <span class="id-val">{session_code}</span>
          </div>
        </td>
      </tr>
    </table>

    <table class="verdict-table {verdict_class}">
      <tr>
        <td class="verdict-td">
          <div class="verdict-title">{verdict_title}</div>
          <div class="verdict-desc">{verdict_desc}</div>
        </td>
      </tr>
    </table>

    <table class="info-bar-table">
      <tr>
        <td class="info-item-td">
          <div class="info-val">{teacher_name}</div>
          <div class="info-lbl">Teacher</div>
        </td>
        <td class="info-item-td">
          <div class="info-val">{session_name}</div>
          <div class="info-lbl">Session Name</div>
        </td>
        <td class="info-item-td">
          <div class="info-val">{session_code}</div>
          <div class="info-lbl">Session Code</div>
        </td>
        <td class="info-item-td">
          <div class="info-val">{date_str}</div>
          <div class="info-lbl">Date</div>
        </td>
        <td class="info-item-td">
          <div class="info-val">{time_range}</div>
          <div class="info-lbl">Time</div>
        </td>
        <td class="info-item-td">
          <div class="info-val">{duration_mins} min</div>
          <div class="info-lbl">Duration</div>
        </td>
      </tr>
    </table>

    <table class="kpi-table">
      <tr>
        <td class="kpi-td">
          <div class="kpi-card" style="border-top: 2px solid #FF7A00;">
            <table style="width: 100%;">
              <tr>
                <td style="width: 20px; font-size: 11pt; vertical-align: middle; text-align: center; color: #FF7A00;">👥</td>
                <td>
                  <span class="kpi-val">{total_students}</span>
                  <span class="kpi-lbl">Students</span>
                </td>
              </tr>
            </table>
          </div>
        </td>
        <td class="kpi-td">
          <div class="kpi-card" style="border-top: 2px solid #D4AF37;">
            <table style="width: 100%;">
              <tr>
                <td style="width: 20px; font-size: 11pt; vertical-align: middle; text-align: center; color: #D4AF37;">⏱️</td>
                <td>
                  <span class="kpi-val">{duration_mins}m</span>
                  <span class="kpi-lbl">Duration</span>
                </td>
              </tr>
            </table>
          </div>
        </td>
        <td class="kpi-td">
          <div class="kpi-card" style="border-top: 2px solid #FF7A00;">
            <table style="width: 100%;">
              <tr>
                <td style="width: 20px; font-size: 11pt; vertical-align: middle; text-align: center; color: #FF7A00;">📝</td>
                <td>
                  <span class="kpi-val">{tasks_assigned}</span>
                  <span class="kpi-lbl">Tasks</span>
                </td>
              </tr>
            </table>
          </div>
        </td>
        <td class="kpi-td">
          <div class="kpi-card" style="border-top: 2px solid #ef4444;">
            <table style="width: 100%;">
              <tr>
                <td style="width: 20px; font-size: 11pt; vertical-align: middle; text-align: center; color: #ef4444;">🚨</td>
                <td>
                  <span class="kpi-val" style="color: #ef4444;">{total_alerts}</span>
                  <span class="kpi-lbl">Alerts</span>
                </td>
              </tr>
            </table>
          </div>
        </td>
        <td class="kpi-td">
          <div class="kpi-card" style="border-top: 2px solid #22c55e;">
            <table style="width: 100%;">
              <tr>
                <td style="width: 20px; font-size: 11pt; vertical-align: middle; text-align: center; color: #22c55e;">📈</td>
                <td>
                  <span class="kpi-val" style="color: #22c55e;">{attendance_percentage}%</span>
                  <span class="kpi-lbl">Attendance</span>
                </td>
              </tr>
            </table>
          </div>
        </td>
      </tr>
    </table>

    <table class="table-layout">
      <tr>
        <!-- 1. Join Analytics -->
        <td class="section-td" style="padding-left: 0;">
          <div class="section-card" style="border-top: 3px solid #D4AF37;">
            <div class="section-header">
              <span class="section-title">👥 1. Join Analytics</span>
            </div>
            
            <table class="panel-table">
              <tr>
                <td class="panel-td" style="padding-left: 0;">
                  <div class="inner-panel" style="height: 50mm;">
                    <div class="panel-title" style="color: #22c55e;">First To Join</div>
                    {first_joiners_html}
                  </div>
                </td>
                <td class="panel-td" style="padding-right: 0;">
                  <div class="inner-panel" style="height: 50mm;">
                    <div class="panel-title" style="color: #FF7A00;">Late Joiners</div>
                    {late_joiners_html}
                  </div>
                </td>
              </tr>
            </table>
            
            <div class="inner-panel" style="height: 80mm; margin-top: 10px;">
              <div class="panel-title" style="color: #D4AF37; margin-bottom: 6px;">Class Presence Duration</div>
              {presence_html}
            </div>
          </div>
        </td>
        
        <!-- 2. Security Analytics -->
        <td class="section-td" style="padding-right: 0;">
          <div class="section-card" style="border-top: 3px solid #FF7A00;">
            <div class="section-header">
              <span class="section-title">🛡️ 2. Security Analytics</span>
            </div>
            
            <table class="panel-table">
              <tr>
                <td class="panel-td" style="padding-left: 0; width: 45%; vertical-align: middle; text-align: center;">
                  <div style="position: relative; display: inline-block; width: 70px; height: 70px;">
                    {security_donut_svg_str}
                    <div style="position: absolute; top: 20px; left: 0; right: 0; text-align: center;">
                      <span style="font-size: 12pt; font-weight: bold; color: #FFF; line-height: 1;">{total_alerts}</span>
                      <span style="font-size: 5pt; color: #A0A0A0; display: block; text-transform: uppercase; margin-top: -2px;">Alerts</span>
                    </div>
                  </div>
                </td>
                <td class="panel-td" style="padding-right: 0; width: 55%; vertical-align: middle;">
                  <div class="inner-panel" style="height: 50mm; display: flex; flex-direction: column; justify-content: center; gap: 4px;">
                    <div class="list-item" style="border: none;"><span style="color: #ef4444;">●</span> Tab Switches <span style="float: right; font-weight: bold;">{tab_switches}</span></div>
                    <div class="list-item" style="border: none;"><span style="color: #FF7A00;">●</span> Face Missing <span style="float: right; font-weight: bold;">{face_missing}</span></div>
                    <div class="list-item" style="border: none;"><span style="color: #D4AF37;">●</span> Multi-Face <span style="float: right; font-weight: bold;">{multi_face}</span></div>
                    <div class="list-item" style="border: none;"><span style="color: #22c55e;">●</span> DevTools <span style="float: right; font-weight: bold;">{devtools}</span></div>
                  </div>
                </td>
              </tr>
            </table>
            
            <div class="inner-panel" style="height: 80mm; margin-top: 10px;">
              <div class="panel-title" style="color: #D4AF37; margin-bottom: 4px;">Risk Distribution</div>
              <div class="risk-row" style="margin-bottom: 8px;">
                <div class="risk-lbl" style="font-size: 8pt;"><span class="risk-dot dot-low"></span>Low Risk: {low_risk}</div>
                <div class="risk-lbl" style="font-size: 8pt;"><span class="risk-dot dot-med"></span>Med Risk: {med_risk}</div>
                <div class="risk-lbl" style="font-size: 8pt;"><span class="risk-dot dot-high"></span>High Risk: {high_risk}</div>
              </div>
              <table style="width: 100%; height: 6px; background: rgba(255,255,255,0.03); border-radius: 3px; overflow: hidden; border-collapse: collapse;">
                <tr>
                  <td style="background: #22c55e; width: {round(low_risk/max(1,total_students)*100)}%;"></td>
                  <td style="background: #D4AF37; width: {round(med_risk/max(1,total_students)*100)}%;"></td>
                  <td style="background: #ef4444; width: {round(high_risk/max(1,total_students)*100)}%;"></td>
                </tr>
              </table>
            </div>
          </div>
        </td>
      </tr>
    </table>

    <table class="gen-box-table">
      <tr>
        <td class="gen-box-td" style="font-size: 9pt; font-weight: bold; color: #FFF; width: 30%;">{brand_name}</td>
        <td class="gen-box-td" style="font-size: 7pt; color: #A0A0A0; text-transform: uppercase; width: 45%; text-align: center;">{brand_name} AI Analytics Engine</td>
        <td class="gen-box-td" style="font-size: 7.5pt; color: #A0A0A0; width: 25%; text-align: right;">{datetime.now().strftime('%d %b %Y | %I:%M %p')}</td>
      </tr>
    </table>

    <footer>
      <span class="footer-tagline">Empowering Educators with AI • Page 1 of 3</span>
    </footer>
  </div>

  <!-- PAGE 2 -->
  <div class="page">
    <table class="header-table">
      <tr>
        <td class="logo-td" style="vertical-align: middle;">
          <table style="border-collapse: collapse; border: none;">
            <tr>
              <td style="padding-right: 8px; vertical-align: middle;">
                <svg width="24" height="24" viewBox="0 0 44 44" fill="none">
                  <path d="M22 2C10.95 2 2 10.95 2 22s8.95 20 20 20 20-8.95 20-20S33.05 2 22 2zm0 36c-8.82 0-16-7.18-16-16S13.18 6 22 6s16 7.18 16 16-7.18 16-16 16z" fill="#FF7A00"/>
                  <circle cx="22" cy="22" r="8" fill="#D4AF37"/>
                </svg>
              </td>
              <td style="vertical-align: middle; line-height: 1;">
                <div style="font-family: 'Poppins', sans-serif; font-size: 15pt; font-weight: 900; letter-spacing: 2px; color: #FFF; margin: 0; line-height: 1;">{brand_name.upper()}</div>
                <div style="font-size: 5.5pt; font-weight: 700; letter-spacing: 1.5px; color: #D4AF37; text-transform: uppercase; margin-top: 1px;">AI Classroom</div>
              </td>
            </tr>
          </table>
        </td>
        <td class="title-td" style="vertical-align: middle;">
          <div class="title-text">SESSION INTELLIGENCE REPORT</div>
          <div class="title-sub">AI Powered Classroom Analytics</div>
        </td>
        <td class="id-td" style="vertical-align: middle;">
          <div class="id-box">
            <span class="id-lbl">Report ID</span>
            <span class="id-val">{session_code}</span>
          </div>
        </td>
      </tr>
    </table>

    <table class="table-layout" style="margin-bottom: 8px;">
      <tr>
        <!-- 3. Task Analytics -->
        <td class="section-td" style="padding-left: 0;">
          <div class="section-card" style="border-top: 3px solid #22c55e;">
            <div class="section-header">
              <span class="section-title">📝 3. Task Analytics</span>
            </div>
            
            <table class="panel-table">
              <tr>
                <td class="panel-td" style="padding-left: 0; width: 45%; vertical-align: middle; text-align: center;">
                  <div style="position: relative; display: inline-block; width: 70px; height: 70px;">
                    {completion_svg_str}
                    <div style="position: absolute; top: 22px; left: 0; right: 0; text-align: center;">
                      <span class="circular-val" style="font-size: 11pt; font-weight: 800; color: #FFF;">{completion_pct}%</span>
                      <span class="circular-lbl" style="font-size: 5pt; color: #A0A0A0; text-transform: uppercase; display: block;">Done</span>
                    </div>
                  </div>
                </td>
                <td class="panel-td" style="padding-right: 0; width: 55%; vertical-align: middle;">
                  <div class="inner-panel" style="height: 50mm; display: flex; flex-direction: column; justify-content: center; gap: 4px;">
                    <div class="list-item" style="border: none;">Assigned: <span style="float: right; font-weight: bold;">{total_assigned}</span></div>
                    <div class="list-item" style="border: none;">Completed: <span style="float: right; font-weight: bold;">{completed_cnt}</span></div>
                    <div class="list-item" style="border: none;">Pending: <span style="float: right; font-weight: bold;">{pending_cnt}</span></div>
                    <div class="list-item" style="border: none;">Not Sub: <span style="float: right; font-weight: bold;">{not_sub_cnt}</span></div>
                  </div>
                </td>
              </tr>
            </table>
            
            <div class="inner-panel" style="height: 80mm; margin-top: 10px;">
              <div class="panel-title" style="color: #D4AF37;">Top Performers</div>
              {top_perf_html}
            </div>
          </div>
        </td>
        
        <!-- 4. Student Understanding -->
        <td class="section-td" style="padding-right: 0;">
          <div class="section-card" style="border-top: 3px solid #D4AF37;">
            <div class="section-header">
              <span class="section-title">🧠 4. Student Understanding</span>
            </div>
            
            <table class="panel-table">
              <tr>
                <td class="panel-td" style="padding-left: 0;">
                  <div class="inner-panel" style="height: 50mm;">
                    <div class="panel-title" style="color: #22c55e;">Topic Accuracy</div>
                    {topics_html}
                  </div>
                </td>
                <td class="panel-td" style="padding-right: 0;">
                  <div class="inner-panel" style="height: 50mm;">
                    <div class="panel-title" style="color: #ef4444;">Struggling</div>
                    {attention_html}
                  </div>
                </td>
              </tr>
            </table>
            
            <table class="panel-table" style="margin-top: 10px;">
              <tr>
                <td class="panel-td" style="padding-left: 0;">
                  <div class="inner-panel" style="border-left: 3px solid #D4AF37; height: 80mm;">
                    <div style="font-size: 6pt; color: #A0A0A0; text-transform: uppercase;">Strongest Topic</div>
                    <div style="font-size: 8.5pt; font-weight: bold; color: #FFF; margin-top: 2px;">{strongest_topic}</div>
                  </div>
                </td>
                <td class="panel-td" style="padding-right: 0;">
                  <div class="inner-panel" style="border-left: 3px solid #ef4444; height: 80mm;">
                    <div style="font-size: 6pt; color: #A0A0A0; text-transform: uppercase;">Weakest Topic</div>
                    <div style="font-size: 8.5pt; font-weight: bold; color: #FFF; margin-top: 2px;">{weakest_topic}</div>
                  </div>
                </td>
              </tr>
            </table>
          </div>
        </td>
      </tr>
    </table>

    <table class="gen-box-table">
      <tr>
        <td class="gen-box-td" style="font-size: 9pt; font-weight: bold; color: #FFF; width: 30%;">{brand_name}</td>
        <td class="gen-box-td" style="font-size: 7pt; color: #A0A0A0; text-transform: uppercase; width: 45%; text-align: center;">{brand_name} AI Analytics Engine</td>
        <td class="gen-box-td" style="font-size: 7.5pt; color: #A0A0A0; width: 25%; text-align: right;">{datetime.now().strftime('%d %b %Y | %I:%M %p')}</td>
      </tr>
    </table>

    <footer>
      <span class="footer-tagline">Empowering Educators with AI • Page 2 of 3</span>
    </footer>
  </div>

  <!-- PAGE 3 -->
  <div class="page" style="height: auto; page-break-after: avoid;">
    <table class="header-table">
      <tr>
        <td class="logo-td" style="vertical-align: middle;">
          <table style="border-collapse: collapse; border: none;">
            <tr>
              <td style="padding-right: 8px; vertical-align: middle;">
                <svg width="24" height="24" viewBox="0 0 44 44" fill="none">
                  <path d="M22 2C10.95 2 2 10.95 2 22s8.95 20 20 20 20-8.95 20-20S33.05 2 22 2zm0 36c-8.82 0-16-7.18-16-16S13.18 6 22 6s16 7.18 16 16-7.18 16-16 16z" fill="#FF7A00"/>
                  <circle cx="22" cy="22" r="8" fill="#D4AF37"/>
                </svg>
              </td>
              <td style="vertical-align: middle; line-height: 1;">
                <div style="font-family: 'Poppins', sans-serif; font-size: 15pt; font-weight: 900; letter-spacing: 2px; color: #FFF; margin: 0; line-height: 1;">{brand_name.upper()}</div>
                <div style="font-size: 5.5pt; font-weight: 700; letter-spacing: 1.5px; color: #D4AF37; text-transform: uppercase; margin-top: 1px;">AI Classroom</div>
              </td>
            </tr>
          </table>
        </td>
        <td class="title-td" style="vertical-align: middle;">
          <div class="title-text">SESSION INTELLIGENCE REPORT</div>
          <div class="title-sub">AI Powered Classroom Analytics</div>
        </td>
        <td class="id-td" style="vertical-align: middle;">
          <div class="id-box">
            <span class="id-lbl">Report ID</span>
            <span class="id-val">{session_code}</span>
          </div>
        </td>
      </tr>
    </table>

    <table class="table-layout" style="margin-bottom: 8px;">
      <tr>
        <!-- 5. Engagement Analytics -->
        <td class="section-td" style="padding-left: 0;">
          <div class="section-card" style="border-top: 3px solid #D4AF37; height: 75mm; margin-bottom: 8px;">
            <div class="section-header">
              <span class="section-title">📈 5. Engagement Analytics</span>
            </div>
            
            <table class="panel-table">
              <tr>
                <td class="panel-td" style="padding-left: 0; width: 45%; vertical-align: middle; text-align: center;">
                  <div style="position: relative; display: inline-block; width: 50px; height: 50px;">
                    {engagement_donut_svg_str}
                    <div style="position: absolute; top: 15px; left: 0; right: 0; text-align: center;">
                      <span class="circular-val" style="font-size: 9pt; font-weight: 800; color: #FFF;">{engagement_score}%</span>
                      <span class="circular-lbl" style="font-size: 4pt; color: #A0A0A0; text-transform: uppercase; display: block;">Engaged</span>
                    </div>
                  </div>
                </td>
                <td class="panel-td" style="padding-right: 0; width: 55%; vertical-align: middle;">
                  <div class="inner-panel" style="height: 35mm; display: flex; flex-direction: column; justify-content: center; gap: 4px;">
                    <div class="list-item" style="border: none;"><span style="color: #22c55e;">●</span> High: {eng_high}</div>
                    <div class="list-item" style="border: none;"><span style="color: #D4AF37;">●</span> Med: {eng_med}</div>
                    <div class="list-item" style="border: none;"><span style="color: #FF7A00;">●</span> Low: {eng_low}</div>
                  </div>
                </td>
              </tr>
            </table>
            
            <table class="panel-table" style="margin-top: 4px;">
              <tr>
                <td class="panel-td" style="padding-left: 0; width: 50%; vertical-align: middle;">
                  <div style="font-size: 7pt; font-weight: bold; color: #22c55e; text-transform: uppercase;">Response Rate</div>
                  <div style="display: flex; align-items: center; gap: 4px; margin-top: 2px;">
                    <span style="font-size: 13pt; font-weight: 800; color: #22c55e; line-height: 1;">{engagement_score}%</span>
                    {engagement_badge_html}
                  </div>
                </td>
                <td class="panel-td" style="padding-right: 0; width: 50%; vertical-align: middle;">
                  <div style="height: 25px; display: inline-block; width: 100%;">
                    {line_chart_svg_str}
                  </div>
                </td>
              </tr>
            </table>
          </div>
        </td>
        
        <!-- 6. AI Insights & Recommendations -->
        <td class="section-td" style="padding-right: 0;">
          <div class="section-card" style="border-top: 3px solid #FF7A00; height: 75mm; margin-bottom: 8px;">
            <div class="section-header">
              <span class="section-title">🤖 6. AI Insights & Recommendations</span>
            </div>
            
            <div class="inner-panel" style="background: rgba(212, 175, 55, 0.03); border: 1px solid rgba(212, 175, 55, 0.15); margin-bottom: 6px; padding: 6px;">
              <div class="panel-title" style="color: #D4AF37; margin-bottom: 2px;">AI Session Summary</div>
              <p class="ai-text" style="font-size: 7.5pt; line-height: 1.3; color: #FFFFFF;">{ai_summary_txt}</p>
            </div>
            
            <div class="inner-panel" style="background: rgba(255, 122, 0, 0.03); border: 1px solid rgba(255, 122, 0, 0.15); padding: 6px;">
              <div class="panel-title" style="color: #FF7A00; margin-bottom: 2px;">Recommendations</div>
              {ai_recs_html}
            </div>
          </div>
        </td>
      </tr>
    </table>

    <!-- 7. Student Performance Gradebook -->
    <div class="gradebook-card" style="border-top: 3px solid #D4AF37;">
      <div class="section-header">
        <span class="section-title">📊 7. Student Performance Marks Register</span>
      </div>
      <table class="gradebook-table">
        <thead>
          <tr>
            <th style="width: 8%; text-align: center;">Rank</th>
            <th style="width: 25%; text-align: left;">Student Name</th>
            <th style="width: 15%; text-align: left;">Roll No</th>
            <th style="width: 15%; text-align: left;">Class</th>
            <th style="width: 10%; text-align: center;">Tasks</th>
            <th style="width: 10%; text-align: center;">Tests</th>
            <th style="width: 10%; text-align: center;">Coding</th>
            <th style="width: 10%; text-align: center;">Att. %</th>
            <th style="width: 12%; text-align: center;">Overall</th>
          </tr>
        </thead>
        <tbody>
          {gradebook_rows_html}
        </tbody>
      </table>
    </div>

    <table class="gen-box-table" style="margin-top: 10px;">
      <tr>
        <td class="gen-box-td" style="font-size: 9pt; font-weight: bold; color: #FFF; width: 30%;">{brand_name}</td>
        <td class="gen-box-td" style="font-size: 7pt; color: #A0A0A0; text-transform: uppercase; width: 45%; text-align: center;">{brand_name} AI Analytics Engine</td>
        <td class="gen-box-td" style="font-size: 7.5pt; color: #A0A0A0; width: 25%; text-align: right;">{datetime.now().strftime('%d %b %Y | %I:%M %p')}</td>
      </tr>
    </table>

    <footer style="margin-top: 8px;">
      <span class="footer-tagline">Empowering Educators with AI • Page 3 of 3</span>
    </footer>
  </div>
  
</body>
</html>
'''

    # Write debug HTML to disk for verification screenshots
    try:
        debug_html_path = "C:\\Users\\robin\\.gemini\\antigravity\\brain\\f96eef2a-3c48-4fc0-9f72-5fdc252dccd8\\sample_report.html"
        os.makedirs(os.path.dirname(debug_html_path), exist_ok=True)
        with open(debug_html_path, "w", encoding="utf-8") as f:
            f.write(html_content)
    except Exception:
        pass

    # Compile HTML to PDF using WeasyPrint with a 90.0s thread timeout
    def run_weasyprint():
        return weasyprint.HTML(string=html_content).write_pdf(font_config=weasyprint_font_config)

    import threading
    import queue
    q = queue.Queue()

    def worker():
        try:
            res = run_weasyprint()
            q.put((True, res))
        except Exception as err:
            q.put((False, err))

    t = threading.Thread(target=worker)
    t.daemon = True
    t.start()
    t.join(timeout=90.0)

    if not t.is_alive():
        ok, res = q.get()
        if ok:
            log.info("[PDF_GENERATOR] WeasyPrint generated PDF successfully!")
            return res
        else:
            log.warning("[PDF_GENERATOR] WeasyPrint failed: %s. Falling back to ReportLab...", res)
    else:
        log.warning("[PDF_GENERATOR] WeasyPrint timed out (took >90s). Falling back to ReportLab...")

    # ReportLab Fallback PDF Generator (guaranteed to generate in milliseconds)
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
        import io

        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=30, leftMargin=30, topMargin=30, bottomMargin=30)
        story = []

        styles = getSampleStyleSheet()

        title_style = ParagraphStyle(
            'DocTitle',
            parent=styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=22,
            leading=26,
            textColor=colors.HexColor('#ffffff'),
            spaceAfter=15
        )

        h2_style = ParagraphStyle(
            'Heading2',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=13,
            leading=17,
            textColor=colors.HexColor('#D4AF37'), # Gold
            spaceBefore=12,
            spaceAfter=6
        )

        body_style = ParagraphStyle(
            'BodyText',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor('#f3f4f6') # Light white text
        )

        story.append(Paragraph(f"VYOM Session Intelligence Report", title_style))
        story.append(Spacer(1, 10))

        story.append(Paragraph(f"<b>Session Code:</b> {session_code}", body_style))
        story.append(Paragraph(f"<b>Teacher Name:</b> {teacher_name}", body_style))
        story.append(Paragraph(f"<b>Session Name:</b> {session_name}", body_style))
        story.append(Paragraph(f"<b>Date:</b> {date_str}", body_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("Classroom Performance Analytics", h2_style))
        story.append(Paragraph(f"<b>Average Understanding:</b> {understanding}%", body_style))
        story.append(Paragraph(f"<b>Student Participation:</b> {participation}%", body_style))
        story.append(Paragraph(f"<b>Total Connected Students:</b> {total_students}", body_style))
        story.append(Spacer(1, 12))

        story.append(Paragraph("Student Performance Details", h2_style))
        if students_list:
            data = [["Student Name", "Score", "Correct Answers", "Total Answered"]]
            for st in students_list:
                data.append([
                    st.get("name", "Student"),
                    f"{st.get('score', 0)}",
                    f"{st.get('correct', 0)}",
                    f"{st.get('total_answered', 0)}"
                ])
            t_table = Table(data, colWidths=[200, 100, 100, 100])
            t_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1f2937')), # Dark grey header
                ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#D4AF37')), # Gold text header
                ('TEXTCOLOR', (0,1), (-1,-1), colors.HexColor('#f3f4f6')), # Light text rows
                ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#111827')), # Dark cell background
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#374151')), # Subtle dark border
            ]))
            story.append(t_table)
        else:
            story.append(Paragraph("No student data recorded in this session.", body_style))

        # Background callback to paint the entire page dark
        def draw_background(canvas, doc):
            canvas.saveState()
            canvas.setFillColor(colors.HexColor('#05070f')) # Dark background
            canvas.rect(0, 0, doc.pagesize[0], doc.pagesize[1], fill=True, stroke=False)
            # Add a top gold bar
            canvas.setFillColor(colors.HexColor('#D4AF37'))
            canvas.rect(0, doc.pagesize[1] - 8, doc.pagesize[0], 8, fill=True, stroke=False)
            canvas.restoreState()

        doc.build(story, onFirstPage=draw_background, onLaterPages=draw_background)
        buffer.seek(0)
        log.info("[PDF_GENERATOR] Successfully generated premium ReportLab fallback PDF!")
        return buffer.getvalue()
    except Exception as fallback_err:
        log.critical("[PDF_GENERATOR] CRITICAL ERROR: Both WeasyPrint and ReportLab failed: %s", fallback_err, exc_info=True)
        raise fallback_err








async def send_session_email(to_email: str, session_data: dict, teacher_name: str = "Teacher") -> Tuple[bool, str]:
    """Generate and send session end report email with PDF attachment to the teacher."""
    session_id = session_data.get('session_code', session_data.get('code', 'Session'))
    session_name = session_data.get('session_name', 'Live Class')
    created_at = session_data.get('created_at') or time.time()
    
    # Subject: "VYOM Session Intelligence Report - {Session Name}"
    subject = f"VYOM Session Intelligence Report - {session_name}"
    
    # Email Body (exactly as requested)
    text = f"""Hello {teacher_name},

Your classroom session has ended successfully.

Please find attached the AI-generated Session Intelligence Report containing attendance insights, security analytics, task performance, engagement metrics, and recommendations.

Regards,
VYOM AI Classroom"""

    # HTML formatted email body matching text
    html = f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #334155; padding: 24px; max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 12px; background: #ffffff;">
    <h2 style="color: #1e3a8a; margin-top: 0; border-bottom: 2px solid #3b82f6; padding-bottom: 8px; font-weight: 700;">VYOM AI Classroom</h2>
    <p>Hello <strong>{teacher_name}</strong>,</p>
    <p>Your classroom session has ended successfully.</p>
    <p>Please find attached the AI-generated Session Intelligence Report containing attendance insights, security analytics, task performance, engagement metrics, and recommendations.</p>
    <br/>
    <p>Regards,<br/><strong>VYOM AI Classroom</strong></p>
</div>"""

    # Generate PDF attachment
    try:
        pdf_bytes = create_session_report_pdf(session_data, teacher_email=to_email)
        # Keep attachment filename professional (for example: VYOM_Premium_Report.pdf)
        pdf_filename = "VYOM_Premium_Report.pdf"
        pdf_attachment = (pdf_bytes, pdf_filename)
        log.info("[EMAIL_TASK] Successfully generated PDF for session %s, size: %d bytes", session_id, len(pdf_bytes))
    except Exception as pdf_err:
        log.error("[EMAIL_TASK] Failed to generate PDF: %s", pdf_err, exc_info=True)
        pdf_attachment = None

    return await send_mail_raw(
        to_email=to_email,
        subject=subject,
        html_content=html,
        text_content=text,
        pdf_attachment=pdf_attachment
    )

async def send_class_starting_email(to_email: str, session_code: str, teacher_name: str) -> Tuple[bool, str]:
    """Notify student that session has started."""
    subject = f"Class Started: Session {session_code}"
    html = f"""
    <div style="font-family: sans-serif; padding: 20px; border: 1px solid #10b981; border-radius: 8px;">
        <h2 style="color: #10b981;">Class is Starting!</h2>
        <p>Hello, Teacher <b>{teacher_name}</b> has started the session: <b>{session_code}</b>.</p>
        <p>Please join using the class link.</p>
    </div>
    """
    text = f"Class is Starting! Teacher {teacher_name} has started session {session_code}. Please join now."
    return await send_mail_raw(to_email, subject, html, text)

async def send_student_report_email(
    to_email: str,
    student_name: str,
    session_name: str,
    session_code: str,
    test_report: Optional[dict] = None,
    task_reports: Optional[List[dict]] = None
) -> Tuple[bool, str]:
    from report_generator import generate_student_test_pdf, generate_student_tasks_pdf
    
    attachments = []
    if test_report:
        roll = test_report.get("roll", "")
        cls_name = test_report.get("class", "")
        test_pdf = generate_student_test_pdf(session_code, student_name, roll, cls_name, test_report)
        attachments.append((test_pdf, "Premium Test Report.pdf"))
        
    if task_reports:
        roll = task_reports[0].get("roll", "")
        cls_name = task_reports[0].get("class", "")
        tasks_pdf = generate_student_tasks_pdf(session_code, student_name, roll, cls_name, task_reports)
        attachments.append((tasks_pdf, "Task Report.pdf"))
        
    if not attachments:
        return False, "No reports available to send"
        
    subject = f"VYOM Session Reports – {student_name} – {session_name}"
    
    html = f"""<div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; line-height: 1.6; color: #cbd5e1; background: #0f172a; padding: 40px 20px; max-width: 600px; margin: 0 auto; border: 1px solid #334155; border-radius: 16px;">
        <h2 style="color: #f59e0b; margin-top: 0; border-bottom: 2px solid rgba(245, 158, 11, 0.2); padding-bottom: 8px;">VYOM Session Reports</h2>
        <p>Hello <strong>{student_name}</strong>,</p>
        <p>Your session in class <strong>{session_name}</strong> has ended.</p>
        <p>Please find attached your performance reports for this session.</p>
        <br/>
        <p>Regards,<br/><strong>VYOM AI Classroom</strong></p>
    </div>"""
    
    text = f"Hello {student_name},\n\nYour session in class {session_name} has ended. Please find attached your performance reports for this session.\n\nRegards,\nVYOM AI Classroom"
    
    return await send_mail_raw(
        to_email=to_email,
        subject=subject,
        html_content=html,
        text_content=text,
        attachments=attachments
    )

async def send_otp_email(to_email: str, otp: str, user_name: str) -> Tuple[bool, str]:
    """Send a beautifully styled OTP code email to the user for login verification."""
    subject = f"VYOM Verification Code: {otp}"
    
    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; line-height: 1.6; color: #f8fafc; background: #0f172a; margin: 0; padding: 40px 20px; }}
            .card {{ max-width: 500px; margin: 0 auto; background: #1e293b; border-radius: 16px; border: 1px solid #334155; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3); }}
            .header {{ background: linear-gradient(135deg, #6366f1, #8b5cf6); color: #ffffff; padding: 36px 24px; text-align: center; }}
            .header .logo {{ font-size: 32px; margin-bottom: 8px; }}
            .header h1 {{ margin: 0; font-size: 24px; font-weight: 700; letter-spacing: -0.025em; }}
            .content {{ padding: 36px 32px; text-align: center; }}
            .greeting {{ font-size: 16px; color: #94a3b8; margin-bottom: 24px; text-align: left; }}
            .instructions {{ font-size: 15px; color: #cbd5e1; margin-bottom: 32px; text-align: left; }}
            .otp-box {{ background: #0f172a; border: 1px solid #475569; border-radius: 12px; padding: 20px; font-size: 36px; font-weight: 800; color: #818cf8; letter-spacing: 6px; margin: 24px 0; font-family: monospace; display: inline-block; box-shadow: inset 0 2px 4px rgba(0,0,0,0.4); }}
            .expiry-warning {{ font-size: 13px; color: #f43f5e; font-weight: 500; margin-top: 16px; }}
            .footer {{ padding: 24px; text-align: center; font-size: 12px; color: #64748b; border-top: 1px solid #334155; background: #1e293b; }}
        </style>
    </head>
    <body>
        <div class="card">
            <div class="header">
                <div class="logo">🧠</div>
                <h1>VYOM</h1>
            </div>
            <div class="content">
                <p class="greeting">Hello <strong>{user_name}</strong>,</p>
                <p class="instructions">Use the following verification code to sign in to your VYOM account. This code is valid for 5 minutes.</p>
                <div class="otp-box">{otp}</div>
                <p class="expiry-warning">⚠️ Do not share this code with anyone.</p>
            </div>
            <div class="footer">
                VYOM Intelligence &bull; Secure Authentication System
            </div>
        </div>
    </body>
    </html>
    """
    text = f"Hello {user_name},\n\nYour VYOM verification code is: {otp}\n\nThis code will expire in 5 minutes. Please do not share it with anyone."
    return await send_mail_raw(to_email, subject, html, text)

