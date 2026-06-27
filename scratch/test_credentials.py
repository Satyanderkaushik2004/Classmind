import asyncio
import os
import sys

# Ensure project root is in python path
sys.path.append(os.getcwd())

from email_service import verify_smtp_credentials

async def run_tests():
    print("--- Testing SMTP Credentials Verification ---")
    
    # 1. Test when no credentials are configured
    print("\nTest 1: Unconfigured Environment")
    orig_env = {
        "SENDGRID_API_KEY": os.environ.pop("SENDGRID_API_KEY", None),
        "EMAIL_ADDRESS": os.environ.pop("EMAIL_ADDRESS", None),
        "EMAIL_PASSWORD": os.environ.pop("EMAIL_PASSWORD", None),
    }
    
    ok, msg = await verify_smtp_credentials()
    print("Verification result:", ok)
    print("Message:", msg)
    assert not ok
    assert "Email service not configured" in msg

    # 2. Test when invalid SendGrid API Key is configured
    print("\nTest 2: Invalid SendGrid API Key")
    os.environ["SENDGRID_API_KEY"] = "short"
    ok, msg = await verify_smtp_credentials()
    print("Verification result:", ok)
    print("Message:", msg)
    assert not ok
    assert "SendGrid API Key is too short" in msg
    os.environ.pop("SENDGRID_API_KEY")

    # 3. Test when invalid SMTP credentials are configured (using Gmail ending)
    print("\nTest 3: Invalid SMTP Credentials (Gmail)")
    os.environ["EMAIL_ADDRESS"] = "vyomtest@gmail.com"
    os.environ["EMAIL_PASSWORD"] = "wrongpassword"
    
    ok, msg = await verify_smtp_credentials()
    print("Verification result:", ok)
    print("Message:", msg)
    assert not ok
    assert "SMTP Connection/Auth failed" in msg
    assert "App Password required" in msg

    # Restore original environment
    for k, v in orig_env.items():
        if v is not None:
            os.environ[k] = v
        else:
            os.environ.pop(k, None)

    print("\n--- All Tests Passed! ---")

if __name__ == "__main__":
    asyncio.run(run_tests())
