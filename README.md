# ClaimRight

**An independent auditor for Indian health insurance claims.**

When an insurer settles a hospital claim for less than the bill, families rarely know whether the cuts were legitimate. ClaimRight checks them. Upload the **hospital bill**, the **insurer's settlement letter** and the **policy**. ClaimRight lists every deduction, marks each one **Wrong / Looks right / Needs a human** against IRDAI rules and your own policy wording, shows how many rupees you can claim back, and drafts the complaint letter in **English and Hindi** with dated escalation steps (insurer → Bima Bharosa → Insurance Ombudsman).

Built by **Team Aviti** for the Google Startup Buildathon India 2026 (City Buildathon, 20–21 Nov 2026).

> **AI reads and talks; code decides.** Gemini extracts data from the documents and explains the findings. All ₹ arithmetic and every pass/fail decision is made by a deterministic Python rules engine, never by the model.

## Features

- **Claim audit**: upload 3 PDFs and get a line-by-line verdict on every deduction, the ₹ recoverable, and the rule behind each flag with a source link.
- **Complaint letters** in English and Hindi, with escalation dates.
- **Ask ClaimRight**: a chat agent (English, Hindi or Hinglish) that answers questions about your case using tools, not guesses. For example, "Why was ₹12,000 cut?" or "What do I do if they don't reply?"
- **Hospital pre-check** (`/hospital.html`): a billing-desk panel that catches problems *before* the claim is filed, such as room-rent overruns, non-payable items and missing reasons. It runs as pure Python with no AI call.
- **Insurer report card**: audits are written to BigQuery, so a data agent can answer questions like "Which insurer makes the most wrong room-rent cuts?" (on clearly labelled synthetic data).
- **Evaluated**: an agent evaluation scorecard covers tool routing, grounded amounts, language and faithfulness (see `claimright/eval/scorecard.md`).

## The rules engine

| ID | Check |
| --- | --- |
| R1 | Proportionate (room-rent) deduction can't touch medicines, consumables, implants or tests |
| R1-ICU | No proportionate deduction on ICU charges |
| R1-DB | No proportionate deduction if the hospital doesn't bill by room category |
| R2 | Consumables are covered if the policy has a consumables benefit |
| R3 | A hospital discount must reach the policyholder |
| R4 | Every deduction needs a written reason |
| R5 | The numbers must add up |
| R6 | Only limits written in your policy can be applied |
| R7 | Excess room rent must be calculated correctly |

Rules live in `claimright/app/rules/irdai_rules.json`, and a copy is kept in BigQuery. When a check isn't sure, it returns **Needs a human** instead of guessing.

## Architecture

```
Browser (family app / hospital desk)
   │  upload 3 documents · chat
   ▼
Cloud Run: ClaimRight (Python, FastAPI + Google ADK)
   ├─ Audit pipeline (fixed steps, same answer every time)
   │    1. Extract  Gemini Flash → strict JSON (Pydantic schemas)
   │    2. Check    rules engine in plain Python (all ₹ maths here)
   │    3. Explain  Gemini → plain-language reason per flag, EN + HI
   │    4. Save     audit rows → BigQuery
   │
   └─ "Ask ClaimRight" ADK agent (Gemini)
        tools: get_case_audit, explain_rule, get_next_steps,
               draft_complaint_letter, insurer_track_record
                          │
                          ▼
               MCP Toolbox (Cloud Run) → BigQuery
```

## Tech stack

Python · FastAPI · Google ADK · Gemini (Vertex AI or AI Studio) · BigQuery · MCP Toolbox for Databases · Cloud Run · Pydantic · pytest

## Getting started

### Prerequisites

- Python 3.11+
- **Either** a Google Cloud project with Vertex AI enabled, **or** a free [AI Studio](https://aistudio.google.com) API key

### Install

```bash
cd claimright
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
cp .env.example .env    # then edit .env
```

### Configure

| Variable | Description |
| --- | --- |
| `GOOGLE_GENAI_USE_VERTEXAI` | `TRUE` for Vertex AI, `FALSE` for an AI Studio key |
| `GOOGLE_CLOUD_PROJECT` / `GOOGLE_CLOUD_LOCATION` | Your GCP project and region (Vertex AI only) |
| `GOOGLE_API_KEY` | AI Studio key (only when not using Vertex AI) |
| `MODEL_EXTRACT`, `MODEL_EXPLAIN`, `MODEL_DRAFT`, `MODEL_DRAFT_FALLBACK` | Gemini model IDs for each step |
| `TOOLBOX_URL` | Optional. MCP Toolbox service URL for the insurer report-card tool |
| `RECORD_AUDITS` | `false` to skip writing audits to BigQuery |

### Run

```bash
uvicorn app.main:app --reload --port 8080
```

Open [http://localhost:8080](http://localhost:8080). There are three synthetic demo cases (dengue in Delhi, knee replacement in Pune, appendix surgery in Bengaluru) under **Demo**. The classic UI is at `/classic/`, and the hospital desk is at `/hospital.html`.

On Windows there is also a one-command free-tier launcher. Put `GOOGLE_API_KEY=...` in `claimright/.env.free`, then:

```powershell
cd claimright
.\start_local_demo.ps1
```

### Tests

```bash
cd claimright
pip install -r requirements-dev.txt
pytest
```

### Deploy to Cloud Run

```bash
cd claimright
gcloud run deploy claimright --source . --region us-central1
```

## API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/api/health` | Health check |
| GET | `/api/rules` | The rules catalogue |
| GET | `/api/demo-cases` | List the demo cases |
| POST | `/api/demo/{case_id}` | Run a demo case |
| POST | `/api/audit` | Audit uploaded documents |
| GET | `/api/report/{case_id}` | Get an audit report |
| POST | `/api/letter/{case_id}` | Draft a complaint letter (EN/HI) |
| POST | `/api/chat/{case_id}` | Ask ClaimRight about a case |
| POST | `/api/precheck` | Hospital pre-check |

## Repository layout

```
claimright/
  app/            FastAPI app, extraction, pipeline, ADK agent, BigQuery access
  app/rules/      Rules engine + IRDAI rule catalogue
  web/            Family app, classic UI, hospital desk
  demo/cases/     3 synthetic cases (bill, settlement, policy PDFs + expected results)
  data/           Synthetic audit rows, rule data
  eval/           Agent evaluation + scorecard
  scripts/        Demo PDF / synthetic data generators, helpers
  tests/          pytest suites for the rules engine and pre-check
  toolbox/        MCP Toolbox tool definitions (tools.yaml)
  Dockerfile
deck/             Pitch decks (idea + final prototype) and generators
logo/             Team Aviti logos
```

The MCP Toolbox binary isn't included because of its size. Download it from [googleapis/genai-toolbox](https://github.com/googleapis/genai-toolbox) and place it in `claimright/toolbox/`.

## Disclaimer

All demo data is **synthetic**: fake patients, hospitals and policy numbers, with insurers named "Insurer A–E". ClaimRight points to the rule; you decide whether to file. It is not legal advice, and disputes that turn on judgement should go to a lawyer.
