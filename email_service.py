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
from typing import Dict, Optional, Tuple

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
DEFAULT_FROM_EMAIL = "vyom7@gmail.com"

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
            use_ssl = (SMTP_PORT == 465)

            log.info("[EMAIL_SERVICE] Verifying SMTP credentials synchronously for: %s", email_address)
            smtp = aiosmtplib.SMTP(hostname=SMTP_HOST, port=SMTP_PORT, use_tls=use_ssl, timeout=5)
            await smtp.connect()
            if not use_ssl:
                try:
                    await smtp.starttls()
                except aiosmtplib.SMTPException as tls_err:
                    if "already using TLS" not in str(tls_err):
                        raise
            await smtp.login(email_address, email_password)
            await smtp.quit()
            log.info("[EMAIL_SERVICE] SMTP credentials verified successfully!")
            return True, "SMTP credentials verified successfully"
        except Exception as smtp_err:
            err_msg = str(smtp_err)
            log.error("[EMAIL_SERVICE] SMTP Verification failed: %s", err_msg)
            if "535" in err_msg and email_address.lower().endswith("@gmail.com"):
                err_msg += " (Gmail App Password required. Please generate a 16-character App Password at https://myaccount.google.com/apppasswords instead of using your main Gmail password)"
            return False, f"SMTP Connection/Auth failed: {err_msg}"

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
    pdf_attachment: Optional[Tuple[bytes, str]] = None
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
                    from_email=Email(from_email, "VYOM"),
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

                # 2. Add Anti-Spam Headers
                unsubscribe_link = "https://vyom.onrender.com/unsubscribe"
                message.add_header(Header("List-Unsubscribe", f"<{unsubscribe_link}>, <mailto:vyom7@gmail.com?subject=unsubscribe>"))
                message.add_header(Header("Precedence", "list"))
                message.add_header(Header("X-Auto-Response-Suppress", "All"))
                
                # 3. Set Reply-To
                message.reply_to = Email(from_email, "VYOM Support")

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
            message["From"] = f"VYOM <{email_address}>"
            message["To"] = to_email
            message["Subject"] = subject

            part1 = MIMEText(text_content or "Please view in HTML client", "plain", "utf-8")
            part2 = MIMEText(html_content, "html", "utf-8")
            message.attach(part1)
            message.attach(part2)

            if pdf_attachment:
                pdf_bytes, filename = pdf_attachment
                part = MIMEBase("application", "octet-stream")
                part.set_payload(pdf_bytes)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename={filename}",
                )
                main_message = MIMEMultipart("mixed")
                main_message["From"] = message["From"]
                main_message["To"] = message["To"]
                main_message["Subject"] = message["Subject"]
                main_message.attach(message)
                main_message.attach(part)
                message = main_message

            SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com").strip()
            SMTP_PORT = int(os.getenv("SMTP_PORT", "587").strip())
            use_ssl = (SMTP_PORT == 465)

            smtp = aiosmtplib.SMTP(hostname=SMTP_HOST, port=SMTP_PORT, use_tls=use_ssl, timeout=5)
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
            
            log.info("[SMTP] SUCCESS: Email sent successfully to %s", to_email)
            return True, "Email sent successfully via SMTP"
        except ImportError:
            log.error("[SMTP] aiosmtplib not installed")
            return False, "aiosmtplib library not installed"
        except Exception as smtp_err:
            log.error("[SMTP] ERROR: Failed to send via SMTP: %s", smtp_err, exc_info=True)
            return False, f"SMTP Send Error: {str(smtp_err)}"

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

