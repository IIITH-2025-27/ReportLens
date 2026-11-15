"""C3 (run_log H20): calibrate the planner, not only the tools.

The frozen margins come from fixed tool subsets (the first k tools of every calibration point). But P3 stops as soon
as two readings agree, so the readings it decides on are a selected sample (why U14 failed, implementation.md
§24.5). Here P3 itself is run on every calibration point, offline from the cached readings, as a correct claim (the
claimed value is the truth), and the margins are fitted on the readings it had when it stopped. Difference claims are
added the same way, on the pairs `calibration.collect` uses.

    python scripts/analysis/c3_planner_calibration.py -c configs/exp/v2.yaml --out calibration_tables/c3_planner

Writes the table and a copy of the tool profile into --out; replay with a config whose calibration_dir is --out.
Rule written before the replay: keep only if margin coverage on P3 stays >= 95% on every split and pooled wrong
flags do not rise.
"""
import argparse
import json
import random
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from chart_claim_verifier.agent.memory import ReportMemory  # noqa: E402
from chart_claim_verifier.calibration.fit import CalibrationItem, fit_table  # noqa: E402
from chart_claim_verifier.config import load_config  # noqa: E402
from chart_claim_verifier.generator.build import report_dirs  # noqa: E402
from chart_claim_verifier.generator.tables import ChartTable  # noqa: E402
from chart_claim_verifier.measure.aggregate import derived_value  # noqa: E402
from chart_claim_verifier.pipeline import (Context, build_agent, calibration_splits, ingest,  # noqa: E402
                                           load_table)
from chart_claim_verifier.retrieval.figure_index import FigureIndex  # noqa: E402
from chart_claim_verifier.schemas import ClaimSpec  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-c", "--config", default="configs/exp/v2.yaml")
    ap.add_argument("--out", default="calibration_tables/c3_planner")
    args = ap.parse_args()
    cfg = load_config(args.config)
    ctx = Context(cfg, offline=True)
    table = load_table(ctx)
    agent, rc, _ = build_agent(ctx, table, "informed")
    rng = random.Random(cfg["seed"])
    items, stopped_k, misses = [], {}, 0
    for split in calibration_splits(cfg):
        for rd in report_dirs(ctx.data, split):
            report, truth = ingest(ctx, rd)
            mem = ReportMemory(report, FigureIndex(report.figures))
            agent.plan(mem)
            by_num = {f["number"]: f for f in truth["figures"]}
            for fig in report.figures:
                if fig.number not in by_num:
                    continue
                t = ChartTable.from_dict(by_num[fig.number]["table"])
                span = fig.y_span or t.span

                def run(claim, ctype, truth_value):
                    nonlocal misses
                    r = agent.controller.run(claim, fig, mem)
                    misses += sum(x.error == "offline_miss" for x in r.readings)
                    if len(r.tool_values) >= 2:
                        items.append(CalibrationItem(fig.chart_type, ctype, truth_value, dict(r.tool_values), span,
                                                     fig.image_path))
                        stopped_k[len(r.tool_values)] = stopped_k.get(len(r.tool_values), 0) + 1
                for s in t.series:
                    for x in t.x_values:
                        v = t.value(s, x)
                        run(ClaimSpec(claim_id="c", sentence=f"{s} {x}", claim_type="point", series=s, x=x,
                                      claimed_value=v), "point", v)
                names, xs = list(t.series), t.x_values
                for _ in range(max(1, len(names) * len(xs) // 2)):
                    if len(names) > 1:
                        x = rng.choice(xs)
                        a, b = rng.sample(names, 2)
                        ops = (a, x, b, x)
                    elif len(xs) > 1:
                        x1, x2 = rng.sample(xs, 2)
                        ops = (names[0], x1, names[0], x2)
                    else:
                        continue
                    d = derived_value("difference", [t.value(ops[0], ops[1]), t.value(ops[2], ops[3])])
                    run(ClaimSpec(claim_id="c", sentence="d", claim_type="difference", series=ops[0], x=ops[1],
                                  series_b=ops[2], x_b=ops[3], claimed_value=d, unit="pct_points"), "difference", d)
    d = cfg["decision"]
    new = fit_table(items, d["eps"], d["min_group_size"], order=None, seed=cfg["seed"],
                    min_group_charts=d.get("min_group_charts", 0),
                    meta={**table.meta, "calibrated_on": "P3 stopped readings (C3)"})
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    name = "_".join(cfg["tools"]["enabled"])
    new.save(out / f"{name}.json")
    src = Path(cfg["paths"]["calibration_dir"])
    shutil.copy(src / f"{name}.profile.json", out / f"{name}.profile.json")
    print(json.dumps({"items": len(items), "readings_at_stop": stopped_k, "offline_misses": misses,
                      "cutoff_95": {g: round(new.cutoff(*g.split("|")[:2], 2, 0.95)[1], 3)
                                    for g in ("bar|point", "line|point", "bar|difference", "line|difference")},
                      "old_cutoff_95": {g: round(table.cutoff(*g.split("|")[:2], 2, 0.95)[1], 3)
                                        for g in ("bar|point", "line|point", "bar|difference", "line|difference")}},
                     indent=1))


if __name__ == "__main__":
    main()
