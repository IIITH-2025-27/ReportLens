"""Tool interface (implementation.md §6.5).

Two kinds of tools:
  * point tools read one (series, x) value per call (vlm_crop, ocr_pixel)
  * table tools turn the whole figure into a table once; every later lookup on
    that figure is free (vlm_table, deplot)

Every tool returns a Reading and never raises: failures come back as
ok=False with a short error code, and the controller decides how to recover.
"""
from __future__ import annotations

import functools
import hashlib
import time
from abc import ABC, abstractmethod
from typing import Literal

import re

from rapidfuzz import fuzz, process

from ..models.vlm import OfflineMiss
from ..schemas import Figure, PointQuery, Reading
from .cache import ReadingCache

Table = dict[str, dict[str, float]]          # series -> x -> value


@functools.lru_cache(maxsize=4096)
def image_key(path: str) -> str:
    """Content hash of a figure image: the same chart gets the same cached readings
    wherever it was extracted to (e.g. a report and its clean twin)."""
    try:
        return hashlib.sha1(open(path, "rb").read()).hexdigest()
    except OSError:
        return path


class Tool(ABC):
    name: str = "tool"
    scope: Literal["point", "figure"] = "point"
    cost: float = 1.0                         # seconds per uncached call, measured on the pilot
    version: str = "v1"                       # bump when behaviour changes -> invalidates the cache
    kind: str = "neural"                      # "neural" | "classical" | "simulated"

    def __init__(self, cache: ReadingCache | None = None):
        self.cache = cache

    # -- what subclasses implement -------------------------------------------
    @abstractmethod
    def _read(self, fig: Figure, q: PointQuery) -> float:
        """Return the value or raise ToolError(code)."""

    def cache_key(self, fig: Figure, q: PointQuery) -> tuple:
        return (self.name, self.version, image_key(fig.image_path), q.series, q.x)

    # -- what callers use -------------------------------------------------------
    def read(self, fig: Figure, q: PointQuery) -> Reading:
        key = self.cache_key(fig, q)
        if self.cache is not None:
            hit = self.cache.get(key)
            if hit is not None:
                return Reading(**{**hit, "cached": True, "query": q})
        t0 = time.perf_counter()
        try:
            value, ok, err = float(self._read(fig, q)), True, None
        except ToolError as e:
            value, ok, err = None, False, e.code
        except OfflineMiss:                   # replay without the model: not a real failure, never cached
            return Reading(tool=self.name, value=None, ok=False, error="offline_miss",
                           latency_s=0.0, cached=False, query=q)
        except Exception as e:                # a tool bug must not crash the agent
            value, ok, err = None, False, f"exception:{type(e).__name__}"
        r = Reading(tool=self.name, value=value, ok=ok, error=err,
                    latency_s=time.perf_counter() - t0, cached=False, query=q)
        if self.cache is not None:
            self.cache.put(key, r.model_dump(exclude={"query", "cached"}))
        return r


class ToolError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class TableTool(Tool):
    """Extract the figure's table once (cached), then look values up by fuzzy name."""
    scope = "figure"

    def __init__(self, cache: ReadingCache | None = None):
        super().__init__(cache)
        self._tables: dict[str, Table | ToolError] = {}

    @abstractmethod
    def extract_table(self, fig: Figure) -> Table:
        ...

    def table(self, fig: Figure) -> Table:
        key = (self.name, self.version, image_key(fig.image_path), "__table__", "")
        if fig.image_path not in self._tables:
            hit = self.cache.get(key) if self.cache else None
            if hit is not None:
                self._tables[fig.image_path] = hit.get("table") or ToolError(hit.get("error", "no_table"))
            else:
                try:
                    tab = self.extract_table(fig)
                    if not tab:
                        raise ToolError("empty_table")
                    self._tables[fig.image_path] = tab
                    if self.cache:
                        self.cache.put(key, {"table": tab})
                except ToolError as e:
                    self._tables[fig.image_path] = e
                    if self.cache:
                        self.cache.put(key, {"table": None, "error": e.code})
        tab = self._tables[fig.image_path]
        if isinstance(tab, ToolError):
            raise tab
        return tab

    def has_table(self, fig: Figure) -> bool:
        return fig.image_path in self._tables

    def known_table(self, fig: Figure) -> Table | None:
        """The table if it was already read (in memory or in the reading cache), else None. Never calls the model:
        a cached point reading does not load the table into memory, so `has_table` alone misses it (v3, A3)."""
        tab = self._tables.get(fig.image_path)
        if tab is None and self.cache:
            hit = self.cache.get((self.name, self.version, image_key(fig.image_path), "__table__", ""))
            tab = hit.get("table") if hit else None
        return tab if isinstance(tab, dict) and tab else None

    def _read(self, fig: Figure, q: PointQuery) -> float:
        return lookup(self.table(fig), q.series, q.x)

    def read(self, fig: Figure, q: PointQuery) -> Reading:
        if STRICT_NAMES:                       # v4: never reuse a cached lookup that only loose matching allowed
            tab = self.known_table(fig)
            why = tab and lookup_veto(tab, q.series, q.x)
            if why:
                return Reading(tool=self.name, value=None, ok=False, error=why, cached=True, query=q)
        return super().read(fig, q)


def lookup_veto(table: Table, series: str, x: str) -> str | None:
    """Why strict matching refuses this (series, x) in a table that loose matching would read, or None."""
    why = strict_veto(series, list(table))
    if why or (len(table) == 1 and names_conflict(series, next(iter(table)))):
        return "series_" + (why or "name_conflict")
    s = match_name(series, list(table), strict=False) or (next(iter(table)) if len(table) == 1 else None)
    row = table.get(s) or {}
    if s is not None and x not in row and (w := strict_veto(x, list(row), 85)):
        return "x_" + w
    return None


