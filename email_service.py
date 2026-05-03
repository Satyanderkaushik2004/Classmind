"""
email_service.py  ─  ClassMind Session Report Email System (SendGrid API Version)
Sends async emails via SendGrid Web API to bypass Render SMTP port blocks.
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
    from sendgrid.helpers.mail import Mail, Email, To, Content
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
    """Check if SendGrid API key is configured (Aliased for compatibility)."""
    return bool(os.getenv("SENDGRID_API_KEY", "").strip())

def get_sendgrid_key():
    """Fetch SendGrid API Key."""
    return os.getenv("SENDGRID_API_KEY", "").strip()

# ── SendGrid API CORE SEND ───────────────────────────────────────

async def send_mail_raw(to_email: str, subject: str, html_content: str) -> Tuple[bool, str]:
    """
    Core Email sending logic using SendGrid Web API.
    """
    api_key = get_sendgrid_key()
    from_email = os.getenv("SENDGRID_FROM_EMAIL", DEFAULT_FROM_EMAIL)
    
    if not api_key:
        return False, "SendGrid API Key not configured (SENDGRID_API_KEY missing in .env)"
    
    if SendGridAPIClient is None:
        return False, "SendGrid library not installed. Run: pip install sendgrid"

    try:
        message = Mail(
            from_email=Email(from_email, "ClassMind Reports"),
            to_emails=To(to_email),
            subject=subject,
            html_content=html_content
        )
        
        # Add Reply-To
        message.reply_to = Email(from_email)

        # SendGrid client is synchronous by default, we'll run it in a thread to avoid blocking FastAPI
        def _send():
            sg = SendGridAPIClient(api_key)
            response = sg.send(message)
            return response.status_code

        log.info("[SENDGRID] Attempting to send email to: %s", to_email)
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
    """
    Requirement 8: Self-test mode on server start.
    Sends a real test email to the configured sender.
    """
    api_key = get_sendgrid_key()
    from_email = os.getenv("SENDGRID_FROM_EMAIL", DEFAULT_FROM_EMAIL)
    
    if not api_key:
        msg = "Email system not fully working: SENDGRID_API_KEY missing in .env"
        print(f"\n❌ {msg}")
        return False, msg

    print(f"\n[SENDGRID_TEST] Verifying SendGrid API for {from_email}...")
    
    test_html = f"""
    <div style="font-family: sans-serif; padding: 20px; border: 2px solid #00b140; border-radius: 10px;">
        <h2 style="color: #00b140;">✅ ClassMind SendGrid Test</h2>
        <p>This is a real-time verification email sent at <strong>{datetime.now().strftime('%H:%M:%S')}</strong>.</p>
        <p>If you see this, your SendGrid API system is <strong>fully functional</strong>.</p>
        <p><i>Note: Port 587 blocks on Render are now bypassed via Web API.</i></p>
    </div>
    """
    
    success, msg = await send_mail_raw(from_email, "🔬 ClassMind SendGrid Self-Test", test_html)
    
    if success:
        full_msg = "SendGrid API system is fully configured and working correctly"
        print(f"✅ {full_msg}")
        return True, full_msg
    else:
        full_msg = f"Email system not fully working: {msg}"
        print(f"❌ {full_msg}")
        return False, full_msg

# ── HTML Email Template ───────────────────────────────────────────

def generate_email_html(session_data: dict, teacher_name: str) -> str:
    """Generate professional HTML email."""
    analytics = session_data.get("analytics", {})
    start_time = datetime.fromtimestamp(session_data.get("created_at", 0))
    duration_secs = session_data.get("duration_secs", 0)
    duration_mins = max(1, duration_secs // 60)
    
    total_students = analytics.get("total_students", 0)
    participation = analytics.get("participation", 0)
    understanding = analytics.get("understanding", 0)
    session_id = session_data.get("code", "N/A")

    return f"""
    <!DOCTYPE html>
    <html>
    <head><style>
        body {{ font-family: 'Segoe UI', sans-serif; line-height: 1.6; color: #334155; background: #f8fafc; margin: 0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
        .header {{ background: #00b140; color: #fff; padding: 30px; text-align: center; }}
        .content {{ padding: 30px; }}
        .stat-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin: 20px 0; }}
        .stat-card {{ background: #f1f5f9; padding: 15px; border-radius: 12px; text-align: center; }}
        .footer {{ background: #f1f5f9; padding: 20px; text-align: center; font-size: 12px; color: #64748b; }}
    </style></head>
    <body>
        <div class="container">
            <div class="header"><h1>ClassMind Report</h1><p>Session {session_id}</p></div>
            <div class="content">
                <p>Teacher: <strong>{teacher_name}</strong></p>
                <div class="stat-grid">
                    <div class="stat-card"><b>Participation</b><br>{participation}%</div>
                    <div class="stat-card"><b>Understanding</b><br>{understanding}%</div>
                    <div class="stat-card"><b>Students</b><br>{total_students}</div>
                    <div class="stat-card"><b>Duration</b><br>{duration_mins}m</div>
                </div>
                <p style="text-align:center; color: #64748b; font-size: 14px;">Started at {start_time.strftime('%I:%M %p')}</p>
            </div>
            <div class="footer">ClassMind &bull; Interactive Classroom Intelligence</div>
        </div>
    </body>
    </html>
    """

async def send_session_email(to_email: str, session_data: dict, teacher_name: str = "Teacher") -> Tuple[bool, str]:
    """Wrapper for session report email."""
    html = generate_email_html(session_data, teacher_name)
    session_id = session_data.get('code', 'Session')
    return await send_mail_raw(to_email, f"ClassMind Report: {session_id}", html)

async def send_student_report_email(to_email: str, student_name: str, report_data: dict) -> Tuple[bool, str]:
    return False, "Not implemented yet"

async def send_class_starting_email(to_email: str, session_code: str, teacher_name: str) -> Tuple[bool, str]:
    return False, "Not implemented yet"
