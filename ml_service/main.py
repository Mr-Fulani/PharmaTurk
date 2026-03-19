"""Minimal FastAPI service stub for future ML/embeddings (per TZ)."""

from fastapi import FastAPI

app = FastAPI(title="ML Service", description="Optional ML/embeddings service for PharmaTurk AI")


@app.get("/health")
def health():
    """Health check for orchestration/load balancers."""
    return {"status": "ok"}
