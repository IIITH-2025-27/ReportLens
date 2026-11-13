# Model server

Runs the verifier's two neural models, Qwen3-VL-4B (with the chart-to-table LoRA) and DePlot, on a machine
with a GPU, so the web backend can run anywhere. OCR and everything else in the verifier stay in the backend.

```
backend (verifier) --HTTPS jobs--> model server (app.py) --> Qwen3-VL-4B + LoRA, DePlot
```

The server imports the verifier's own model code (`chart_claim_verifier/models/vlm.py`, `tools/deplot.py`),
so prompts and decoding are the same as a local run. The client is `chart_claim_verifier/models/remote.py`.

## Where the models live

| Model | Hugging Face repo |
|---|---|
| Chart-to-table LoRA | `ReportLens/qwen3-vl-4b-chart2table-lora` (private; uploaded by `deploy.py`) |
| Qwen3-VL-4B-Instruct | `Qwen/Qwen3-VL-4B-Instruct` (public) |
| DePlot | `google/deplot` (public) |

Downloading the private adapter needs a Hugging Face token that can read the ReportLens org.

## Hosting

**Hugging Face Space.** `deploy.py` builds and uploads a Docker Space. Hugging Face only runs Docker Spaces
for PRO accounts or organizations on a Team plan, even on the free CPU hardware, so this needs one of those.

```bash
python web/model_server/deploy.py --skip-model --space-owner <username or org>   # add --hardware t4-small for a GPU
```

Then add a read-only token as the Space secret `HF_TOKEN`. The backend reaches a private Space with your
saved Hugging Face login (`hf auth login`) or `HF_TOKEN`.

**Kaggle (free T4 GPU, for testing).** Build the notebook, which carries the server code inside it:

```bash
python web/model_server/make_kaggle.py      # writes web/model_server/kaggle_server.ipynb (not in git)
```

On Kaggle: New notebook > File > Import notebook > pick that file. Settings: Accelerator GPU T4, Internet on
(needs a verified phone number). Add-ons > Secrets: `HF_TOKEN`, a read-only token that can read the ReportLens
org, ticked for the notebook. Keep the notebook private. Run all: the last cell waits for the models (5-10
minutes), prints `CCV_REMOTE_URL` and `CCV_REMOTE_KEY`, and keeps the server up until you stop it. The address
changes every session; sessions end after at most 12 hours and use the weekly GPU quota (about 30 hours).
Rebuild the notebook after changing the model code.

Outside Hugging Face nothing else guards the server, so always set `SERVER_KEY`.

## Point the backend at it

In `web/backend/.env`:

```
CCV_REMOTE_URL=https://....trycloudflare.com
CCV_REMOTE_KEY=<the SERVER_KEY>           # leave out for a private Hugging Face Space
```

The first call waits for the server to finish loading (`GET /health` shows `"ready": true`).

## Settings (environment variables of the server)

| Name | Default | Meaning |
|---|---|---|
| `LORA_REPO` | empty | adapter repo; empty runs the base model only |
| `VLM_ID` | `Qwen/Qwen3-VL-4B-Instruct` | base model |
| `DEPLOT_ID` | `google/deplot` | DePlot model |
| `DTYPE` | float16 on GPU, bfloat16 on CPU | model precision |
| `LOAD` | `vlm,deplot` | which models to load (`deplot` alone fits on a laptop, for testing) |
| `SERVER_KEY` | empty | bearer key clients must send |

## Calibration

The calibration tables in `calibration_tables/local` and `local_lora` were measured with float16 on Apple
silicon. A T4 or a CPU computes slightly differently; greedy decoding usually gives the same readings, but
re-read the calibration charts on the server's hardware before relying on the margins.
