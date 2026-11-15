"""A table tool on the second model family (run_log section I): Granite Vision's built-in chart-to-CSV task.

The model card's task tag `<chart2csv>` is expanded by its chat template into the full instruction; the answer is a
CSV table (sometimes in a ```csv fence, sometimes a markdown table). First column = x values, one column per series.
A table written the other way round (series as rows) is looked up transposed when the series is not a column.
"""
from __future__ import annotations

import csv
import re

from ..models.vlm import LLM
from ..schemas import Figure, PointQuery
from .base import Table, TableTool, ToolError, lookup

PROMPT = "<chart2csv>"
# models without Granite's task tag get the same request written out (run_log I6, Phi-4-multimodal)
PROMPT_PLAIN = ("Convert this chart into a CSV table. The first column holds the x-axis values, and there is one column "
                "per data series, headed by the series name exactly as in the legend. Give every value as a plain "
                "number. Answer only with the CSV.")


def _num(s: str) -> float | None:
    s = s.strip().strip('"').replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_csv_table(answer: str) -> Table:
    m = re.search(r"```[a-zA-Z]*\s*\n(.*?)(?:```|$)", answer, re.S)    # a cut-off answer has no closing fence
    lines = [ln for ln in (m.group(1) if m else answer).strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        raise ToolError("bad_csv")
    if all("|" in ln for ln in lines[:2]):                          # markdown table
        rows = [[c.strip() for c in ln.strip().strip("|").split("|")] for ln in lines
                if not re.fullmatch(r"[\s|:\-]+", ln)]
    else:
        rows = [[c.strip() for c in r] for r in csv.reader(lines)]
    header, body = rows[0], rows[1:]
    if len(header) < 2:
        raise ToolError("bad_csv")
    table: Table = {}
    for j, series in enumerate(header[1:], start=1):
        col = {r[0]: v for r in body if len(r) > j and r[0] and (v := _num(r[j])) is not None}
        if col and series:
            table[series] = col
    if not table:
        raise ToolError("empty_table")
    return table


def transpose(table: Table) -> Table:
    out: Table = {}
    for s, row in table.items():
        for x, v in row.items():
            out.setdefault(x, {})[s] = v
    return out


class Vlm2TableTool(TableTool):
    name = "vlm2_table"
    cost = 6.0
    kind = "neural"

    def __init__(self, llm: LLM, cache=None, max_new_tokens: int = 1024):
        super().__init__(cache)
        self.llm, self.max_new_tokens = llm, max_new_tokens
        self.prompt = PROMPT if "granite" in llm.name.lower() else PROMPT_PLAIN
        self.version = f"v1:{llm.name}:chart2csv" + ("" if self.prompt == PROMPT else ":plain")

    def extract_table(self, fig: Figure) -> Table:
        return parse_csv_table(self.llm.generate(self.prompt, [fig.image_path], max_new_tokens=self.max_new_tokens)[0])

    def _read(self, fig: Figure, q: PointQuery) -> float:
        tab = self.table(fig)
        try:
            return lookup(tab, q.series, q.x)
        except ToolError as e:
            if e.code != "series_not_found":
                raise
            return lookup(transpose(tab), q.series, q.x)
