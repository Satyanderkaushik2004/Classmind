"""
email_service.py  ─  ClassMind Session Report Email System (SendGrid API Version)
Sends async emails via SendGrid Web API with anti-spam optimizations.
"""
import logging
import os
import re
import asyncio
from datetime import datetime
from typing import Dict, Optional, Tuple

# Third-party imports
try:
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail, Email, To, Content, Header
except ImportError:
    SendGridAPIClient = None
    Mail = None

log = logging.getLogger("classmind.email")

# ── Configuration ─────────────────────────────────────────────────
DEFAULT_FROM_EMAIL = "classmind7@gmail.com"

# ── Email validation ──────────────────────────────────────────────
EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

def is_valid_email(email: str) -> bool:
    """Validate email format."""
    if not email: return False
    return bool(EMAIL_REGEX.match(email.strip()))

def validate_smtp_config() -> bool:
    """Check if SendGrid API key is configured."""
    return bool(os.getenv("SENDGRID_API_KEY", "").strip())

def get_sendgrid_key():
    """Fetch SendGrid API Key."""
    return os.getenv("SENDGRID_API_KEY", "").strip()

# ── SendGrid API CORE SEND ───────────────────────────────────────

async def send_mail_raw(to_email: str, subject: str, html_content: str, text_content: Optional[str] = None) -> Tuple[bool, str]:
    """
    Core Email sending logic using SendGrid Web API with Spam-avoidance headers.
    """
    api_key = get_sendgrid_key()
    from_email = os.getenv("SENDGRID_FROM_EMAIL", DEFAULT_FROM_EMAIL)
    
    if not api_key:
        return False, "SendGrid API Key not configured (SENDGRID_API_KEY missing in .env)"
    
    if SendGridAPIClient is None:
        return False, "SendGrid library not installed. Run: pip install sendgrid"

    # Generate plain text version if missing (Spam filters prefer multi-part)
    if not text_content:
        text_content = "Please view this email in an HTML-compatible client for the full report."

    try:
        # 1. Create Message with Display Name
        message = Mail(
            from_email=Email(from_email, "ClassMind"),
            to_emails=To(to_email),
            subject=subject,
            plain_text_content=Content("text/plain", text_content),
            html_content=Content("text/html", html_content)
        )
        
        # 2. Add Anti-Spam Headers
        # List-Unsubscribe is a strong signal of legitimacy
        unsubscribe_link = "https://classmind.onrender.com/unsubscribe"
        message.add_header(Header("List-Unsubscribe", f"<{unsubscribe_link}>, <mailto:classmind7@gmail.com?subject=unsubscribe>"))
        message.add_header(Header("Precedence", "list"))
        message.add_header(Header("X-Auto-Response-Suppress", "All"))
        
        # 3. Set Reply-To
        message.reply_to = Email(from_email, "ClassMind Support")

        def _send():
            sg = SendGridAPIClient(api_key)
            response = sg.send(message)
            return response.status_code

        log.info("[SENDGRID] Sending anti-spam optimized email to: %s", to_email)
        status_code = await asyncio.to_thread(_send)
        
        if 200 <= status_code < 300:
            log.info("[SENDGRID] SUCCESS: Email delivered to %s (Status: %s)", to_email, status_code)
            return True, "Email sent successfully"
        else:
            log.error("[SENDGRID] FAILED: Status code %s", status_code)
            return False, f"SendGrid returned status code {status_code}"

    except Exception as e:
        log.error("[SENDGRID] UNEXPECTED ERROR: %s", e, exc_info=True)
        return False, f"SendGrid Error: {str(e)}"

# ── Self-Test Mode ────────────────────────────────────────────────

async def verify_email_system() -> Tuple[bool, str]:
    """Diagnostic test on startup."""
    api_key = get_sendgrid_key()
    from_email = os.getenv("SENDGRID_FROM_EMAIL", DEFAULT_FROM_EMAIL)
    
    if not api_key:
        return False, "SENDGRID_API_KEY missing"

    test_html = "<h2>SendGrid Diagnostic Test</h2><p>Connection Successful. Anti-Spam headers active.</p>"
    test_text = "SendGrid Diagnostic Test: Connection Successful."
    return await send_mail_raw(from_email, "🔬 ClassMind Diagnostic Test", test_html, test_text)

# ── Content Generators ───────────────────────────────────────────

def generate_email_text(session_data: dict, teacher_name: str) -> str:
    """Generate plain text version of the session report."""
    analytics = session_data.get("analytics", {})
    session_id = session_data.get("code", "N/A")
    participation = analytics.get("participation", 0)
    understanding = analytics.get("understanding", 0)
    total_students = analytics.get("total_students", 0)

    return f"""
CLASSMIND SESSION REPORT
========================
Session: {session_id}
Teacher: {teacher_name}

ANALYTICS:
- Participation: {participation}%
- Understanding: {understanding}%
- Students: {total_students}

Thank you for using ClassMind.
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

async def send_session_email(to_email: str, session_data: dict, teacher_name: str = "Teacher") -> Tuple[bool, str]:
    """Wrapper for session report email."""
    html = generate_email_html(session_data, teacher_name)
    text = generate_email_text(session_data, teacher_name)
    session_id = session_data.get('code', 'Session')
    return await send_mail_raw(to_email, f"ClassMind Report: {session_id}", html, text)

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