def create_session_report_pdf(report: dict) -> bytes:
    """Generate a highly polished, professional PDF report matching the dashboard's layout using WeasyPrint."""
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
    /* Fonts are loaded locally/fallback to prevent HTTP hangs during compilation */
    
    :root {{
      --bg-color: #05070f;
      --card-bg: rgba(16, 22, 42, 0.65);
      --card-border: rgba(255, 255, 255, 0.06);
      --text-main: #f3f4f6;
      --text-muted: #9ca3af;
      --accent-blue: #3b82f6;
      --accent-purple: #8b5cf6;
      --accent-cyan: #06b6d4;
      --accent-green: #10b981;
      --accent-orange: #f59e0b;
      --accent-red: #ef4444;
      --accent-pink: #ec4899;
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
      background-color: var(--bg-color);
      color: var(--text-main);
      font-family: 'Outfit', sans-serif;
      font-size: 11px;
      line-height: 1.4;
      -webkit-print-color-adjust: exact;
      print-color-adjust: exact;
    }}
    
    .page {{
      width: 100%;
      height: 279mm;
      page-break-after: always;
      break-after: always;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      box-sizing: border-box;
      padding: 4mm;
    }}
    
    .page:last-child {{
      page-break-after: avoid;
      break-after: avoid;
    }}
    
    /* Header */
    header {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--card-border);
      padding-bottom: 10px;
      margin-bottom: 12px;
    }}
    
    .logo-container {{
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    
    .logo-text h1 {{
      font-size: 22px;
      font-weight: 800;
      margin: 0;
      color: #FFF;
      letter-spacing: -0.5px;
    }}
    
    .logo-text p {{
      font-size: 8px;
      font-weight: 700;
      margin: 0;
      color: var(--accent-blue);
      text-transform: uppercase;
      letter-spacing: 1.5px;
    }}
    
    .title-container {{
      text-align: center;
    }}
    
    .title-container h2 {{
      font-size: 18px;
      font-weight: 800;
      margin: 0;
      letter-spacing: 1px;
      background: linear-gradient(135deg, #FFF, var(--accent-blue));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }}
    
    .title-container p {{
      font-size: 9px;
      color: var(--text-muted);
      margin-top: 1px;
      text-transform: uppercase;
      letter-spacing: 1px;
    }}
    
    .report-id-box {{
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--card-border);
      border-radius: 6px;
      padding: 4px 10px;
      text-align: right;
    }}
    
    .report-id-box label {{
      font-size: 7px;
      color: var(--text-muted);
      text-transform: uppercase;
      display: block;
    }}
    
    .report-id-box span {{
      font-size: 10px;
      font-weight: 700;
      color: var(--accent-blue);
    }}
    
    /* Verdict Card */
    .verdict-card {{
      padding: 12px 16px;
      border-radius: 10px;
      margin-bottom: 12px;
      display: flex;
      flex-direction: column;
      gap: 3px;
      position: relative;
      overflow: hidden;
    }}
    
    .verdict-card::before {{
      content: '';
      position: absolute;
      left: 0;
      top: 0;
      bottom: 0;
      width: 4px;
    }}
    
    .verdict-excellent {{
      background: rgba(16, 185, 129, 0.06);
      border: 1px solid rgba(16, 185, 129, 0.15);
    }}
    .verdict-excellent::before {{ background: var(--accent-green); }}
    .verdict-excellent h3 {{ color: var(--accent-green); font-size: 12px; font-weight: 800; }}
    
    .verdict-good {{
      background: rgba(59, 130, 246, 0.06);
      border: 1px solid rgba(59, 130, 246, 0.15);
    }}
    .verdict-good::before {{ background: var(--accent-blue); }}
    .verdict-good h3 {{ color: var(--accent-blue); font-size: 12px; font-weight: 800; }}
    
    .verdict-review {{
      background: rgba(239, 68, 68, 0.06);
      border: 1px solid rgba(239, 68, 68, 0.15);
    }}
    .verdict-review::before {{ background: var(--accent-red); }}
    .verdict-review h3 {{ color: var(--accent-red); font-size: 12px; font-weight: 800; }}
    
    .verdict-neutral {{
      background: rgba(255, 255, 255, 0.03);
      border: 1px solid var(--card-border);
    }}
    .verdict-neutral::before {{ background: var(--text-muted); }}
    .verdict-neutral h3 {{ color: var(--text-muted); font-size: 12px; font-weight: 800; }}
    
    .verdict-card p {{ font-size: 10px; color: var(--text-main); }}
    
    /* Info Bar */
    .session-info-bar {{
      display: grid;
      grid-template-columns: repeat(6, 1fr);
      gap: 8px;
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 10px;
      margin-bottom: 12px;
    }}
    
    .info-item {{
      display: flex;
      align-items: center;
      gap: 6px;
    }}
    
    .info-icon {{
      font-size: 12px;
      width: 22px;
      height: 22px;
      background: rgba(255, 255, 255, 0.03);
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--accent-blue);
    }}
    
    .info-details {{
      display: flex;
      flex-direction: column;
    }}
    
    .info-details span {{
      font-size: 9.5px;
      font-weight: 700;
      color: #FFF;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
      max-width: 130px;
    }}
    
    .info-details label {{
      font-size: 7px;
      color: var(--text-muted);
      text-transform: uppercase;
    }}
    
    /* KPI Grid */
    .kpi-grid {{
      display: grid;
      grid-template-columns: 1.8fr 1fr 1fr 1fr 1fr;
      gap: 8px;
      margin-bottom: 12px;
    }}
    
    .kpi-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 10px;
      display: flex;
      align-items: center;
      gap: 8px;
      position: relative;
    }}
    
    .kpi-icon-box {{
      width: 26px;
      height: 26px;
      border-radius: 6px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 12px;
    }}
    
    .kpi-content {{
      display: flex;
      flex-direction: column;
    }}
    
    .kpi-val {{
      font-size: 15px;
      font-weight: 800;
    }}
    
    .kpi-lbl {{
      font-size: 8px;
      font-weight: 600;
      color: var(--text-muted);
      text-transform: uppercase;
    }}
    
    .kpi-pink {{ border-color: rgba(236, 72, 153, 0.15); }}
    .kpi-pink .kpi-icon-box {{ background: rgba(236, 72, 153, 0.1); color: var(--accent-pink); }}
    .kpi-pink .kpi-val {{ color: var(--accent-pink); }}
    
    .kpi-purple {{ border-color: rgba(139, 92, 246, 0.15); }}
    .kpi-purple .kpi-icon-box {{ background: rgba(139, 92, 246, 0.1); color: var(--accent-purple); }}
    .kpi-purple .kpi-val {{ color: var(--accent-purple); }}
    
    .kpi-blue {{ border-color: rgba(59, 130, 246, 0.15); }}
    .kpi-blue .kpi-icon-box {{ background: rgba(59, 130, 246, 0.1); color: var(--accent-blue); }}
    .kpi-blue .kpi-val {{ color: var(--accent-blue); }}
    
    .kpi-orange {{ border-color: rgba(245, 158, 11, 0.15); }}
    .kpi-orange .kpi-icon-box {{ background: rgba(245, 158, 11, 0.1); color: var(--accent-orange); }}
    .kpi-orange .kpi-val {{ color: var(--accent-orange); }}
    
    .kpi-green {{ border-color: rgba(16, 185, 129, 0.15); }}
    .kpi-green .kpi-icon-box {{ background: rgba(16, 185, 129, 0.1); color: var(--accent-green); }}
    .kpi-green .kpi-val {{ color: var(--accent-green); }}
    
    /* Grid Columns */
    .two-col-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 12px;
      margin-bottom: auto;
    }}
    
    .section-card {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 12px;
      padding: 12px;
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    
    .section-header {{
      display: flex;
      align-items: center;
      gap: 6px;
      border-bottom: 1px solid rgba(255, 255, 255, 0.04);
      padding-bottom: 6px;
    }}
    
    .section-header span {{
      font-size: 13px;
    }}
    
    .section-title {{
      font-size: 10px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      color: #FFF;
    }}
    
    .panel-grid {{
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 8px;
    }}
    
    .inner-panel {{
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid rgba(255, 255, 255, 0.04);
      border-radius: 8px;
      padding: 8px;
    }}
    
    .panel-title {{
      font-size: 8px;
      font-weight: 700;
      text-transform: uppercase;
      margin-bottom: 6px;
      letter-spacing: 0.5px;
    }}
    
    /* Join Analytics Styling */
    .join-item {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 3px 0;
      border-bottom: 1px solid rgba(255, 255, 255, 0.03);
    }}
    .join-item:last-child {{ border-bottom: none; }}
    
    .join-student {{
      display: flex;
      align-items: center;
      gap: 4px;
      font-size: 9px;
      font-weight: 600;
      color: #FFF;
    }}
    
    .rank-badge {{
      width: 12px;
      height: 12px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 7px;
      font-weight: bold;
    }}
    .rank-1 {{ background: rgba(245, 158, 11, 0.15); color: var(--accent-orange); border: 1px solid var(--accent-orange); }}
    .rank-2 {{ background: rgba(156, 163, 175, 0.15); color: #d1d5db; border: 1px solid #9ca3af; }}
    .rank-3 {{ background: rgba(217, 119, 6, 0.15); color: #fbbf24; border: 1px solid #ca8a04; }}
    
    .join-time {{
      font-size: 8px;
      color: var(--text-muted);
    }}
    .late-badge {{
      background: rgba(239, 68, 68, 0.1);
      color: var(--accent-red);
      padding: 1px 4px;
      border-radius: 3px;
      font-size: 7px;
      font-weight: 600;
    }}
    
    /* Security Styling */
    .sec-item {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 8.5px;
      padding: 2px 0;
    }}
    .sec-item .count {{
      font-weight: 700;
      color: #FFF;
    }}
    
    .risk-row {{
      display: flex;
      justify-content: space-between;
      font-size: 8px;
      margin-bottom: 4px;
    }}
    
    .risk-dot {{
      display: inline-block;
      width: 5px;
      height: 5px;
      border-radius: 50%;
      margin-right: 3px;
    }}
    .dot-low {{ background: var(--accent-green); }}
    .dot-med {{ background: var(--accent-orange); }}
    .dot-high {{ background: var(--accent-red); }}
    
    .risk-bar {{
      height: 4px;
      background: rgba(255, 255, 255, 0.03);
      border-radius: 2px;
      display: flex;
      overflow: hidden;
    }}
    
    .risk-seg {{
      height: 100%;
    }}
    
    /* Progress Ring */
    .circular-progress-wrapper {{
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
    }}
    
    .circular-progress-text {{
      position: absolute;
      text-align: center;
      display: flex;
      flex-direction: column;
    }}
    
    .circular-val {{
      font-size: 13px;
      font-weight: 800;
      color: #FFF;
    }}
    .circular-lbl {{
      font-size: 6px;
      color: var(--text-muted);
      text-transform: uppercase;
    }}
    
    /* Topic Bar */
    .topic-progress-item {{
      margin-bottom: 6px;
    }}
    .topic-progress-item:last-child {{ margin-bottom: 0; }}
    
    .topic-info {{
      display: flex;
      justify-content: space-between;
      font-size: 8.5px;
      font-weight: 600;
      margin-bottom: 2px;
      color: #FFF;
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
    .t-fill-green {{ background: linear-gradient(90deg, #10b981, #34d399); }}
    .t-fill-blue {{ background: linear-gradient(90deg, #3b82f6, #60a5fa); }}
    .t-fill-orange {{ background: linear-gradient(90deg, #f59e0b, #fbbf24); }}
    
    /* AI Box Styling */
    .ai-summary-box {{
      background: rgba(6, 182, 212, 0.04);
      border: 1px solid rgba(6, 182, 212, 0.15);
      border-radius: 8px;
      padding: 8px 10px;
    }}
    .ai-title {{
      font-size: 8px;
      font-weight: 800;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 4px;
    }}
    .ai-title.summary {{ color: var(--accent-cyan); }}
    .ai-title.recs {{ color: var(--accent-purple); }}
    
    .ai-text {{
      font-size: 9px;
      line-height: 1.35;
      color: var(--text-main);
    }}
    
    .ai-recs-box {{
      background: rgba(139, 92, 246, 0.04);
      border: 1px solid rgba(139, 92, 246, 0.15);
      border-radius: 8px;
      padding: 8px 10px;
    }}
    
    .ai-rec-item {{
      display: flex;
      align-items: flex-start;
      gap: 5px;
      font-size: 9px;
      margin-bottom: 4.5px;
    }}
    .ai-rec-item:last-child {{ margin-bottom: 0; }}
    
    .ai-rec-check {{
      color: var(--accent-green);
      font-weight: bold;
      font-size: 9px;
    }}
    
    /* Rankings & Lists */
    .rank-card {{
      display: flex;
      align-items: center;
      gap: 6px;
      padding: 5px 8px;
      background: rgba(255, 255, 255, 0.02);
      border: 1px solid rgba(255, 255, 255, 0.03);
      border-radius: 6px;
      margin-bottom: 4px;
    }}
    .rank-card:last-child {{ margin-bottom: 0; }}
    .rank-laurel {{ font-size: 11px; }}
    .rank-avatar {{
      width: 18px;
      height: 18px;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 8px;
      font-weight: bold;
      border: 1px solid rgba(255, 255, 255, 0.1);
    }}
    .rank-card-1 .rank-avatar {{ border-color: #f59e0b; background: rgba(245, 158, 11, 0.2); color: #fff; }}
    .rank-card-2 .rank-avatar {{ border-color: #9ca3af; background: rgba(156, 163, 175, 0.2); color: #fff; }}
    .rank-card-3 .rank-avatar {{ border-color: #ca8a04; background: rgba(217, 119, 6, 0.2); color: #fff; }}
    .rank-details {{ display: flex; flex-direction: column; }}
    .rank-name {{ font-size: 9px; font-weight: 700; color: #fff; }}
    .rank-score {{ font-size: 8px; color: var(--accent-green); font-weight: 700; }}
    
    /* Footer box */
    .gen-box {{
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 10px;
      padding: 8px 16px;
      display: flex;
      flex-direction: row;
      align-items: center;
      justify-content: space-between;
      margin-top: 10px;
    }}
    
    .gen-logo-text {{
      font-size: 12px;
      font-weight: 800;
      letter-spacing: -0.5px;
      color: #fff;
    }}
    .gen-engine {{ font-size: 8px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; }}
    .gen-time {{ font-size: 7.5px; color: var(--text-muted); }}
    
    footer {{
      display: flex;
      justify-content: center;
      border-top: 1px solid rgba(255, 255, 255, 0.04);
      padding-top: 6px;
      margin-top: 6px;
    }}
    
    .footer-tagline {{
      font-size: 7.5px;
      color: var(--accent-purple);
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
  </style>
</head>
<body>
  
  <!-- PAGE 1 -->
  <div class="page">
    <header>
      <div class="logo-container">
        <div class="logo-text">
          <h1 style="background: linear-gradient(135deg, #FFF 40%, var(--accent-blue)); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{brand_name}</h1>
          <p>AI Classroom</p>
        </div>
      </div>
      <div class="title-container">
        <h2>SESSION INTELLIGENCE REPORT</h2>
        <p>AI Powered Classroom Analytics</p>
      </div>
      <div class="report-id-box">
        <label>Report ID</label>
        <span>{session_code}</span>
      </div>
    </header>

    <div class="verdict-card {verdict_class}">
      <h3>{verdict_title}</h3>
      <p>{verdict_desc}</p>
    </div>
    
    <div class="session-info-bar">
      <div class="info-item">
        <div class="info-icon">👤</div>
        <div class="info-details">
          <span>{teacher_name}</span>
          <label>Teacher</label>
        </div>
      </div>
      <div class="info-item">
        <div class="info-icon">📖</div>
        <div class="info-details">
          <span>{session_name}</span>
          <label>Session Name</label>
        </div>
      </div>
      <div class="info-item">
        <div class="info-icon">📇</div>
        <div class="info-details">
          <span>{session_code}</span>
          <label>Session Code</label>
        </div>
      </div>
      <div class="info-item">
        <div class="info-icon">📅</div>
        <div class="info-details">
          <span>{date_str}</span>
          <label>Date</label>
        </div>
      </div>
      <div class="info-item">
        <div class="info-icon">⏰</div>
        <div class="info-details">
          <span>{time_range}</span>
          <label>Time</label>
        </div>
      </div>
      <div class="info-item">
        <div class="info-icon">⏳</div>
        <div class="info-details">
          <span>{duration_mins} min</span>
          <label>Duration</label>
        </div>
      </div>
    </div>
    
    <div class="kpi-grid">
      <div class="kpi-card kpi-pink" style="background: rgba(236, 72, 153, 0.03);">
        <div class="kpi-icon-box">✨</div>
        <div class="kpi-content">
          <span class="kpi-val">{quality_score}%</span>
          <span class="kpi-lbl">Quality Index</span>
        </div>
      </div>
      <div class="kpi-card kpi-purple" style="background: rgba(139, 92, 246, 0.02);">
        <div class="kpi-icon-box">👥</div>
        <div class="kpi-content">
          <span class="kpi-val">{participation_score}%</span>
          <span class="kpi-lbl">Participation</span>
        </div>
      </div>
      <div class="kpi-card kpi-blue" style="background: rgba(59, 130, 246, 0.02);">
        <div class="kpi-icon-box">⏱️</div>
        <div class="kpi-content">
          <span class="kpi-val">{engagement_score}%</span>
          <span class="kpi-lbl">Engagement</span>
        </div>
      </div>
      <div class="kpi-card kpi-orange" style="background: rgba(245, 158, 11, 0.02);">
        <div class="kpi-icon-box">🛡️</div>
        <div class="kpi-content">
          <span class="kpi-val">{discipline_score}%</span>
          <span class="kpi-lbl">Discipline</span>
        </div>
      </div>
      <div class="kpi-card kpi-green" style="background: rgba(16, 185, 129, 0.02);">
        <div class="kpi-icon-box">🧠</div>
        <div class="kpi-content">
          <span class="kpi-val">{understanding_score}%</span>
          <span class="kpi-lbl">Understanding</span>
        </div>
      </div>
    </div>
    
    <div class="two-col-grid">
      <!-- 1. Join Analytics -->
      <div class="section-card" style="border-top: 3px solid var(--accent-purple);">
        <div class="section-header">
          <span style="color: var(--accent-purple);">👥</span>
          <span class="section-title">1. Join Analytics</span>
        </div>
        
        <div class="panel-grid">
          <div class="inner-panel">
            <div class="panel-title" style="color: var(--accent-green);">First To Join</div>
            {first_joiners_html}
          </div>
          <div class="inner-panel">
            <div class="panel-title" style="color: var(--accent-orange);">Late Joiners</div>
            {late_joiners_html}
          </div>
        </div>
        
        <div class="inner-panel" style="margin-top: auto;">
          <div class="panel-title" style="color: var(--accent-blue); margin-bottom: 6px;">Class Presence Duration</div>
          {presence_html}
        </div>
      </div>
      
      <!-- 2. Security Analytics -->
      <div class="section-card" style="border-top: 3px solid var(--accent-orange);">
        <div class="section-header">
          <span style="color: var(--accent-orange);">🛡️</span>
          <span class="section-title">2. Security Analytics</span>
        </div>
        
        <div class="panel-grid">
          <div style="display: flex; align-items: center; justify-content: center; position: relative;">
            {security_donut_svg_str}
            <div style="position: absolute; text-align: center;">
              <div style="font-size: 16px; font-weight: 800; color: #FFF; line-height: 1;">{total_alerts}</div>
              <div style="font-size: 6px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; margin-top: 1px;">Total Alerts</div>
            </div>
          </div>
          
          <div class="inner-panel" style="display: flex; flex-direction: column; justify-content: center; gap: 4px;">
            <div class="sec-item"><span style="color: var(--accent-red);">● Tab Switches</span> <span class="count">{tab_switches}</span></div>
            <div class="sec-item"><span style="color: var(--accent-orange);">● Face Missing</span> <span class="count">{face_missing}</span></div>
            <div class="sec-item"><span style="color: var(--accent-blue);">● Multi-Face</span> <span class="count">{multi_face}</span></div>
            <div class="sec-item"><span style="color: var(--accent-green);">● DevTools</span> <span class="count">{devtools}</span></div>
          </div>
        </div>
        
        <div class="inner-panel" style="margin-top: auto;">
          <div class="panel-title" style="color: var(--accent-blue); margin-bottom: 4px;">Risk Distribution</div>
          <div class="risk-row">
            <div class="risk-lbl"><span class="risk-dot dot-low"></span>Low Risk: {low_risk}</div>
            <div class="risk-lbl"><span class="risk-dot dot-med"></span>Med Risk: {med_risk}</div>
            <div class="risk-lbl"><span class="risk-dot dot-high"></span>High Risk: {high_risk}</div>
          </div>
          <div class="risk-bar">
            <div class="risk-seg dot-low" style="width: {round(low_risk/max(1,total_students)*100)}%;"></div>
            <div class="risk-seg dot-med" style="width: {round(med_risk/max(1,total_students)*100)}%;"></div>
            <div class="risk-seg dot-high" style="width: {round(high_risk/max(1,total_students)*100)}%;"></div>
          </div>
        </div>
      </div>
    </div>
    
    <div class="gen-box">
      <span class="gen-logo-text" style="background: linear-gradient(135deg, #FFF, var(--accent-blue)); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{brand_name}</span>
      <span class="gen-engine">{brand_name} AI Analytics Engine</span>
      <span class="gen-time">{datetime.now().strftime('%d %b %Y | %I:%M %p')}</span>
    </div>
    
    <footer>
      <span class="footer-tagline">Empowering Educators with AI • Page 1 of 2</span>
    </footer>
  </div>

  <!-- PAGE 2 -->
  <div class="page">
    <header>
      <div class="logo-container">
        <div class="logo-text">
          <h1 style="background: linear-gradient(135deg, #FFF 40%, var(--accent-blue)); -webkit-background-clip: text; -webkit-text-fill-color: transparent;">{brand_name}</h1>
          <p>AI Classroom</p>
        </div>
      </div>
      <div class="title-container">
        <h2>SESSION INTELLIGENCE REPORT</h2>
        <p>AI Powered Classroom Analytics</p>
      </div>
      <div class="report-id-box">
        <label>Report ID</label>
        <span>{session_code}</span>
      </div>
    </header>

    <div class="two-col-grid" style="margin-bottom: 12px;">
      <!-- 3. Task Analytics -->
      <div class="section-card" style="border-top: 3px solid var(--accent-green);">
        <div class="section-header">
          <span style="color: var(--accent-green);">📝</span>
          <span class="section-title">3. Task Analytics</span>
        </div>
        
        <div class="panel-grid">
          <div class="inner-panel circular-progress-wrapper">
            {completion_svg_str}
            <div class="circular-progress-text">
              <span class="circular-val">{completion_pct}%</span>
              <span class="circular-lbl">Done</span>
            </div>
          </div>
          
          <div class="inner-panel" style="display: flex; flex-direction: column; justify-content: center; gap: 3.5px; font-size: 8.5px;">
            <div style="display: flex; justify-content: space-between;"><span>Assigned:</span> <strong>{total_assigned}</strong></div>
            <div style="display: flex; justify-content: space-between;"><span>Completed:</span> <strong>{completed_cnt}</strong></div>
            <div style="display: flex; justify-content: space-between;"><span>Pending:</span> <strong>{pending_cnt}</strong></div>
            <div style="display: flex; justify-content: space-between;"><span>Not Sub:</span> <strong>{not_sub_cnt}</strong></div>
          </div>
        </div>
        
        <div class="inner-panel" style="margin-top: auto;">
          <div class="panel-title" style="color: var(--accent-blue); margin-bottom: 4px;">Top Performers</div>
          <div style="display: flex; gap: 4px; justify-content: space-around;">
            {top_performers_cards_html}
          </div>
        </div>
      </div>
      
      <!-- 4. Student Understanding -->
      <div class="section-card" style="border-top: 3px solid var(--accent-purple);">
        <div class="section-header">
          <span style="color: var(--accent-purple);">🧠</span>
          <span class="section-title">4. Student Understanding</span>
        </div>
        
        <div class="panel-grid">
          <div class="inner-panel" style="display: flex; flex-direction: column; gap: 4px; min-height: 80px;">
            <div class="panel-title" style="color: var(--accent-green); margin-bottom: 2px;">Topic Accuracy</div>
            {topics_html}
          </div>
          
          <div class="inner-panel" style="display: flex; flex-direction: column; gap: 4px;">
            <div class="panel-title" style="color: var(--accent-red); margin-bottom: 2px;">Struggling</div>
            {attention_html}
          </div>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 6px; margin-top: auto;">
          <div class="inner-panel" style="border-left: 3px solid var(--accent-green); padding: 4px 6px; display: flex; align-items: center; gap: 5px;">
            <span style="font-size: 12px;">🏆</span>
            <div>
              <div style="font-size: 6px; color: var(--text-muted); text-transform: uppercase;">Strongest</div>
              <div style="font-size: 8.5px; font-weight: 700; color: #fff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 90px;">{strongest_topic}</div>
            </div>
          </div>
          <div class="inner-panel" style="border-left: 3px solid var(--accent-red); padding: 4px 6px; display: flex; align-items: center; gap: 5px;">
            <span style="font-size: 12px;">⚠️</span>
            <div>
              <div style="font-size: 6px; color: var(--text-muted); text-transform: uppercase;">Weakest</div>
              <div style="font-size: 8.5px; font-weight: 700; color: #fff; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; max-width: 90px;">{weakest_topic}</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="two-col-grid" style="margin-bottom: 12px;">
      <!-- 5. Engagement Analytics -->
      <div class="section-card" style="border-top: 3px solid var(--accent-blue);">
        <div class="section-header">
          <span style="color: var(--accent-blue);">📈</span>
          <span class="section-title">5. Engagement Analytics</span>
        </div>
        
        <div class="panel-grid">
          <div class="inner-panel" style="display: flex; align-items: center; gap: 6px;">
            {engagement_donut_svg_str}
            <div style="display: flex; flex-direction: column; gap: 1px; font-size: 7.5px;">
              <div><span style="color: var(--accent-green);">●</span> High: {eng_high}</div>
              <div><span style="color: var(--accent-blue);">●</span> Med: {eng_med}</div>
              <div><span style="color: var(--accent-red);">●</span> Low: {eng_low}</div>
            </div>
          </div>
          
          <div class="inner-panel" style="display: flex; flex-direction: column; justify-content: center; gap: 2px;">
            <div class="panel-title" style="color: var(--accent-blue); margin-bottom: 2px;">Most Active</div>
            {most_active_html}
          </div>
        </div>
        
        <div style="display: grid; grid-template-columns: 1fr 1.2fr; gap: 6px; align-items: center; margin-top: auto;">
          <div>
            <div style="font-size: 7.5px; font-weight: 700; color: var(--accent-green); text-transform: uppercase;">Response Rate</div>
            <div style="display: flex; align-items: center; gap: 4px; margin-top: 2px;">
              <span style="font-size: 14px; font-weight: 800; color: var(--accent-green);">{engagement_score}%</span>
              {engagement_badge_html}
            </div>
          </div>
          <div style="height: 36px; display: flex; align-items: center;">
            {line_chart_svg_str}
          </div>
        </div>
      </div>
      
      <!-- 6. AI Insights -->
      <div class="section-card" style="border-top: 3px solid var(--accent-cyan);">
        <div class="section-header">
          <span style="color: var(--accent-cyan);">🤖</span>
          <span class="section-title">6. AI Insights & Recommendations</span>
        </div>
        
        <div class="ai-summary-box">
          <div class="ai-title summary">AI Session Summary</div>
          <p class="ai-text">{ai_summary_txt}</p>
        </div>
        
        <div class="ai-recs-box" style="margin-top: auto;">
          <div class="ai-title recs">Recommendations</div>
        <span class="gen-time">{{datetime.now().strftime('%d %b %Y | %I:%M %p')}}</span>
      </div>
    </div>
    
    <!-- Footer -->
    <footer>
      <span class="footer-tagline">Empowering Educators with AI • Enhancing Learning with Intelligence</span>
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

    # Compile HTML to PDF using WeasyPrint with a 3.0s thread timeout
    def run_weasyprint():
        return weasyprint.HTML(string=html_content).write_pdf()

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
    t.join(timeout=3.0)

    if not t.is_alive():
        ok, res = q.get()
        if ok:
            log.info("[PDF_GENERATOR] WeasyPrint generated PDF successfully!")
            return res
        else:
            log.warning("[PDF_GENERATOR] WeasyPrint failed: %s. Falling back to ReportLab...", res)
    else:
        log.warning("[PDF_GENERATOR] WeasyPrint timed out (took >3s). Falling back to ReportLab...")

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
            textColor=colors.HexColor('#1e3a8a'),
            spaceAfter=15
        )

        h2_style = ParagraphStyle(
            'Heading2',
            parent=styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=13,
            leading=17,
            textColor=colors.HexColor('#2563eb'),
            spaceBefore=12,
            spaceAfter=6
        )

        body_style = ParagraphStyle(
            'BodyText',
            parent=styles['Normal'],
            fontName='Helvetica',
            fontSize=9.5,
            leading=13,
            textColor=colors.HexColor('#334155')
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
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#f1f5f9')),
                ('TEXTCOLOR', (0,0), (-1,0), colors.HexColor('#1e293b')),
                ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                ('FONTSIZE', (0,0), (-1,-1), 9),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
            ]))
            story.append(t_table)
        else:
            story.append(Paragraph("No student data recorded in this session.", body_style))

        doc.build(story)
        buffer.seek(0)
        log.info("[PDF_GENERATOR] Successfully generated ReportLab fallback PDF!")
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
        pdf_bytes = create_session_report_pdf(session_data)
        date_str = datetime.fromtimestamp(created_at).strftime('%Y-%m-%d')
        # PDF filename format: session-report-{sessionCode}-{date}.pdf
        pdf_filename = f"session-report-{session_id}-{date_str}.pdf"
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

async def send_student_report_email(to_email: str, student_name: str, report_data: dict) -> Tuple[bool, str]:
    return False, "Not implemented"

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

