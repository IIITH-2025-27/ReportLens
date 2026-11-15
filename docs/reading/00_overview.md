# 00 · Overview (everyone reads this first)

## The problem in one paragraph

A student report says "ResNet-50 reaches 91.2% accuracy on CIFAR-10 (Figure 3)". Is that true according to the
student's **own** Figure 3? ReportLens reads the chart value with four different tools, measures how much the tools
disagree, turns that disagreement into an error margin using charts whose true values are known (calibration), and
only flags the sentence when the gap between the claim and the chart is clearly larger than the reading error.
Unclear cases go to the TA as NOT_SURE instead of becoming a wrong accusation.

**The language model never decides a verdict.** It may parse sentences and choose the next tool; the verdict comes from
a few lines of tested Python ([decide/rule.py](../../chart_claim_verifier/decide/rule.py)).

## The four verdicts

| Verdict | Meaning |
|---|---|
| CONSISTENT | gap ≤ rounding + accept margin, and the margin is narrow enough to mean something |
| MISMATCH | gap > rounding + flag margin, and it survives the batch check (Benjamini–Hochberg) |
| NOT_SURE | anything in between, too few readings, or readings too spread out |
| NO_FIGURE | no figure in the report shows this series / x value |

(`SKIPPED` marks sentences with a number that are not chart claims, e.g. "we trained for 50 epochs".)

## How the whole project works

The project has two halves. **Before deployment** we build data with known answers, measure how wrong each tool is
(calibration), optionally fine-tune one tool, and evaluate. **At deployment** a TA uploads a report and the frozen
system checks it using what was measured before. Nothing at deployment learns or changes.

```

━━━━━━━━━━━━━━━━━━━ BEFORE DEPLOYMENT  ·  done once, by us ━━━━━━━━━━━━━━━━━━━

┌────────────────────────────────────────────────────────────────────────────┐
│ ① GENERATE  synthetic reports with known answers                           │
├────────────────────────────────────────────────────────────────────────────┤
│ generator/  →  report.pdf + fig*.png + truth.json  for every split         │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼  calibration split
┌────────────────────────────────────────────────────────────────────────────┐
│ ② CALIBRATE  measure how wrong each tool is                                │
├────────────────────────────────────────────────────────────────────────────┤
│ every tool reads every point of charts with known values                   │
│ → calibration table (the margins)   → tool profile (planner's evidence)    │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼  optional
┌────────────────────────────────────────────────────────────────────────────┐
│ ③ FINE-TUNE  LoRA on Qwen3-VL for the vlm_table tool (E6)                  │
├────────────────────────────────────────────────────────────────────────────┤
│ changed tool → old margins invalid → run ② again                           │
│ result: better reading, not fewer wrong flags → base model kept            │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼  test / dev / holdout / final splits
┌────────────────────────────────────────────────────────────────────────────┐
│ ④ EVALUATE & FREEZE                                                        │
├────────────────────────────────────────────────────────────────────────────┤
│ run the agent on every split, compare with truth.json                      │
│ policies P0–P3, baselines B1–B5, safety  →  freeze the config              │
└────────────────────────────────────────────────────────────────────────────┘

━━━━━━━━━━━━━━━━━━ AT DEPLOYMENT  ·  every uploaded report ━━━━━━━━━━━━━━━━━━━

┌────────────────────────────────────────────────────────────────────────────┐
│ ⑤ CHECK A REPORT                                                           │
├────────────────────────────────────────────────────────────────────────────┤
│ TA uploads report.pdf (web, web_lite, or `check`)                          │
│ ingest → find claims → parse → find figure → measure → decide              │
│ → one verdict per sentence, with evidence, for the TA to review            │
│ uses (read-only): calibration table + tool profile from ②                  │
└────────────────────────────────────────────────────────────────────────────┘
```

### "Training", "calibration" and "fine-tuning": what each one is

