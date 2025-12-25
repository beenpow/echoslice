# EchoSlice Backend (FastAPI)

## Run (dev)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

## Health Check
- GET http://localhost:8000/health
