"""Run demo cases through Gemini and compare the extraction with truth.json.

Usage: .venv/Scripts/python.exe scripts/check_extraction.py [case_id ...]
"""
import asyncio, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.stdout.reconfigure(encoding="utf-8")

from app.pipeline import DEMO_DIR, audit_demo, load_report


def diff(a, b, path=""):
    out = []
    if isinstance(a, dict):
        for k in a:
            out += diff(a[k], b.get(k) if isinstance(b, dict) else None, f"{path}.{k}")
    elif isinstance(a, list):
        if not isinstance(b, list) or len(a) != len(b):
            out.append(f"{path}: expected {len(a)} items, got {len(b) if isinstance(b, list) else b}")
        else:
            for i, (x, y) in enumerate(zip(a, b)):
                out += diff(x, y, f"{path}[{i}]")
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if abs(a - b) > 0.5:
            out.append(f"{path}: expected {a}, got {b}")
    elif path.endswith(("category", "reason_type", "follows_differential_billing", "consumables_cover", "days")) and a != b:
        out.append(f"{path}: expected {a!r}, got {b!r}")
    return out


async def main(ids):
    for cid in ids:
        report = await audit_demo(cid, fresh=True)
        _, docs = load_report(cid)
        truth = json.loads((DEMO_DIR / cid / "truth.json").read_text(encoding="utf-8"))
        problems = []
        for part in ("bill", "settlement", "policy"):
            problems += diff(truth[part], docs.model_dump(mode="json")[part], part)
        exp = truth["expected"]
        print(f"\n== {cid}: recoverable {report.recoverable} (expected {exp['recoverable']}), "
              f"to_clarify {report.to_clarify} (expected {exp['to_clarify']})")
        print("   extraction mismatches:", problems or "none")
        for i, f in enumerate(report.findings):
            print(f"   [{f.verdict.value}] {f.title}: Rs {f.amount:,.0f}")
            print(f"      HI: {report.explanations_hi.get(str(i), '')}")


ids = sys.argv[1:] or sorted(p.name for p in DEMO_DIR.iterdir() if (p / "truth.json").exists())
asyncio.run(main(ids))
