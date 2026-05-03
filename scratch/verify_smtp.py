import asyncio
import os
from dotenv import load_dotenv
from pathlib import Path
import sys

# Add parent dir to sys.path to import internal modules
sys.path.append(str(Path(__file__).parent.parent))

from email_service import send_mail_raw, validate_smtp_config

async def test_sendgrid():
    print("🚀 ClassMind SendGrid API Verification Tool")
    print("-------------------------------------------")
    
    # Load env
    env_path = Path(__file__).parent.parent / ".env"
    load_dotenv(dotenv_path=env_path)
    
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("SENDGRID_FROM_EMAIL", "classmind7@gmail.com")
    
    print(f"🔑 API Key Found: {'Yes' if api_key else 'No'}")
    print(f"📧 From Email: {from_email}")
    
    if not api_key:
        print("❌ ERROR: SENDGRID_API_KEY not found in .env")
        return

    print(f"⏳ Attempting to send test email to {from_email}...")
    
    subject = "🔬 ClassMind SendGrid API Test"
    html = """
    <div style="font-family: sans-serif; padding: 20px; border: 2px solid #00b140; border-radius: 10px;">
        <h2 style="color: #00b140;">✅ SendGrid API Verified</h2>
        <p>This email was sent using the <b>SendGrid Web API</b>.</p>
        <p>If you see this, your configuration is perfect and Render port blocks are bypassed.</p>
    </div>
    """
    
    try:
        # Install dependency if missing (for the test script environment)
        try:
            import sendgrid
        except ImportError:
            print("📦 Installing sendgrid library...")
            import subprocess
            subprocess.check_call([sys.executable, "-m", "pip", "install", "sendgrid"])
            
        success, message = await send_mail_raw(from_email, subject, html)
        
        if success:
            print(f"✅ SUCCESS: {message}")
            print(f"📢 Action: Please check the inbox (and spam) of {from_email}")
        else:
            print(f"❌ FAILED: {message}")
            print("\n💡 Troubleshooting Tips:")
            print("1. Ensure your API Key is correct and has 'Mail Send' permissions.")
            print("2. Ensure the 'From' email is verified in your SendGrid Single Sender Authentication.")

    except Exception as e:
        print(f"❌ UNEXPECTED ERROR: {e}")

if __name__ == "__main__":
    asyncio.run(test_sendgrid())
