# M07 — Mock Bureau & Policy-Based Eligibility Engine

> **AgentFinance AI** · Module 07 · Isolated mock credit bureau microservice on **port 8001**

## Quick Start

```bash
# Install dependencies
cd module07
pip install -r requirements.txt

# Run the server
python -m app.main
# → http://localhost:8001
# → Swagger UI: http://localhost:8001/docs

# Run tests
python -m pytest tests/ -v
```

## Docker

```bash
docker build -t bureau-mock .
docker run -p 8001:8001 bureau-mock
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Service health check |
| `GET` | `/api/bureau/seed` | List all seed applicant IDs |
| `GET` | `/api/bureau/{applicant_id}` | **Mock bureau check + eligibility decision** |
| `POST` | `/api/bureau/evaluate` | Evaluate eligibility from parsed (document) payload |
| `GET` | `/api/mock/fraud-score/{applicant_id}` | Standalone M06 fraud score mock |
| `GET` | `/api/mock/liveness/{applicant_id}` | Standalone M04 liveness mock |
| `GET` | `/api/mock/consent/{applicant_id}` | Standalone M03 consent mock |
| `POST` | `/api/docs/upload` | Upload PDF, OCR/extract text, parse required fields |
| `GET` | `/api/docs/{doc_id}` | Fetch parsed placeholder record |

### Bureau Check — Query Parameter Overrides

Override cross-module signals when testing:

```
GET /api/bureau/PRIYA-001?fraud_score=85&liveness_avg=0.3&consent_detected=false&session_id=<uuid>
```

## Eligibility Rules (R01–R08)

| Rule | Field | Op | Threshold | On Fail |
|------|-------|----|-----------|---------|
| R01 | credit_score | >= | 650 | REJECT |
| R02 | written_off_accounts | == | 0 | REJECT |
| R03 | foir | <= | 0.50 | REJECT |
| R04 | dpd_last_12m | == | None | REFER |
| R05 | active_loan_count | <= | 4 | REFER |
| R06 | fraud_score (M06) | <= | 60 | REJECT |
| R07 | liveness_avg (M04) | >= | 0.6 | REJECT |
| R08 | consent_detected (M03) | == | true | HALT |

Rules are configurable via `data/rules_config.json`.

## Addendum Flow — PDF Ingestion to Decision

1. Upload PDF using `POST /api/docs/upload`
2. Service extracts text (`pypdf`, OCR fallback via `pdf2image` + `pytesseract`)
3. Parser maps text into required bureau/scoring fields
4. Parsed record stored in in-memory placeholder store
5. Call `POST /api/bureau/evaluate` with parsed payload
6. Service derives `credit_score`, runs R01–R08, returns decision

## Demo Personas

| ID | Name | Score | Expected Decision | Key Trigger |
|----|------|-------|-------------------|-------------|
| PRIYA-001 | Priya Sharma | 740 | PASS | All rules pass |
| ROHIT-002 | Rohit X | 580 | REJECT | R01 + R06 + R07 |
| MEERA-003 | Meera Patil | 680 | REFER | R04 (recent DPD) |

## Architecture

```
app/
├── main.py              # FastAPI entrypoint
├── config.py            # Settings & cross-module defaults
├── models.py            # Pydantic schemas (bureau_responses DDL)
├── scoring.py           # Weighted CIBIL score calculator
├── rules_engine.py      # R01–R08 eligibility gates
├── decision.py          # PASS / REFER / REJECT aggregator
├── document_pipeline.py # PDF extraction/OCR + field parser
├── standalone_mocks.py  # fraud/liveness/consent mock functions
├── repositories/
│   └── doc_store.py     # In-memory parsed-document placeholder DB
└── routes/
    ├── bureau.py        # GET /api/bureau/{applicant_id}
    ├── health.py        # GET /health
    ├── mocks.py         # Standalone mock endpoints
    └── docs.py          # PDF upload/get parsed record
```
