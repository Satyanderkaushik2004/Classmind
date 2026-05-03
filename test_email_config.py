import asyncio
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_sendgrid_connection():
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("SENDGRID_FROM_EMAIL", "classmind7@gmail.com")

    print(f"--- SendGrid API Connection Test ---")
    print(f"From Email: {from_email}")
    
    if not api_key:
        print("ERROR: SENDGRID_API_KEY not found in .env")
        return

    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
    except ImportError:
        print("ERROR: sendgrid library not installed. Run: pip install sendgrid")
        return

    message = Mail(
        from_email=from_email,
        to_emails=from_email,
        subject='ClassMind SendGrid Test',
        plain_text_content='This is a test email to verify SendGrid configuration.'
    )

    try:
        print("Connecting to SendGrid...")
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        
        if response.status_code >= 200 and response.status_code < 300:
            print(f"SUCCESS: Email sent successfully! Status Code: {response.status_code}")
            print("\nSUCCESS: Your SendGrid configuration is 100% correct.")
        else:
            print(f"FAILED: SendGrid returned status code {response.status_code}")
            
    except Exception as e:
        print(f"\nERROR: {type(e).__name__}: {e}")
        print("Suggestion: Ensure your API key is correct and your Sender Identity is verified in SendGrid.")

if __name__ == "__main__":
    asyncio.run(test_sendgrid_connection())
