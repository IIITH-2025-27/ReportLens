"""Tool 3: DePlot (Pix2Struct) chart-to-table; a different model from the VLM."""
from __future__ import annotations

import re

from ..schemas import Figure
from .base import Table, TableTool, ToolError


PROMPT = "Generate underlying data table of the figure below:"


def parse_linearized(text: str) -> Table:
    """Parse DePlot output: 'TITLE | t <0x0A> Epoch | A | B <0x0A> 1 | 0.5 | 0.6 ...'."""
    rows = [r.strip() for r in re.split(r"<0x0A>|\n", text) if r.strip()]
    rows = [r for r in rows if not r.upper().startswith("TITLE")]
    if len(rows) < 2:
        raise ToolError("empty_table")
    header = [c.strip() for c in rows[0].split("|")]
    series = header[1:] or ["value"]
    table: Table = {s: {} for s in series}
    for r in rows[1:]:
        cells = [c.strip() for c in r.split("|")]
        if len(cells) < 2:
            continue
        x = cells[0]
        for s, c in zip(series, cells[1:]):
            m = re.search(r"-?\d+(?:\.\d+)?", c.replace(",", ""))
            if m:
                table[s][x] = float(m.group())
    table = {s: row for s, row in table.items() if row}
    if not table:
        raise ToolError("empty_table")
    return table


class DePlotTool(TableTool):
    name = "deplot"
    cost = 1.5
    kind = "neural"
    version = "v1:google/deplot"

    def __init__(self, cache=None, model_id: str = "google/deplot", offline: bool = False, server=None):
        super().__init__(cache)
        self.model_id, self.offline, self.server = model_id, offline, server   # server: models.remote.ModelServer
        self._model = None

    def _load(self):
        if self._model is None:
            from transformers import Pix2StructForConditionalGeneration, Pix2StructProcessor

            from ..models.vlm import best_device
            self._proc = Pix2StructProcessor.from_pretrained(self.model_id)
            self._model = Pix2StructForConditionalGeneration.from_pretrained(self.model_id).to(best_device()).eval()
        return self._proc, self._model

    def linearize(self, image) -> str:
        """DePlot's raw answer for one chart image (path or PIL). The model server calls this too."""
        import torch
        from PIL import Image
        proc, model = self._load()
        im = Image.open(image) if isinstance(image, str) else image
        inputs = proc(images=im.convert("RGB"), text=PROMPT, return_tensors="pt").to(model.device)
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=512)
        return proc.decode(out[0], skip_special_tokens=True)

    def extract_table(self, fig: Figure) -> Table:
        if self.offline:
            from ..models.vlm import OfflineMiss
            raise OfflineMiss("deplot table not cached")
        if self.server is not None:
            from ..models.remote import encode_image
            text = self.server.run("deplot", {"image": encode_image(fig.image_path)})["text"]
        else:
            text = self.linearize(fig.image_path)
        return parse_linearized(text)
