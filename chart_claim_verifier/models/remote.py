"""Models served by the ReportLens model server (web/model_server, a Hugging Face Space) instead of loaded here.

Set `models.remote_url` in the config (or CCV_REMOTE_URL) to the server URL. The bearer token sent is
CCV_REMOTE_KEY (a server's own key), else HF_TOKEN / the saved Hugging Face login (a private Space). The server runs the same `VLM` class and DePlot code as a local run, so prompts, decoding and cache
keys are unchanged: only where the forward pass happens moves.

Calls are jobs (submit, then poll) because a CPU Space can take minutes per answer, longer than a proxy keeps
one HTTP request open.
"""
from __future__ import annotations

import base64
import io
import os
import time
from typing import Sequence

import requests


class RemoteError(RuntimeError):
    pass


class ModelServer:
    def __init__(self, url: str, token: str | None = None, timeout_s: float = 3600, poll_s: float = 3,
                 ready_timeout_s: float = 1800):
        self.url = url.rstrip("/")
        self.token = token if token is not None else _hf_token()
        self.timeout_s, self.poll_s, self.ready_timeout_s = timeout_s, poll_s, ready_timeout_s
        self._ready = False
        self.http = requests.Session()
        if self.token:
            self.http.headers["Authorization"] = f"Bearer {self.token}"

    def _call(self, method: str, path: str, **kw) -> dict:
        for attempt in range(5):                     # the Space may be waking up or briefly unreachable
            try:
                r = self.http.request(method, self.url + path, timeout=60, **kw)
            except requests.RequestException as e:
                err = f"{type(e).__name__}: {e}"
            else:
                if r.status_code < 500 and r.status_code != 429:
                    if not r.ok:
                        raise RemoteError(f"model server {path}: HTTP {r.status_code} {r.text[:300]}")
                    return r.json()
                err = f"HTTP {r.status_code}"
            time.sleep(5 * (attempt + 1))
        raise RemoteError(f"model server {path} unreachable: {err}")

    def wait_ready(self) -> dict:
        """A sleeping Space wakes on the first request and then downloads and loads the models (minutes)."""
        end = time.monotonic() + self.ready_timeout_s
        last = "no answer"
        while time.monotonic() < end:
            try:
                r = self.http.get(self.url + "/health", timeout=60)
                if r.ok:
                    h = r.json()
                    if h.get("error"):
                        raise RemoteError(f"model server could not load its models: {h['error']}")
                    if h.get("ready"):
                        self._ready = True
                        return h
                    last = "loading models"
                elif r.status_code in (401, 403, 404):
                    raise RemoteError(f"model server {self.url}: HTTP {r.status_code}; check the URL and HF_TOKEN")
                else:
                    last = f"HTTP {r.status_code}"
            except requests.RequestException as e:
                last = type(e).__name__
            time.sleep(10)
        raise RemoteError(f"model server not ready after {self.ready_timeout_s:.0f}s ({last})")

    def run(self, task: str, payload: dict) -> dict:
        """Submit one job and wait for its result."""
        if not self._ready:
            self.wait_ready()
        job = self._call("POST", "/jobs", json={"task": task, **payload})["id"]
        end = time.monotonic() + self.timeout_s
        while time.monotonic() < end:
            j = self._call("GET", f"/jobs/{job}")
            if j["status"] == "done":
                return j["result"]
            if j["status"] == "failed":
                raise RemoteError(f"model server {task} failed: {j.get('error')}")
            time.sleep(self.poll_s)
        raise RemoteError(f"model server {task} did not answer within {self.timeout_s:.0f}s")

    def health(self) -> dict:
        return self._call("GET", "/health")


def _hf_token() -> str | None:
    """CCV_REMOTE_KEY (the server's own SERVER_KEY, for a server outside Hugging Face), else HF_TOKEN, else the
    token saved by `hf auth login` on this machine (for a private Space)."""
    if os.environ.get("CCV_REMOTE_KEY"):
        return os.environ["CCV_REMOTE_KEY"]
    if os.environ.get("HF_TOKEN"):
        return os.environ["HF_TOKEN"]
    try:
        from huggingface_hub import get_token
        return get_token()
    except Exception:
        return None


def encode_image(img) -> str:
    """Path or PIL image -> base64 PNG."""
    from PIL import Image
    im = Image.open(img) if isinstance(img, str) else img
    buf = io.BytesIO()
    im.convert("RGB").save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


class RemoteVLM:
    """Same interface and names as models.vlm.VLM, so the reading cache keys do not change."""

    def __init__(self, server: ModelServer, model_id: str, lora_adapter: str | None = None):
        self.server = server
        self.base_name = model_id
        self.name = model_id + (f"+{lora_adapter}" if lora_adapter else "")
        self.has_adapter = bool(lora_adapter)

    def generate(self, prompt, images: Sequence = (), temperature=0.0, max_new_tokens=256, n=1, adapter=False):
        out = self.server.run("generate", {
            "prompt": prompt, "images": [encode_image(i) for i in images], "temperature": temperature,
            "max_new_tokens": max_new_tokens, "n": n, "adapter": bool(adapter and self.has_adapter)})
        return out["texts"]


def server_from_config(models_cfg: dict) -> ModelServer | None:
    url = os.environ.get("CCV_REMOTE_URL") or models_cfg.get("remote_url")
    return ModelServer(url) if url else None
