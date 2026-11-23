"""Ask the agent a few questions. Usage: .venv/Scripts/python.exe scripts/try_agent.py"""
import asyncio, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")
from app.agent import chat
from app.pipeline import audit_demo

QUESTIONS = [
    ("dengue_delhi", "Why did they cut 10,500 from my medicines?"),
    ("dengue_delhi", "Which IRDAI rule says that? Give me the source."),
    ("knee_pune", "मेरा क्लेम क्यों कटा? कितना पैसा वापस मिल सकता है?"),
    ("appendix_bengaluru", "Should I complain about my claim?"),
]

async def main():
    sessions = {}
    for case_id, q in QUESTIONS:
        await audit_demo(case_id)  # cached, no Gemini cost
        r = await chat(case_id, q, sessions.get(case_id))
        sessions[case_id] = r["session_id"]
        print(f"\n[{case_id}] Q: {q}\n   tools: {r['tools_used']}\n   A: {r['reply']}")

asyncio.run(main())
