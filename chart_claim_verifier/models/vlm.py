"""One shared model loader (implementation.md §14): load the VLM once, reuse it for
claim parsing, the controller, and tools 1–2.

Anything that needs a language model takes an object with this method:

    generate(prompt: str, images: Sequence[str | PIL.Image] = (), temperature=0.0,
             max_new_tokens=256, n=1) -> list[str]

`VLM` is the real (GPU) implementation; `ScriptedLLM` is a stand-in for tests.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, Protocol, Sequence


class LLM(Protocol):
    name: str

    def generate(self, prompt: str, images: Sequence = (), temperature: float = 0.0,
                 max_new_tokens: int = 256, n: int = 1, adapter: bool = False) -> list[str]: ...


def new_usage() -> dict:
    """What a model actually cost in one run (v3, A8): calls, tokens in and out, seconds, peak accelerator memory."""
    return {"calls": 0, "input_tokens": 0, "output_tokens": 0, "seconds": 0.0, "peak_memory_gb": 0.0}


def record_usage(usage: dict, n_in: int, n_out: int, seconds: float) -> None:
    usage["calls"] += 1
    usage["input_tokens"] += int(n_in)
    usage["output_tokens"] += int(n_out)
    usage["seconds"] = round(usage["seconds"] + seconds, 2)
    try:
        import torch
        if torch.cuda.is_available():
            peak = torch.cuda.max_memory_allocated() / 1e9
        elif torch.backends.mps.is_available():
            peak = torch.mps.driver_allocated_memory() / 1e9
        else:
            peak = 0.0
        usage["peak_memory_gb"] = round(max(usage["peak_memory_gb"], peak), 2)
    except Exception:                       # memory reporting must never break a run
        pass


def best_device() -> str:
    import torch
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


class VLM:
    """Qwen3-VL (default Qwen/Qwen3-VL-4B-Instruct) via transformers; also the second model family (models.vlm2,
    Granite Vision), which loads through the same Auto classes.

    fp16 on a T4 (CUDA) or on Apple silicon (MPS); fp32 on plain CPU unless bfloat16 is asked for.
    """

    def __init__(self, model_id: str, dtype: str = "float16", lora_adapter: str | None = None,
                 load_in_4bit: bool = False, device: str | None = None, max_pixels: int = 640 * 28 * 28):
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self.device = device or best_device()
        self.base_name = model_id               # the adapter is used only for the chart-to-table task (adapter=True)
        self.name = model_id + (f"+{lora_adapter}" if lora_adapter else "")
        self.has_adapter = bool(lora_adapter)
        # float16 is slow or unsupported on CPU, so it falls back to float32 there; bfloat16 is kept (half the
        # memory of float32, which is what lets the 4B model fit on a 16 GB CPU machine such as a free Space)
        torch_dtype = torch.float32 if self.device == "cpu" and dtype == "float16" else getattr(torch, dtype)
        kwargs = {"dtype": torch_dtype}
        if load_in_4bit and self.device == "cuda":
            from transformers import BitsAndBytesConfig
            kwargs["quantization_config"] = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_compute_dtype=torch_dtype)
            kwargs["device_map"] = "auto"
        elif self.device == "mps":
            # load straight into GPU memory: loading on the CPU and then moving needs two copies at once, which an
            # 8B model (17.5 GB) does not have room for on a 24 GB Mac (run_log I4)
            kwargs["device_map"] = "mps"
            # transformers 5 loads the weights with 4 threads; on MPS those threads deadlock inside PyTorch's Metal
            # shader cache (the web app's first run hung at ~400% CPU and 1.4 GB, 2026-11-14). Load them one at a time.
            os.environ.setdefault("HF_DEACTIVATE_ASYNC_LOAD", "1")
        # cap image size: charts do not need more than ~640 visual tokens (a Qwen processor option; others tile)
        extra = {"max_pixels": max_pixels} if "qwen" in model_id.lower() else {}
        repo, _, revision = model_id.partition("@")      # "repo@revision", e.g. Phi-4-multimodal's native-format branch
        if revision:
            extra["revision"] = kwargs["revision"] = revision
        self.processor = AutoProcessor.from_pretrained(repo, **extra)
        if not getattr(self.processor, "chat_template", None):
            # Phi-4-multimodal ships its template as chat_template.jinja, which this processor class does not pick up
            from huggingface_hub import hf_hub_download
            path = hf_hub_download(repo, "chat_template.jinja", revision=revision or None)
            self.processor.chat_template = open(path).read()
        if "phi-4-multimodal" in repo.lower():
            # run_log I6: a causal-LM class in transformers, and its image skills live in a bundled "vision" LoRA
            from transformers import AutoModelForCausalLM
            self.model = AutoModelForCausalLM.from_pretrained(repo, **kwargs)
            self.model.load_adapter(repo, adapter_name="vision", device_map=kwargs.get("device_map"),
                                    adapter_kwargs={"subfolder": "vision-lora", **({"revision": revision} if revision else {})})
            self.model.set_adapter("vision")
        else:
            self.model = AutoModelForImageTextToText.from_pretrained(repo, **kwargs)
        if "device_map" not in kwargs:
            self.model.to(self.device)
        if lora_adapter:
            from peft import PeftModel
            self.model = PeftModel.from_pretrained(self.model, lora_adapter)
        self.model.eval()
        self.usage = new_usage()

    def generate(self, prompt, images=(), temperature=0.0, max_new_tokens=256, n=1, adapter=False):
        import contextlib
        import time
        import torch
        from PIL import Image
        t0 = time.perf_counter()

        content = [{"type": "image", "image": Image.open(i).convert("RGB") if isinstance(i, str) else i}
                   for i in images]
        content.append({"type": "text", "text": prompt})
        inputs = self.processor.apply_chat_template(
            [{"role": "user", "content": content}], tokenize=True, add_generation_prompt=True,
            return_dict=True, return_tensors="pt").to(self.model.device)
        sample = temperature > 0
        gen = {"max_new_tokens": max_new_tokens, "do_sample": sample, "num_return_sequences": n}
        if sample:
            gen.update(temperature=temperature, top_p=0.95)
        else:
            gen.update(temperature=None, top_p=None, top_k=None)
        off = self.model.disable_adapter() if self.has_adapter and not adapter else contextlib.nullcontext()
        with torch.inference_mode(), off:
            out = self.model.generate(**inputs, **gen)
        out = out[:, inputs["input_ids"].shape[1]:]
        pad = self.processor.tokenizer.pad_token_id
        n_out = int((out != pad).sum()) if pad is not None else int(out.numel())
        record_usage(self.usage, inputs["input_ids"].shape[1] * out.shape[0], n_out, time.perf_counter() - t0)
        return self.processor.batch_decode(out, skip_special_tokens=True)


class LazyLLM:
    """A `VLM` that loads on its first call (run_log I0): a run whose readings all come from the reading cache loads
    no model, and two models need not sit in memory together. Same name, so the same cache keys as `VLM`."""

    def __init__(self, model_id: str, dtype: str = "float16", lora_adapter: str | None = None, factory=None):
        self.base_name = model_id
        self.name = model_id + (f"+{lora_adapter}" if lora_adapter else "")
        self.has_adapter = bool(lora_adapter)
        self._make = factory or (lambda: VLM(model_id, dtype, lora_adapter))
        self._vlm = None
        self.usage = new_usage()

    @property
    def loaded(self) -> bool:
        return self._vlm is not None

    def load(self) -> None:
        """Load now instead of on the first call (the web app does this at start-up)."""
        if self._vlm is None:
            self._vlm = self._make()
            self._vlm.usage = self.usage

    def generate(self, prompt, images=(), temperature=0.0, max_new_tokens=256, n=1, adapter=False):
        self.load()
        return self._vlm.generate(prompt, images, temperature=temperature, max_new_tokens=max_new_tokens, n=n,
                                  adapter=adapter)


class OfflineMiss(Exception):
    """A replay needed a model call that is not in the reading cache."""


class OfflineLLM:
    """Stand-in model for replays (`--offline`): answers nothing, so a missing reading is
    reported as `offline_miss` instead of silently loading the model."""

    def __init__(self, name: str, base_name: str | None = None):
        self.name, self.base_name = name, base_name or name

    def generate(self, *args, **kwargs):
        raise OfflineMiss("model call needed")


class ScriptedLLM:
    """Test double: answers come from a function of (prompt, images, call index)."""

    def __init__(self, respond: Callable[[str, Sequence, int], str], name: str = "scripted"):
        self.respond, self.name, self.calls = respond, name, 0

    def generate(self, prompt, images=(), temperature=0.0, max_new_tokens=256, n=1, adapter=False):
        out = []
        for _ in range(n):
            out.append(self.respond(prompt, images, self.calls))
            self.calls += 1
        return out


def extract_json(text: str):
    """First JSON object/array in a model answer (models like to add prose or ``` fences)."""
    text = re.sub(r"```(?:json)?", "", text)
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        while start != -1:
            depth = 0
            for i in range(start, len(text)):
                if text[i] == opener:
                    depth += 1
                elif text[i] == closer:
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[start:i + 1])
                        except json.JSONDecodeError:
                            break
            start = text.find(opener, start + 1)
    raise ValueError("no JSON found")