| Word | Is it training? | What it actually is | Output |
|---|---|---|---|
| Calibration | **No** | Measuring how far each tool's readings are from the truth on charts with known values | `calibration_tables/<name>.json` + `.profile.json` |
| Tool profile | **No** | Statistics from the same calibration readings: success rate, error, cost, pair agreement per situation | `<name>.profile.json` |
| Fine-tuning | **Yes, of one tool only** | LoRA training of Qwen3-VL to turn a chart into a JSON table (`vlm_table`) | `checkpoints/lora_chart2table/` |
| The agent, the rule | **No** | Fixed code with thresholds from the config; nothing is learned | — |

So the verifier itself is not trained. The only trained component is the optional LoRA adapter, and the frozen system
kept the base model.

---

### ① Generate data with known answers (Harsh)

```bash
chart-claim-verifier generate -c configs/exp/local_real.yaml
```

```
┌────────────────────────────────────────────────────────────────────────────┐
│ 1  generator/tables.py                                                     │
├────────────────────────────────────────────────────────────────────────────┤
│ result tables like student ML results (accuracy, loss)                     │
│ half are 'hard': more series, more points                                  │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 2  generator/plot.py                                                       │
├────────────────────────────────────────────────────────────────────────────┤
│ draw bar / grouped bar / line in a random style                            │
│ record the real y-axis limits (the span)                                   │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 3  generator/claims.py                                                     │
├────────────────────────────────────────────────────────────────────────────┤
│ sentences with known labels: correct, rounded, hedged,                     │
│ planted errors (2/5/10/20/50% of span), wrong series/x,                    │
│ no-figure claims, setup sentences                                          │
│ labels use the checker's own tolerance rules                               │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 4  generator/injections.py                                                 │
├────────────────────────────────────────────────────────────────────────────┤
│ 15% of reports: hidden white tiny instruction                              │
│ + a clean twin without it (safety test)                                    │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 5  generator/report_builder.py                                             │
├────────────────────────────────────────────────────────────────────────────┤
│ write report.pdf + truth.json (true tables + gold labels)                  │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 6  generator/build.py                                                      │
├────────────────────────────────────────────────────────────────────────────┤
│ splits: calib, dev, test, holdout*, final, phrasing,                       │
│ style_shift, ft_pool  →  data/local/splits/<split>.txt                     │
└────────────────────────────────────────────────────────────────────────────┘
```

Only the generator and the simulated tools ever read `truth.json`.

### ② Calibrate the tools and build the tool profile (Vikash, Hritik)

```bash
chart-claim-verifier calibrate -c configs/exp/local_real.yaml      # needs the real models (GPU or model server)
chart-claim-verifier profile   -c configs/exp/local_real.yaml      # print the measured profile
```

```
┌────────────────────────────────────────────────────────────────────────────┐
│ calibration split                                                          │
├────────────────────────────────────────────────────────────────────────────┤
│ report.pdf + truth.json (true value of every chart point)                  │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ pipeline.ingest                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│ parse the PDF exactly as a real report would be parsed                     │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ calibration/collect.py                                                     │
├────────────────────────────────────────────────────────────────────────────┤
│ for EVERY (series, x) of EVERY figure, read with EVERY tool                │
│ → per-point error (fraction of span), failure code, seconds                │
│ → every reading saved in cache/local.sqlite                                │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼  the same readings feed two outputs
┌────────────────────────────────────────────────────────────────────────────┐
│ calibration/fit.py  →  calibration_tables/<tools>.json                     │
├────────────────────────────────────────────────────────────────────────────┤
│ ratio = |truth − median| / (disagreement + 0.5% of span)                   │
│ sorted per group: chart type × claim type × number of tools                │
│ used by the RULE: margin = ratio quantile × (disagreement + floor)         │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ evaluation/tool_profile.py  →  <tools>.profile.json                        │
├────────────────────────────────────────────────────────────────────────────┤
│ per tool × situation: answers?  typical error?  badly wrong?               │
│ per pair: how often do the two agree on a WRONG value?                     │
│ how far a failure reaches: whole figure / series / point                   │
│ used by the PLANNER to choose tools                                        │
└────────────────────────────────────────────────────────────────────────────┘
```

