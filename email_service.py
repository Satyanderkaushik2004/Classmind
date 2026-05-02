"""
email_service.py  ─  ClassMind Session Report Email System
Sends async emails via Gmail SMTP with professional HTML formatting.
"""
import logging
import os
import re
import asyncio
from datetime import datetime
from typing import Dict, Optional, Tuple

# Third-party imports
try:
    import aiosmtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
except ImportError:
    aiosmtplib = None
    MIMEText = None
    MIMEMultipart = None

log = logging.getLogger("classmind.email")

# ── Configuration ─────────────────────────────────────────────────
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# ── Email validation ──────────────────────────────────────────────
EMAIL_REGEX = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")

def is_valid_email(email: str) -> bool:
    """Validate email format."""
    return bool(EMAIL_REGEX.match(email.strip()))

def validate_smtp_config() -> bool:
    """Check if SMTP credentials are configured and not placeholders."""
    email, pwd = get_credentials()
    if not email or not pwd:
        return False
    placeholders = ["your-email@gmail.com", "your-app-password", "example.com"]
    if any(p in email for p in placeholders) or any(p in pwd for p in placeholders):
        return False
    return True

def get_credentials():
    """Dynamically fetch credentials to ensure they are loaded after dotenv."""
    return os.getenv("EMAIL_ADDRESS", "").strip(), os.getenv("EMAIL_PASSWORD", "").strip()

# ── SMTP CORE SEND ───────────────────────────────────────────────

async def send_mail_raw(to_email: str, subject: str, html_content: str) -> Tuple[bool, str]:
    """
    Core SMTP sending logic with strict error handling.
    """
    sender_email, sender_password = get_credentials()
    
    if not sender_email or not sender_password:
        return False, "SMTP not configured (check EMAIL_ADDRESS and EMAIL_PASSWORD in .env)"
    
    if not aiosmtplib:
        return False, "aiosmtplib not installed"

    try:
        message = MIMEMultipart("alternative")
        message["Subject"] = subject
        message["From"] = f"ClassMind Reports <{sender_email}>"
        message["To"] = to_email
        
        text_content = "Please view this email in an HTML-compatible client."
        message.attach(MIMEText(text_content, "plain"))
        message.attach(MIMEText(html_content, "html"))

        # Port 587 with STARTTLS is generally more compatible than 465
        smtp = aiosmtplib.SMTP(hostname=SMTP_SERVER, port=587, use_tls=False, timeout=20)
        
        async with smtp:
            try:
                await smtp.starttls()
                # Clean password of any spaces (common in App Passwords)
                clean_pwd = sender_password.replace(" ", "")
                log.info("[SMTP] Attempting login for: %s", sender_email)
                await smtp.login(sender_email, clean_pwd)
            except aiosmtplib.SMTPAuthenticationError:
                log.error("[SMTP] Auth failed for %s", sender_email)
                return False, f"Authentication failed for {sender_email}. Check App Password."
            except Exception as e:
                log.error("[SMTP] Login/TLS Error: %s", e)
                return False, f"SMTP Connection Error: {str(e)}"
            
            await smtp.send_message(message)
            log.info("[SMTP] Successfully sent email to %s", to_email)
            
        return True, "Email sent successfully"

    except (ConnectionError, asyncio.TimeoutError, OSError) as e:
        return False, f"Connection error (check your internet or firewall): {str(e)}"
    except Exception as e:
        log.error("Unexpected SMTP error: %s", e, exc_info=True)
        return False, f"Unexpected error: {str(e)}"

# ── Self-Test Mode ────────────────────────────────────────────────

async def verify_email_system() -> Tuple[bool, str]:
    """
    Requirement 8: Self-test mode on server start.
    Sends a real test email to the sender.
    """
    if not validate_smtp_config():
        if SENDER_PASSWORD == "your-app-password":
            print("\n\u26A0\uFE0F Please replace EMAIL_PASSWORD with a valid Gmail App Password")
        msg = "Email system not fully working: Missing or placeholder credentials in .env"
        print(f"\n\u274C {msg}")
        return False, msg

    print(f"\n[SMTP_TEST] Verifying Gmail SMTP for {SENDER_EMAIL}...")
    
    test_html = f"""
    <div style="font-family: sans-serif; padding: 20px; border: 2px solid #6366f1; border-radius: 10px;">
        <h2 style="color: #6366f1;">✅ ClassMind SMTP Test</h2>
        <p>This is a real-time verification email sent at <strong>{datetime.now().strftime('%H:%M:%S')}</strong>.</p>
        <p>If you see this, your Gmail SMTP system is <strong>fully functional</strong>.</p>
    </div>
    """
    
    success, msg = await send_mail_raw(SENDER_EMAIL, "🔬 ClassMind SMTP Self-Test", test_html)
    
    if success:
        full_msg = "Gmail SMTP system is fully configured and working correctly"
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
    question_count = len(session_data.get("tasks", []))

    return f"""
    <!DOCTYPE html>
    <html>
    <head><style>
        body {{ font-family: 'Segoe UI', sans-serif; line-height: 1.6; color: #334155; background: #f8fafc; margin: 0; padding: 20px; }}
        .container {{ max-width: 600px; margin: 0 auto; background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 4px 6px rgba(0,0,0,0.05); }}
        .header {{ background: #6366f1; color: #fff; padding: 30px; text-align: center; }}
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
            <div class="footer">ClassMind &bull; Interactive Classroom intelligence</div>
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