# v4 (retrieval.strict_names): set from the config by pipeline.Context.tools(). Off = the frozen matching.
STRICT_NAMES = False
_SIZES = {"base", "large", "small", "tiny", "mini", "medium", "xl", "xxl", "huge", "nano", "micro", "lite", "big"}


def _norm_name(s: str) -> str:
    return "".join(ch for ch in s.lower() if ch.isalnum())


def names_conflict(a: str, b: str) -> bool:
    """Two members of one family, not two spellings of one name: "ResNet-18" / "ResNet-50", "CIFAR-100" /
    "CIFAR-10", "GPT-2" / "GPT-3", "BERT-base" / "BERT-large". token_set_ratio scores these 70-100, so the frozen
    matching read ResNet-50's line for a ResNet-18 claim, and every tool did the same, so they agreed."""
    da, db = re.findall(r"\d+", a), re.findall(r"\d+", b)
    # siblings share every letter and differ in a number; OCR garbles change letters too ("SST-2" read as "SS1-2",
    # "VGG-16" as "VGG-1i6"), so those are spelling noise, not another model (v4 replay: final_013, SST-2)
    if da and db and da != db and re.sub(r"[^a-z]", "", a.lower()) == re.sub(r"[^a-z]", "", b.lower()):
        return True
    sa = {w for w in re.findall(r"[a-z]+", a.lower()) if w in _SIZES}
    sb = {w for w in re.findall(r"[a-z]+", b.lower()) if w in _SIZES}
    return bool(sa and sb and sa != sb)


def strict_match(name: str, options: list[str], cutoff: float = 70) -> tuple[str | None, str | None]:
    """(match, None) or (None, why): no family conflicts, and a name that fits several members equally well
    ("ResNet" on a chart with ResNet-18 and ResNet-50) is ambiguous rather than a guess."""
    if not options:
        return None, "no_names"
    exact = [o for o in options if _norm_name(o) == _norm_name(name)]
    if exact:
        return exact[0], None
    scored = [(o, fuzz.token_set_ratio(name.lower(), o.lower())) for o in options]
    hits = sorted([(o, sc) for o, sc in scored if sc >= cutoff], key=lambda p: -p[1])
    if not hits:
        return None, "not_found"
    if names_conflict(name, hits[0][0]):
        return None, "name_conflict"
    rivals = [o for o, sc in hits[1:] if sc >= hits[0][1] - 5 and names_conflict(hits[0][0], o)]
    if rivals and not re.search(r"\d", name):
        return None, "ambiguous_name"
    return hits[0][0], None


def match_name(name: str, options: list[str], cutoff: float = 70, strict: bool | None = None) -> str | None:
    if not options:
        return None
    if STRICT_NAMES if strict is None else strict:
        return strict_match(name, options, cutoff)[0]
    hit = process.extractOne(name, options, scorer=fuzz.token_set_ratio, processor=str.lower)
    return hit[0] if hit and hit[1] >= cutoff else None


def strict_veto(name: str, options: list[str], cutoff: float = 70) -> str | None:
    """Why strict matching refuses a name the frozen matching would accept (None = no objection). Used to veto cached
    readings, so a reading taken with loose matching is never reused for a name it does not fit."""
    if not options:
        return None
    hit = process.extractOne(name, options, scorer=fuzz.token_set_ratio, processor=str.lower)
    if hit is None or hit[1] < cutoff:
        return None                                    # the frozen matching refuses too: nothing to veto
    _, why = strict_match(name, options, cutoff)
    return why


def lookup(table: Table, series: str, x: str) -> float:
    s = match_name(series, list(table))
    if s is None:
        if len(table) == 1 and not (STRICT_NAMES and names_conflict(series, next(iter(table)))):
            # single-series chart: the only series (v4: not when its name is another family member's)
            s = next(iter(table))
        else:
            raise ToolError("series_not_found")
    row = table[s]
    xx = x if x in row else match_name(x, list(row), cutoff=85)
    if xx is None:
        try:                                   # numeric x ("10" vs "10.0")
            xx = next(k for k in row if _float(k) is not None and _float(k) == _float(x))
        except StopIteration:
            raise ToolError("x_not_found") from None
    return float(row[xx])


def interpolate(table: Table, series: str, x: str) -> tuple[float, str, str] | None:
    """v5 (agent.interpolation_error): the series' value at an x the table has no row for, read off a straight line
    between the nearest x on either side. Table tools return only the x values that carry a tick label, so a claim
    at an unlabelled epoch ("epoch 7" on an axis labelled 1, 5, 9) gets no table reading at all.

    Numeric x only, never beyond the first or last labelled x, and the series is matched exactly as `lookup`
    matches it. Returns (value, left x, right x), or None."""
    s = match_name(series, list(table))
    if s is None:
        if len(table) != 1 or (STRICT_NAMES and names_conflict(series, next(iter(table)))):
            return None
        s = next(iter(table))
    xv = _float(x)
    pts = sorted((_float(k), k, v) for k, v in table[s].items() if _float(k) is not None)
    if xv is None or len(pts) < 2 or len({p[0] for p in pts}) != len(pts):
        return None
    left = [p for p in pts if p[0] < xv]
    right = [p for p in pts if p[0] > xv]
    if not left or not right:
        return None
    (x0, k0, y0), (x1, k1, y1) = left[-1], right[0]
    try:
        return float(y0) + (float(y1) - float(y0)) * (xv - x0) / (x1 - x0), k0, k1
    except (TypeError, ValueError):
        return None


def _float(s: str) -> float | None:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None
