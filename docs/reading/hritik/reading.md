# Hritik · data contract, agent, tool profile, pipeline, CLI, integration tests

You own the parts that make everyone else's modules into **one agent**: the objects they exchange, the loop that
decides which tool to call, the measured profile that loop decides with, and the commands that run it all.

Read [00_overview.md](../00_overview.md) first. Poster questions for this area: [poster_qa.md](poster_qa.md).

---

## Level 0 · Background

| Idea | Why you need it | Read |
|---|---|---|
| pydantic models | `schemas.py` is pydantic: validation, `model_dump_json`, `model_validate_json` | pydantic docs, "Models" page |
| Agents as "LLM proposes, code decides" | the policy may only return `read` / `handoff` / `repair`, never a verdict | ReAct (Yao et al. 2022) for the loop; then notice how this project removes the verdict from the model |
| Sequential decision / stopping | the claim loop stops as soon as the rule is clear; P0 never stops early | any intro to optimal stopping; you only need the intuition "more readings cost time, stop when clear" |
| Correlated errors | two tools that share a model agree on the same wrong value; agreement is only evidence when mistakes are independent | README section "How the agent decides" |
| argparse sub-commands | `cli.py` | Python docs, `argparse` sub-commands |

---

## Level 1 · Read, in this order

1. **[schemas.py](../../../chart_claim_verifier/schemas.py)** — the contract. Note: `ClaimSpec.operands()` decides which
   chart points a claim needs (1 for a point, 2 for difference / relative change). `ClaimTrace` is the only output
   format; metrics, sweeps, baselines and the web app all read it.
2. **[config.py](../../../chart_claim_verifier/config.py)** and the `agent:` / `decision:` sections of
   [configs/default.yaml](../../../configs/default.yaml) — every threshold you will meet has its reason there.
3. **[agent/situation.py](../../../chart_claim_verifier/agent/situation.py)** — what a chart looks like *before*
   measuring: chart type, small image, number of series, value labels, readable axis. `hard` = small image, ≥ 4 series
   or unreadable axis. `key` = `line|hard`, `bar|easy`, … `x_on_tick` matters because table tools only return labelled
   x values.
4. **[agent/memory.py](../../../chart_claim_verifier/agent/memory.py)** — per-report memory: which tool failed on which
   figure/series with which code, and whether that failure reaches the whole figure, the series, or only the point
   (`blocked`, measured as `failure_scope` in the profile). `lift` undoes a block after a repair.
5. **[agent/policies.py](../../../chart_claim_verifier/agent/policies.py)** — P0 all tools, P1 fixed order, P1b
   calibration-informed, P2 LLM. Look at what a policy is allowed to return.
6. **[agent/controller.py](../../../chart_claim_verifier/agent/controller.py)** — the claim loop: ask the policy → read
   every operand with that tool → derived value → once `min_readings` values exist, `decide` → stop if clear (for
   policies with `stops_early`). Budget: `max_tool_calls`; a table tool costs one call per figure, later lookups are
   free.
7. **[evaluation/tool_profile.py](../../../chart_claim_verifier/evaluation/tool_profile.py)** — built from calibration
   errors: per tool × situation `success`, `median_error`, `p90_error`, `big_error`; per pair `agree` and wrong
   agreement; `failure_scope`; `repairs`. Every number carries how many **charts** it rests on.
8. **[agent/planner.py](../../../chart_claim_verifier/agent/planner.py)** — P3, the main method. `assess` → which tools
   would answer and which pairs can cross-check; `_first_read` → best trustworthy pair, read first the member most
   likely to fail per second; `_repair_or_handoff` → a measured repair that completes a pair, else hand off.
9. **[agent/report_agent.py](../../../chart_claim_verifier/agent/report_agent.py)** — one report end to end: plan per
   figure, find sentences, parse (rules first, LLM only on evidence), locate figure (one, two if ambiguous, or none),
   run the controller, log every stage. `finalize` = BH batch check + post flags through the guard.
   `ambiguous_accepts` = the rule for two candidate figures.
10. **[pipeline.py](../../../chart_claim_verifier/pipeline.py)** — `Context` (lazy LLM / remote server / cache),
    `ingest`, `calibrate`, `build_agent` (the one place an agent is assembled; `run`, `check` and the web backend all
    use it), `run_split`, `verify_pdf`.
11. **[cli.py](../../../chart_claim_verifier/cli.py)** — `generate`, `calibrate`, `run`, `sweep`, `check`, `safety`,
    `profile`, `baselines`. A thin layer over `pipeline.py`.

---

## Level 2 · Run

