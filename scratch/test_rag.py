import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import asyncio
from rag_engine import RagEngine

async def test_search():
    engine = RagEngine()
    print("Testing search for: 'attendance report'")
    results = await engine.retrieve("attendance report", top_n=3)
    for i, res in enumerate(results):
        print(f"\n[{i+1}] Source: {res['source']} - Section: {res['section']} (ID: {res['id']})")
        print("-" * 60)
        print(res['text'][:200] + "...")

    print("\n" + "="*80)
    print("Testing search for: 'cheating warning in test mode'")
    results2 = await engine.retrieve("cheating warning in test mode", top_n=2)
    for i, res in enumerate(results2):
        print(f"\n[{i+1}] Source: {res['source']} - Section: {res['section']} (ID: {res['id']})")
        print("-" * 60)
        print(res['text'][:200] + "...")

if __name__ == "__main__":
    asyncio.run(test_search())
