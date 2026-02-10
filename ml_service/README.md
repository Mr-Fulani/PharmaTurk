# ML Service (stub)

Optional separate FastAPI service for ML workloads (embeddings, categorization) per TZ.  
The main backend currently uses LLM/Qdrant directly; this service is a placeholder for future offload.

## Run (Poetry)

```bash
cd ml_service
poetry install
poetry run uvicorn main:app --host 0.0.0.0 --port 8001
```

- Health: `GET http://localhost:8001/health` → `{"status": "ok"}`

## Docker (optional)

При желании можно добавить сервис `ml_service` в корневой `docker-compose.yml` с образом на основе этого каталога (Dockerfile с Poetry) и портом 8001.

## Later

- Add an embeddings endpoint (e.g. `POST /embed` with text → vector) and call it from the backend instead of LLM client.
- Add categorization endpoint if you move category model here.
- Wire the backend to use it via env (e.g. `ML_SERVICE_URL`).
