"""Clipper web server: serves the landing page and runs clip jobs one at a time in a background worker."""
from __future__ import annotations

import json
import queue
import re
import threading
import time
import traceback
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from pipeline import run_job

ROOT = Path(__file__).resolve().parent.parent
STATIC = ROOT / "web"
JOBS = ROOT / "jobs"
JOBS.mkdir(exist_ok=True)

URL_PATTERNS = {
    "youtube": re.compile(r"^https?://(www\.|m\.|music\.)?(youtube\.com/(watch\?|live/|shorts/)|youtu\.be/)\S+$", re.I),
    "twitch": re.compile(r"^https?://(www\.|m\.)?twitch\.tv/(videos/\d+|\w+/(clip|video)/\S+)", re.I),
    "kick": re.compile(r"^https?://(www\.)?kick\.com/\S+/(videos|clips)/\S+", re.I),
}

app = FastAPI(title="Clipper")
jobs: dict[str, dict] = {}
work: "queue.Queue[str]" = queue.Queue()
lock = threading.Lock()


class JobRequest(BaseModel):
    url: str
    max_clips: int = Field(6, ge=1, le=20)
    captions: bool = True
    highlight: str = Field("#FFE600", pattern=r"^#[0-9a-fA-F]{6}$")


def _save(job: dict) -> None:
    (JOBS / job["id"] / "job.json").write_text(json.dumps(job, ensure_ascii=False, indent=1), encoding="utf-8")


def _update(job_id: str, **fields) -> None:
    with lock:
        jobs[job_id].update(fields, updated=time.time())
        _save(jobs[job_id])


def _worker() -> None:
    while True:
        job_id = work.get()
        job = jobs[job_id]
        job_dir = JOBS / job_id

        def progress(stage: str, frac: float, msg: str) -> None:
            _update(job_id, status="running", stage=stage, stage_progress=round(frac, 3), message=msg)

        try:
            opts = {"max_clips": job["max_clips"], "captions": job["captions"], "style": {"highlight": job["highlight"]}}
            result = run_job(job["url"], job_dir, opts, progress)
            _update(job_id, status="done", stage="done", stage_progress=1, message="Clips ready", **result)
        except Exception as e:
            traceback.print_exc()
            _update(job_id, status="error", message=str(e) or type(e).__name__)
        finally:
            work.task_done()


@app.on_event("startup")
def _startup() -> None:
    # reload finished jobs from disk so the gallery survives restarts
    for f in JOBS.glob("*/job.json"):
        try:
            j = json.loads(f.read_text(encoding="utf-8"))
            if j.get("status") in ("queued", "running"):
                j.update(status="error", message="Server restarted while this job was running")
            jobs[j["id"]] = j
        except Exception:
            pass
    threading.Thread(target=_worker, daemon=True).start()


@app.post("/api/jobs")
def create_job(req: JobRequest) -> dict:
    url = req.url.strip()
    platform = next((p for p, rx in URL_PATTERNS.items() if rx.match(url)), None)
    if not platform:
        raise HTTPException(400, "That doesn't look like a YouTube, Twitch or Kick video link.")
    job_id = uuid.uuid4().hex[:12]
    (JOBS / job_id).mkdir()
    job = {
        "id": job_id, "url": url, "platform": platform, "status": "queued", "stage": "queued",
        "stage_progress": 0, "message": "Waiting in line…", "created": time.time(), "updated": time.time(),
        "max_clips": req.max_clips, "captions": req.captions, "highlight": req.highlight,
        "clips": [], "meta": {},
    }
    with lock:
        jobs[job_id] = job
        _save(job)
    work.put(job_id)
    return {"id": job_id, "position": work.qsize()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/jobs")
def list_jobs() -> list[dict]:
    return sorted(
        ({k: j.get(k) for k in ("id", "url", "status", "created", "meta", "clips")} for j in jobs.values()),
        key=lambda j: -j["created"],
    )[:20]


@app.get("/media/{job_id}/{name}")
def media(job_id: str, name: str, download: bool = False):
    if not re.fullmatch(r"[0-9a-f]{12}", job_id) or not re.fullmatch(r"clip_\d{2}\.(mp4|jpg)", name):
        raise HTTPException(404)
    path = JOBS / job_id / name
    if not path.exists():
        raise HTTPException(404)
    return FileResponse(path, filename=name if download else None)


for page in ("youtube-clip-maker", "twitch-clip-maker", "kick-clip-maker"):
    app.add_api_route(f"/{page}", lambda: FileResponse(STATIC / "index.html"), include_in_schema=False)

app.mount("/", StaticFiles(directory=STATIC, html=True), name="web")