```bash
# plumbing with simulated tools
chart-claim-verifier generate  -c configs/exp/smoke_cpu.yaml
chart-claim-verifier calibrate -c configs/exp/smoke_cpu.yaml
chart-claim-verifier profile   -c configs/exp/smoke_cpu.yaml                     # read the profile you plan with
chart-claim-verifier run -c configs/exp/smoke_cpu.yaml --split test --policy fixed_order
chart-claim-verifier run -c configs/exp/smoke_cpu.yaml --split test --policy informed

# replay real readings from the cache, no model (if cache/local.sqlite has them)
chart-claim-verifier run -c configs/exp/local_real.yaml --split test --policy informed --offline --name replay_P3
python scripts/analysis/compare_runs.py runs/local/test_P0 runs/local/replay_P3 \
       --profile calibration_tables/local/<tools>.profile.json

pytest tests/test_planner.py tests/test_memory.py tests/test_repair.py tests/test_v2.py tests/test_end_to_end.py
```

Open one trace line in the run's JSONL and follow `stages` and `controller_steps`: every decision has a `why`.

---

## Level 3 · Full implementation

**State the policy sees.** `ClaimController._state` builds: available tools (minus blocked ones), readings so far,
failures, last decision, situation, measured cost per tool (`_seconds`: profile time, else the tool's `cost`), and
whether a table tool is already paid for on this figure. Anything a policy uses must be in this dict, which is also
why P2 (LLM) and P3 can be compared on the same evidence.

**Why pairs, not single tools.** The rule only accepts or flags when readings agree within a calibrated margin, so a
wrong verdict needs two tools that agree on the same wrong value. The planner therefore ranks *pairs* by measured
wrong-agreement (`pair_info`, `max_wrong_agree`, default 5% = half the 10% wrong-flag target). Tools that share a model
(`vlm_table`, `vlm_crop`) are never each other's cross-check (`shares_model`, `never_pair`).

**Evidence thresholds.** `Thresholds.from_cfg` reads `agent.informed`. A situation with < `min_points` points or
< `min_figures` charts falls back to pooled `*` numbers (points on one chart share mistakes). A pair needs
`min_pair_agreements` agreements before its wrong-agreement rate is trusted.

**Order inside a pair.** Read first the member most likely to fail per second of cost; a failure then shows up before
the expensive tool is paid for (`test_free_unreliable_tool_is_read_first_and_no_expensive_read_follows_its_failure`).

**Memory and failure reach.** A `series_not_found` from `ocr_pixel` blocks that tool for the series on that figure; a
`y_fit_failed` blocks it for the whole figure; `two_lines_at_x` blocks only the point. The reach is not hand-coded: it
is measured from calibration (`failure_scope`). A successful repair (`read_legend`) lifts the block and the tool is
read again (`tests/test_repair.py`).

**Ambiguous figures.** When the second candidate scores ≥ `retrieval.ambiguity_ratio` × the first, both are checked.
A claim is never flagged on an ambiguous figure; `agent.ambiguous_rule` (`both` by default) decides when it may be
accepted. `figure_runs` in the trace keeps what each figure said, so the rule can be compared offline
(`scripts/analysis/ambiguous_rules.py`).

**Parser escalation.** `parser="agent"`: rule parser first; the LLM parser only when no rule phrasing matched or the
parsed names appear in no figure. With `hand_off_rejected`, a sentence that looks like a claim but no parser accepts
goes to the TA instead of being dropped.

**Offline replay.** `Context(offline=True)` gives tools an `OfflineLLM`; a missing reading becomes
`error="offline_miss"`, is never cached, and is counted in `metrics.json` (`offline_misses`). This lets policies be
compared from one set of readings.

**Calibration order is fixed.** `pipeline.calibration_order` uses `agent.fixed_order` (or a seeded random subset),
never the run-time policy, so changing the policy cannot change the calibration table
(`test_calibration_order_does_not_follow_the_run_time_policy`).

**Your integration tests.** `test_end_to_end.py` (whole pipeline on generated data), `test_planner.py` (each planner
rule), `test_memory.py`, `test_repair.py`, `test_v2.py`, `test_final_fixes.py`, `test_offline.py`. A change to the
agent should come with a test named after the behaviour, like the existing ones.

**Work by others in your area:** `pipeline.py` has small edits by Vikash (remote model server).

---

## Level 4 · Check yourself

1. Which object would you change to add a new claim type, and which other modules would then have to change?
2. Why can a policy never return a verdict, and which test proves it?
3. What makes a situation `hard`, and why does `x_on_tick` matter for table tools?
4. Two tools agree. When is that *not* evidence that the reading is right?
5. A `y_fit_failed` from `ocr_pixel` on point 1 of a figure: what does the agent do on point 2 of the same figure?
6. Why are planner numbers that rest on 30 points from 2 charts replaced by pooled numbers?
7. What does `--offline` guarantee, and where do you see whether it held?
8. `run`, `check` and the web backend: where do they share code, and why does that matter for the evaluation?
