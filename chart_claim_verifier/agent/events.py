"""A live feed of what the agent is doing, for the web app's activity panel.

The agent calls `emit(on_event, ...)` at each step: parsing a sentence, picking a figure, calling a tool, deciding.
`on_event` is None everywhere except in the web app, so experiments and the CLI are unaffected. The feed only
reports; nothing in it feeds back into a decision, and a failing listener never stops a run.

An event is a plain dict:
    stage     "run" | "plan" | "parse" | "figure" | "tool" | "repair" | "stop" | "decide"
    text      one line for the feed ("ocr_pixel on fig_2")
    why       the reason the agent logged, if any
    status    "start" (a call has begun), "ok", "error", or None
    sentence  the sentence being checked, if any
    tool      the tool's name, for tool and repair events
"""
from __future__ import annotations

from typing import Callable

Listener = Callable[[dict], None] | None


def emit(on_event: Listener, **event) -> None:
    if on_event is None:
        return
    try:
        on_event({k: v for k, v in event.items() if v is not None})
    except Exception:          # the feed is for watching; it must never break a run
        pass
