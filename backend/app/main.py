"""FastAPI application. Thin layer: all logic lives in service.py / workflow.py.

Run:  uvicorn app.main:app --reload --port 8000     (from the backend/ directory)
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import PROJECT_DIR, Settings
from .service import InputError, JobManager

logging.basicConfig(level=logging.INFO)

settings = Settings.from_env()
manager = JobManager(settings)

app = FastAPI(title="CodePilotX", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
    allow_methods=["GET", "POST"],
    allow_headers=["content-type"],
)


class JobRequest(BaseModel):
    repo_url: str = Field(..., max_length=300, description="https://github.com/<owner>/<repo> or sample:<name>")
    issue: str = Field(..., max_length=4000)


@app.get("/api/health")
def health():
    return manager.health()


@app.get("/api/samples")
def samples():
    return manager.samples()


@app.post("/api/jobs", status_code=202)
def create_job(req: JobRequest):
    try:
        return {"job_id": manager.submit(req.repo_url, req.issue)}
    except InputError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    job = manager.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Unknown job id (the server may have restarted).")
    return job


# Optional single-process deployment: serve the built React app if it exists.
_dist = PROJECT_DIR / "frontend" / "dist"
if _dist.is_dir():
    app.mount("/", StaticFiles(directory=str(_dist), html=True), name="frontend")
