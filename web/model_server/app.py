"""ReportLens model server: Qwen3-VL-4B (+ the chart-to-table LoRA) and DePlot behind a small job API.

Runs as a Hugging Face Space (Docker). The verifier's models/remote.py is the client. The model code is the
verifier's own (chart_claim_verifier/models/vlm.py and tools/deplot.py, copied in by deploy.py), so a remote
answer is the same as a local one on the same hardware.

    POST /jobs        {"task": "generate", "prompt", "images": [base64 PNG], "temperature", "max_new_tokens", "n", "adapter"}
                      {"task": "deplot", "image": base64 PNG}                        -> {"id"}
    GET  /jobs/{id}   {"status": queued|running|done|failed, "result" | "error"}
    GET  /health      whether the models are loaded, device, dtype, queue length

Jobs run one at a time (a CPU Space has two cores; parallel generation would only thrash).
"""
from __future__ import annotations

import base64
import io
import os
import queue
import threading
import time
import traceback
import uuid

import hmac

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

VLM_ID = os.environ.get("VLM_ID", "Qwen/Qwen3-VL-4B-Instruct")
LORA_REPO = os.environ.get("LORA_REPO", "")                 # empty = base model only
DEPLOT_ID = os.environ.get("DEPLOT_ID", "google/deplot")
LOAD = {m.strip() for m in os.environ.get("LOAD", "vlm,deplot").split(",") if m.strip()}   # "deplot" alone for a local test
SERVER_KEY = os.environ.get("SERVER_KEY", "")   # set it whenever the server is reachable without HF's own login (Kaggle, Colab, a VM)
KEEP_S = 3600                                               # finished jobs are forgotten after an hour
MAX_IMAGES, MAX_IMAGE_BYTES = 4, 8 * 1024 * 1024

def check_key(authorization: str = Header(default="")) -> None:
    if SERVER_KEY and not hmac.compare_digest(authorization, f"Bearer {SERVER_KEY}"):
        raise HTTPException(401, "missing or wrong key")


app = FastAPI(title="ReportLens model server", dependencies=[Depends(check_key)])
state = {"ready": False, "error": None, "device": None, "dtype": None, "loaded_s": None}
models: dict = {}
jobs: dict[str, dict] = {}
work: queue.Queue = queue.Queue()


def load_models() -> None:
    t0 = time.time()
    try:
        import torch
        from huggingface_hub import snapshot_download

        from chart_claim_verifier.models.vlm import VLM, best_device
        from chart_claim_verifier.tools.deplot import DePlotTool

        device = best_device()
        dtype = os.environ.get("DTYPE") or ("float16" if device == "cuda" else "bfloat16")
        if "vlm" in LOAD:
            adapter = snapshot_download(LORA_REPO) if LORA_REPO else None
            models["vlm"] = VLM(VLM_ID, dtype, adapter)
            dtype = str(models["vlm"].model.dtype).replace("torch.", "")
        if "deplot" in LOAD:
            models["deplot"] = DePlotTool(None, DEPLOT_ID)
            models["deplot"]._load()
        state.update(ready=True, device=device, dtype=dtype, loaded=sorted(models),
                     loaded_s=round(time.time() - t0), threads=torch.get_num_threads())
    except Exception as e:                                  # shown by /health instead of a crash loop
        state["error"] = f"{type(e).__name__}: {e}"
        traceback.print_exc()


def image(b64: str):
    from PIL import Image
    raw = base64.b64decode(b64, validate=True)
    if len(raw) > MAX_IMAGE_BYTES:
        raise ValueError("image too large")
    return Image.open(io.BytesIO(raw)).convert("RGB")


def run(job: dict) -> dict:
    p = job["payload"]
    need = "vlm" if p["task"] == "generate" else "deplot"
    if need not in models:
        raise RuntimeError(f"{need} is not loaded on this server (LOAD={','.join(sorted(LOAD))})")
    if p["task"] == "generate":
        texts = models["vlm"].generate(p["prompt"], [image(i) for i in p["images"]], temperature=p["temperature"],
                                       max_new_tokens=p["max_new_tokens"], n=p["n"], adapter=p["adapter"])
        return {"texts": texts}
    return {"text": models["deplot"].linearize(image(p["image"]))}


def worker() -> None:
    while True:
        jid = work.get()
        job = jobs.get(jid)
        if job is None:
            continue
        job.update(status="running", started=time.time())
        try:
            job.update(status="done", result=run(job))
        except Exception as e:
            job.update(status="failed", error=f"{type(e).__name__}: {e}"[:1000])
            traceback.print_exc()
        job["finished"] = time.time()
        job.pop("payload", None)                            # drop the images once answered


@app.on_event("startup")
def startup() -> None:
    threading.Thread(target=load_models, daemon=True).start()
    threading.Thread(target=worker, daemon=True).start()


class JobIn(BaseModel):
    task: str = Field(pattern="^(generate|deplot)$")
    prompt: str = Field(default="", max_length=20000)
    images: list[str] = Field(default_factory=list, max_length=MAX_IMAGES)
    image: str = ""
    temperature: float = Field(default=0.0, ge=0, le=2)
    max_new_tokens: int = Field(default=256, ge=1, le=1024)
    n: int = Field(default=1, ge=1, le=8)
    adapter: bool = False


@app.get("/")
def root():
    return {"service": "ReportLens model server", "health": "/health"}


@app.get("/health")
def health():
    return {**state, "vlm": VLM_ID, "lora": LORA_REPO or None, "deplot": DEPLOT_ID,
            "queued": work.qsize(), "running": sum(j["status"] == "running" for j in jobs.values())}


@app.post("/jobs")
def submit(body: JobIn):
    if state["error"]:
        raise HTTPException(503, f"models failed to load: {state['error']}")
    if not state["ready"]:
        raise HTTPException(503, "models are still loading")
    if body.task == "deplot" and not body.image:
        raise HTTPException(422, "deplot needs an image")
    now = time.time()
    for k in [k for k, j in jobs.items() if j.get("finished", now) < now - KEEP_S]:
        jobs.pop(k, None)
    jid = uuid.uuid4().hex
    jobs[jid] = {"status": "queued", "created": now, "payload": body.model_dump()}
    work.put(jid)
    return {"id": jid}


@app.get("/jobs/{jid}")
def status(jid: str):
    j = jobs.get(jid)
    if j is None:
        raise HTTPException(404, "unknown job (finished jobs are kept for an hour)")
    return {k: j[k] for k in ("status", "result", "error") if k in j}
