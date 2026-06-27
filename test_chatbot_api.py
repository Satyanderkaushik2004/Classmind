import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
import httpx

async def test_endpoint():
    url = "http://localhost:8000/api/ai/chatbot"
    
    # Payload 1: General VYOM platform question (RAG check)
    payload_rag = {
        "message": "Explain what the Waiting Room does and how to use it.",
        "history": [],
        "language": "en",
        "role": "teacher"
    }
    
    # Payload 2: Out of scope request (Guardrail check)
    payload_scope = {
        "message": "Who is celebrity gossip today? Tell me who dated whom.",
        "history": [],
        "language": "en",
        "role": "teacher"
    }

    # Payload 3: Hindi response check
    payload_hindi = {
        "message": "Who is the president of USA?",
        "history": [],
        "language": "hi",
        "role": "teacher"
    }

    print("Note: Ensure you have started the server on port 8000 using 'python main.py' or 'run_server.bat' to test these requests live.")
    
    # Let's test the endpoint directly by mocking the FastAPI call locally if we can,
    # or just try connecting to local server.
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            print("\nSending RAG query to local server...")
            resp = await client.post(url, json=payload_rag)
            print(f"Status Code: {resp.status_code}")
            print(f"Response: {resp.json().get('response')[:300]}...")
            
            print("\nSending Out-Of-Scope query to local server...")
            resp = await client.post(url, json=payload_scope)
            print(f"Status Code: {resp.status_code}")
            print(f"Response: {resp.json().get('response')}")
    except Exception as e:
        print(f"\nCould not connect to local server for live tests: {e}")
        print("We can test by directly calling the python function `ai_chatbot` using a mock request!")
        
        # Mocking the FastAPI call locally without running the HTTP server:
        import uvicorn
        from main import ai_chatbot, ChatbotRequest
        
        req_rag = ChatbotRequest(**payload_rag)
        print("\nDirect call test (RAG query):")
        res_rag = await ai_chatbot(req_rag)
        print("Response:", res_rag.get("response")[:300] + "...")
        print("Source:", res_rag.get("source"))

        req_scope = ChatbotRequest(**payload_scope)
        print("\nDirect call test (Out of Scope):")
        res_scope = await ai_chatbot(req_scope)
        print("Response:", res_scope.get("response"))
        print("Source:", res_scope.get("source"))

        req_hindi = ChatbotRequest(**payload_hindi)
        print("\nDirect call test (Hindi Out of Scope Refusal):")
        res_hindi = await ai_chatbot(req_hindi)
        print("Response:", res_hindi.get("response"))
        print("Source:", res_hindi.get("source"))

if __name__ == "__main__":
    asyncio.run(test_endpoint())