Claims are not needed here, only charts with true values.

### ③ Fine-tune the table tool (optional, E6; Karan, Vikash)

```bash
chart-claim-verifier generate -c configs/exp/ft_pool.yaml
python scripts/finetune/finetune_lora.py --pool ft_pool --out checkpoints/lora_chart2table --epochs 1
chart-claim-verifier calibrate -c configs/exp/local_lora.yaml
```

```
┌────────────────────────────────────────────────────────────────────────────┐
│ generate -c configs/exp/ft_pool.yaml                                       │
├────────────────────────────────────────────────────────────────────────────┤
│ separate charts; the held-out style is never used                          │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ training pairs                                                             │
├────────────────────────────────────────────────────────────────────────────┤
│ chart image → its true table as JSON (918 charts)                          │
│ in the exact prompt vlm_table uses                                         │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ scripts/finetune/finetune_lora.py                                          │
├────────────────────────────────────────────────────────────────────────────┤
│ LoRA rank 16, alpha 32, attention + MLP of the language model              │
│ loss on answer tokens only · 1 epoch · 114 steps · ~146 min                │
│ → checkpoints/lora_chart2table/                                            │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ configs/exp/local_lora.yaml                                                │
├────────────────────────────────────────────────────────────────────────────┤
│ models.lora_adapter = checkpoints/lora_chart2table                         │
│ only vlm_table uses the adapter; off for every other call                  │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼  tool changed → margins invalid
┌────────────────────────────────────────────────────────────────────────────┐
│ ② calibrate again  →  calibration_tables/local_lora/                       │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ result                                                                     │
├────────────────────────────────────────────────────────────────────────────┤
│ reading: answers 66 → 74%, badly wrong 26 → 17%                            │
│ system: wrong flags 3.5 → 4.2%  →  frozen system keeps the base model      │
└────────────────────────────────────────────────────────────────────────────┘
```

### ④ Evaluate and freeze (everyone)

```bash
chart-claim-verifier run       -c configs/exp/local_real.yaml --split test --policy informed
chart-claim-verifier sweep     -c configs/exp/local_real.yaml --run runs/local/<all_tools run>
chart-claim-verifier baselines -c configs/exp/local_real.yaml --run runs/local/<all_tools run>
chart-claim-verifier safety    -c configs/exp/local_real.yaml --run <injected run> --clean-run <clean twin run>
```

```
┌────────────────────────────────────────────────────────────────────────────┐
│ run  (every report of a split, exactly as ⑤ checks one)                    │
├────────────────────────────────────────────────────────────────────────────┤
│ --policy all_tools | fixed_order | informed | llm  (--offline: cache)      │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ evaluation/metrics.py  vs truth.json                                       │
├────────────────────────────────────────────────────────────────────────────┤
│ wrong-flag rate · coverage · catch rate by error size · attribution        │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ sweep · baselines · safety                                                 │
├────────────────────────────────────────────────────────────────────────────┤
│ sweep: re-decide P0 readings (coverage curve, B5)                          │
│ baselines: B1–B4 with the same VLM · safety: injected vs clean twins       │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼  design choices made on test / dev only
┌────────────────────────────────────────────────────────────────────────────┐
│ FREEZE the config  →  run the untouched final split once                   │
└────────────────────────────────────────────────────────────────────────────┘
```

### ⑤ A TA uploads a PDF: what happens, step by step

The web app ([web/](../../web/README.md)), the lite app ([web_lite/](../../web_lite/README.md)) and
`chart-claim-verifier check report.pdf` all build the agent with `pipeline.build_agent` and check the report with
`pipeline.verify_pdf`, so a TA runs exactly the system that was evaluated.

