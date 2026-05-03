import asyncio
import os
from dotenv import load_dotenv

async def test():
    load_dotenv()
    api_key = os.getenv("SENDGRID_API_KEY")
    from_email = os.getenv("SENDGRID_FROM_EMAIL", "classmind7@gmail.com")
    
    print(f"Testing SendGrid with: {from_email}")
    
    try:
        from sendgrid import SendGridAPIClient
        from sendgrid.helpers.mail import Mail
        
        message = Mail(
            from_email=from_email,
            to_emails=from_email,
            subject='ClassMind Quick Test',
            plain_text_content='Hello! If you see this, your SendGrid setup is working.'
        )
        
        sg = SendGridAPIClient(api_key)
        response = sg.send(message)
        
        if response.status_code >= 200 and response.status_code < 300:
            print("\n✅ SUCCESS! The test email has been sent via SendGrid.")
        else:
            print(f"\n❌ FAILED: Status {response.status_code}")
            
    except Exception as e:
        print(f"\n❌ FAILED: {str(e)}")

if __name__ == "__main__":
    asyncio.run(test())
