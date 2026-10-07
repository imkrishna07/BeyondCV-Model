# BeyondCV AI Service

A Python 3.13 FastAPI service scaffold for BeyondCV. This repository contains
only the service foundation and a health check; candidate analyzers and ranking
logic are intentionally not implemented yet.

## Setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
```

## Run

```bash
uvicorn app.main:app --reload
```

The API listens at `http://127.0.0.1:8000`. Open
`http://127.0.0.1:8000/docs` for the interactive API documentation.

## Health check

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{"status":"ok","service":"beyondcv-ai"}
```

## Tests

```bash
python -m unittest discover -s tests -v
```

## Structure

```text
app/
├── main.py
├── api/          # HTTP routes
├── analyzers/    # Future independent candidate analyzers
├── ranking/      # Future ranking logic
├── schemas/      # Pydantic request/response models
├── services/     # Shared service integrations
└── config.py
tests/
```