**In the web app**

```
┌────────────────────────────────────────────────────────────────────────────┐
│ 1  student uploads report.pdf to an assignment   [submitted]               │
├────────────────────────────────────────────────────────────────────────────┤
│ web_lite: the TA uploads it directly                                       │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 2  TA presses Verify   [verifying]                                         │
├────────────────────────────────────────────────────────────────────────────┤
│ backend queues a background job (one worker thread)                        │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 3  first job only: load the runtime                                        │
├────────────────────────────────────────────────────────────────────────────┤
│ config + calibration table + tool profile (from ②)                         │
│ tools + models (local, or model server at CCV_REMOTE_URL)                  │
│ pipeline.build_agent → the same agent `run` evaluated                      │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 4  pipeline.verify_pdf(report.pdf)                                         │
├────────────────────────────────────────────────────────────────────────────┤
│ stages V1–V10 below                                                        │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ 5  store and review   [verified]                                           │
├────────────────────────────────────────────────────────────────────────────┤
│ per sentence: verdict, reason, estimate, gap, margin, trace                │
│ TA confirms / dismisses findings → accept or request rework                │
│ students see only what the TA confirmed                                    │
└────────────────────────────────────────────────────────────────────────────┘
```

**Inside the verifier** (the running example is one sentence about Figure 2)

```
┌────────────────────────────────────────────────────────────────────────────┐
│ V1  READ THE PDF                          ingest/pdf_parser.py             │
├────────────────────────────────────────────────────────────────────────────┤
│ text → sentences (page-break cuts joined) · images → figures               │
│ caption = block under a figure starting 'Figure N'                         │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ V2  LOOK AT EACH FIGURE       pdf_parser · chart_type · tools/axis         │
├────────────────────────────────────────────────────────────────────────────┤
│ OCR legend, ticks, title once · bar / grouped bar / line · y span          │
│ e.g. Figure 2: line chart, legend 'ResNet-50, ViT-S', span 0–100           │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ V3  PLAN PER FIGURE               report_agent · situation                 │
├────────────────────────────────────────────────────────────────────────────┤
│ situation (line|easy …) + tool profile → tools worth using here            │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼  for every sentence
┌────────────────────────────────────────────────────────────────────────────┐
│ V4  FIND CLAIMS                               claims/finder.py             │
├────────────────────────────────────────────────────────────────────────────┤
│ number + result word → candidate · setup sentence → SKIPPED                │
│ e.g. 'ResNet-50 reaches 91.2% accuracy at epoch 10 (Figure 2).'            │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ V5  PARSE                              claims/parser · tolerance           │
├────────────────────────────────────────────────────────────────────────────┤
│ rule parser first; LLM parser only if rules fail                           │
│ → point claim · ResNet-50 · x = 10 · 91.2 · rounding ±0.05                 │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ V6  FIND THE FIGURE                   retrieval/figure_index.py            │
├────────────────────────────────────────────────────────────────────────────┤
│ 'Figure N' → BM25 on caption + chart text → series must appear             │
│ none → NO_FIGURE (stop) · two close → check both, never flag               │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ V7  MEASURE (claim loop)          controller · planner · tools             │
├────────────────────────────────────────────────────────────────────────────┤
│ planner picks the most trustworthy PAIR of tools → read → read             │
│ failure? remembered per figure, try another or hand off                    │
│ e.g. ocr_pixel 88.9 · deplot 89.1                                          │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ V8  COMBINE                              measure/aggregate.py              │
├────────────────────────────────────────────────────────────────────────────┤
│ estimate = median · disagreement = MAD  → 89.0 · 0.1                       │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ V9  DECIDE                ◄── calibration table   decide/rule.py           │
├────────────────────────────────────────────────────────────────────────────┤
│ margin = calibrated factor × (disagreement + 0.5% of span)                 │
│ gap > rounding + flag margin     → MISMATCH                                │
│ gap ≤ rounding + accept margin   → CONSISTENT (if margin narrow)           │
│ otherwise / too few readings     → NOT_SURE                                │
│ unclear and budget left → back to V7, read another tool                    │
│ e.g. gap 2.2 > flag margin → MISMATCH                                      │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼  all claims of the report
┌────────────────────────────────────────────────────────────────────────────┐
│ V10  BATCH CHECK                       finalize · decide/rule.py           │
├────────────────────────────────────────────────────────────────────────────┤
│ Benjamini–Hochberg over MISMATCH candidates; weak → NOT_SURE               │
└────────────────────────────────────────────────────────────────────────────┘
                                       │
                                       ▼
┌────────────────────────────────────────────────────────────────────────────┐
│ OUTPUT  one ClaimTrace per sentence                                        │
├────────────────────────────────────────────────────────────────────────────┤
│ verdict · reason · every tool reading · margins · stage log                │
│ evidence card for the TA · only action allowed: post a flag                │
└────────────────────────────────────────────────────────────────────────────┘
```

