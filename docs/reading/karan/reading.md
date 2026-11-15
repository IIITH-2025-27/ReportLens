# Karan · model loader, tool interface, neural tools, simulated tools, fine-tuning, pilots

You own how models are loaded and called, the interface every reading tool implements, the three neural readers
(VLM crop, VLM table, DePlot), the simulated tools used for plumbing, and the chart-to-table LoRA.

Read [00_overview.md](../00_overview.md) first. Poster questions for this area: [poster_qa.md](poster_qa.md).

---

## Level 0 · Background

| Idea | Why you need it | Read |
|---|---|---|
| Hugging Face `transformers` | `AutoProcessor`, `AutoModelForImageTextToText`, `generate`, chat templates | HF docs: "Image-text-to-text", "Chat templates", "Generation strategies" |
| Vision-language models | Qwen3-VL reads an image + prompt and writes text | Qwen-VL model card / technical report; the idea of visual tokens and `max_pixels` |
| Greedy vs sampling | tools use temperature 0 so readings are repeatable; B3 and E4 use samples | HF "Generation strategies" |
| Pix2Struct / DePlot | Tool 3 is a different model family: chart → linearised table | Liu et al., "DePlot: One-shot visual language reasoning by plot-to-table translation" (2022) |
| dtypes and memory | float16 on T4, bfloat16 / float32 on CPU; 4B parameters ≈ 8 GB in 16-bit | PyTorch docs: tensor dtypes |
| LoRA / PEFT | the chart-to-table adapter | Hu et al., "LoRA" (2021); HF PEFT docs |
| Caching and versioning | every reading is cached by tool version and image hash | `tools/cache.py` docstring |

---

## Level 1 · Read, in this order

1. **[models/vlm.py](../../../chart_claim_verifier/models/vlm.py)** — the `LLM` protocol
   (`generate(prompt, images, temperature, max_new_tokens, n, adapter)`), `VLM` (device choice, dtype rules, image size
   cap, optional 4-bit on CUDA, LoRA via PEFT, adapter switched **off** unless `adapter=True`), `OfflineLLM` for
   replays, `ScriptedLLM` for tests, `extract_json` (models add prose and code fences).
2. **[tools/base.py](../../../chart_claim_verifier/tools/base.py)** — `Tool.read` never raises: success or
   `ok=False` with an error code; cache lookup before, cache write after; `OfflineMiss` is never cached; any unexpected
   exception becomes `exception:<Type>`. `TableTool` extracts a figure's table once and looks values up with fuzzy
   names (`match_name`, `lookup`).
3. **[tools/cache.py](../../../chart_claim_verifier/tools/cache.py)** — SQLite cache keyed by
   (tool, version, image hash, series, x).
4. **[tools/registry.py](../../../chart_claim_verifier/tools/registry.py)** — builds the tools named in
   `tools.enabled`, real or simulated.
5. **[tools/vlm_table.py](../../../chart_claim_verifier/tools/vlm_table.py)** — Tool 2: whole chart → JSON table
   (`adapter=True`, so the LoRA is used here). `version` includes the model name, so base and LoRA readings never mix.
6. **[tools/vlm_crop.py](../../../chart_claim_verifier/tools/vlm_crop.py)** — Tool 1: crop around the target x with the
   y-axis strip stitched on the left, upscale 2×, put the series colour in the prompt, ask for one number. Always the
   base model.
7. **[tools/deplot.py](../../../chart_claim_verifier/tools/deplot.py)** — Tool 3: DePlot's linearised output
   (`TITLE | … <0x0A> header <0x0A> rows`) parsed into a table.
8. **[tools/legend.py](../../../chart_claim_verifier/tools/legend.py)** — the repair for `ocr_pixel`: one VLM call reads
   legend names top to bottom; paired with handles by vertical order; counts must match.
9. **[tools/simulated.py](../../../chart_claim_verifier/tools/simulated.py)** — truth + noise, with **shared** noise
   between tools of one model family so calibration and E4 have something real to find. `SimSampleTool` repeats the
   base model's mistake.
10. **[models/remote.py](../../../chart_claim_verifier/models/remote.py)** (Vikash) — the same interface over HTTP, so a
    laptop can use a GPU elsewhere.
