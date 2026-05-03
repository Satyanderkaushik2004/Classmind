import asyncio
import os
from dotenv import load_dotenv
from pathlib import Path
import sys
import aiosmtplib

# Add parent dir to sys.path to import internal modules
sys.path.append(str(Path(__file__).parent.parent))

from email_service import send_mail_raw, validate_smtp_config

async def test_smtp():
    print("🚀 ClassMind SMTP Verification Tool")
    print("-----------------------------------")
    
    # Load env
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)
    
    email = os.getenv("EMAIL_ADDRESS")
    pwd = os.getenv("EMAIL_PASSWORD")
    
    if not email or not pwd:
        print("❌ ERROR: EMAIL_ADDRESS or EMAIL_PASSWORD not found in .env")
        return
        
    print(f"📧 Configured Email: {email}")
    
    if not validate_smtp_config():
        print("❌ VALIDATION FAILED: Credentials missing or placeholder found in .env")
        return

    print(f"⏳ Attempting to send test email to {email}...")
    
    # We call send_mail_raw directly as it now uses the most robust aiosmtplib.send() method
    subject = "🔬 ClassMind SMTP Test - Final Fix"
    html = """
    <div style="font-family: sans-serif; padding: 20px; border: 2px solid #6366f1; border-radius: 10px;">
        <h2 style="color: #6366f1;">✅ SMTP Final Fix Verified</h2>
        <p>This email was sent using <b>aiosmtplib.send()</b> which is the most robust method.</p>
        <p>If you see this, your SMTP configuration is perfect and the TLS conflict is resolved.</p>
    </div>
    """
    
    try:
        success, message = await send_mail_raw(email, subject, html)
        
        if success:
            print(f"✅ SUCCESS: {message}")
            print(f"📢 Action: Please check the inbox (and spam) of {email}")
        else:
            print(f"❌ FAILED: {message}")

    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_smtp())