Changing a grade or emailing a student is blocked by the allow-list guard (`lms/guard.py`). In the evaluation runs the
guard handles every flag; the web app stores the results for the TA instead of posting anywhere.

## The data contract

Every module talks through the objects in [schemas.py](../../chart_claim_verifier/schemas.py). Read it now; it is 120
lines.

| Object | Made by | Used by |
|---|---|---|
| `Figure`, `Sentence`, `Report` | ingest | retrieval, agent, tools |
| `ClaimSpec` | parser | retrieval, controller, rule |
| `PointQuery`, `Reading` | controller / tools | controller, calibration |
| `Decision` | rule | trace, metrics |
| `ClaimTrace` | report agent | metrics, sweeps, baselines, web app |

Changing `schemas.py` changes everybody's code: agree on it first.

## Generated data on disk

```
data/local/generated/<split>/<report_id>/
├── report.pdf   the report the system reads
├── fig1.png …   chart images
└── truth.json   figures[].table (true values) + claims[] (gold labels)
data/local/splits/<split>.txt     report ids of a split
cache/local.sqlite                every tool reading ever made (replays need no model)
calibration_tables/local/         calibration table + tool profile
```

Only the generator and the simulated tools may read `truth.json`. Real tools see only the PDF.

## Run it once (laptop, simulated tools)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
chart-claim-verifier generate  -c configs/exp/smoke_cpu.yaml
chart-claim-verifier calibrate -c configs/exp/smoke_cpu.yaml
chart-claim-verifier run       -c configs/exp/smoke_cpu.yaml --split test --policy all_tools
chart-claim-verifier check     -c configs/exp/smoke_cpu.yaml data/smoke/generated/test/test_000
```

Simulated tools read the truth and add noise. They exist for plumbing; **never report their numbers**.

## Config

[configs/default.yaml](../../configs/default.yaml) holds every default with the reason next to it; files in
`configs/exp/` override it ([config.py](../../chart_claim_verifier/config.py) merges them). When you meet a number in
the code (`level_flag: 0.95`, `eps: 0.005`, `min_group_charts: 20`), the reason is in that file.

## Words used everywhere

| Word | Meaning |
|---|---|
| span | the y-axis range of a figure; errors are fractions of it |
| reading | one tool's value for one (series, x) |
| derived value | one tool's value for a claim (a point, a difference, a relative change) computed from its own readings |
| estimate / disagreement | median / median absolute deviation of the derived values |
| margin | calibrated multiple of the disagreement (plus a floor `eps × span`) |
| situation | `line|easy`, `line|hard`, `bar|easy`, `bar|hard`: what a chart looks like before measuring |
| tool profile | measured success, error, cost and pair agreement per tool and situation |
| hand-off | the agent stops and returns NOT_SURE for the TA |

Now open your own folder: `hritik/`, `vikash/`, `harsh/` or `karan/` (`reading.md` there).