11. **Fine-tuning:** [scripts/finetune/finetune_lora.py](../../../scripts/finetune/finetune_lora.py) (yours; trained the
    adapter on Apple silicon, one epoch, the tool's exact prompt),
    [make_sft_data.py](../../../scripts/finetune/make_sft_data.py) and [train_lora.py](../../../scripts/finetune/train_lora.py)
    (Vikash; the T4 plan: rank 16, alpha 32, attention + MLP of the language model, loss on answer tokens only — not
    run yet).
12. **Pilots and diagnostics (yours):** [scripts/pilots/pilot_legend.py](../../../scripts/pilots/pilot_legend.py),
    [pilot_legend_retrieval.py](../../../scripts/pilots/pilot_legend_retrieval.py),
    [scripts/diagnostics/bench_ocr_pixel.py](../../../scripts/diagnostics/bench_ocr_pixel.py),
    [diagnose_ocr_pixel.py](../../../scripts/diagnostics/diagnose_ocr_pixel.py).

---

## Level 2 · Run

```bash
pytest tests/test_offline.py tests/test_repair.py \
       "tests/test_claims_retrieval_safety.py::test_parse_vlm_table_and_lookup" \
       "tests/test_claims_retrieval_safety.py::test_parse_deplot" \
       "tests/test_claims_retrieval_safety.py::test_extract_json"

# simulated tools end to end (no model)
chart-claim-verifier calibrate -c configs/exp/smoke_cpu.yaml

# real models need a GPU (or the model server): see web/model_server/README.md
python web/model_server/make_kaggle.py        # notebook for a free Kaggle T4
```

Exercise: in a Python shell, build a `ScriptedLLM` that returns `'```json\n{"A": {"1": 0.5, "2": "61%"}}\n```'` and
pass it to `VlmTableTool`. Read a point with `tool.read(fig, PointQuery(series="a", x="2"))` and explain the value and
the cache entry you get.

---

## Level 3 · Full implementation

**One model, many uses.** The same `VLM` object serves `vlm_table`, `vlm_crop`, the legend repair, the LLM parser, the
LLM policy (P2) and baselines B1–B4. It is loaded once (`pipeline.Context.llm`). Anything that needs a model takes an
`LLM`, so tests use `ScriptedLLM` and replays use `OfflineLLM` without any code change.

**Adapter switching.** With a LoRA loaded, `generate(..., adapter=False)` runs inside `model.disable_adapter()`. Only
the chart-to-table task asks for the adapter. Mixing this up silently changes every other tool's readings.

**dtype rules.** float16 on CUDA / MPS; on CPU float16 falls back to float32 (slow, 2× memory), bfloat16 is kept (what
lets the 4B model fit a 16 GB CPU machine). `max_pixels = 640·28·28` caps visual tokens: charts do not need more.

**Tools never raise.** A tool bug must not crash the agent: failures are readings with error codes
(`bad_json`, `empty_table`, `series_not_found`, `x_not_found`, …). The controller and the tool profile learn from those
codes, so return the most specific code you can.

**Versions and the cache.** Cache keys include `version`. `vlm_table`'s version includes the model name (base vs
LoRA); `vlm_crop`'s includes the base model, the temperature and the tool name (`vlm_crop@s2` = sample 2 for E4).
Change a prompt or parsing rule → bump the version, or old answers will be replayed.

**Table tools and x labels.** A table tool only returns x values that have a label on the axis; an unlabelled x is
`x_not_found`. The planner uses `situation.x_on_tick` to avoid calling a table tool that would refuse.

**Same model, same mistakes.** `vlm_table` and `vlm_crop` share a model; the README measures that they agree on a wrong
value 10% of the time, so the planner never uses one as the other's cross-check. DePlot exists precisely because it is
a different model.

**Changing a tool invalidates calibration.** After a new adapter, prompt or model, re-run `calibrate`: the margins
were measured for the old tool. The same holds for new hardware (calibration tables were measured with float16 on
Apple silicon).

**Simulated tools are for plumbing only.** They read `truth.json` through `TruthIndex`. Their numbers must never appear
in a result table.

**Work by others in your area:** Vikash added `models/remote.py`, updated the adapter use for chart-to-table, wrote
`axis.py` / `chart_ocr.py` (used by `vlm_crop` for the crop and colour), and the current LoRA data and training scripts.

---

## Level 4 · Check yourself

1. Which tools use the LoRA adapter and which never do? Where is that enforced?
2. What happens when a tool throws `KeyError` inside `_read`?
3. Why is an `offline_miss` never written to the cache?
4. You change the `vlm_table` prompt. What must you bump, and what must be re-run?
5. Why does `vlm_crop` stitch the y-axis strip onto the crop?
6. How does the simulated noise model make the E4 correlation study meaningful?
7. Why can't Qwen3-VL-4B run on an 8 GB RAM laptop in float32, and what are the options?
8. A table tool returned `{"Resnet50": {"10": 0.9}}` and the claim asks for `ResNet-50` at epoch `10.0`. Walk through
   `lookup`.
