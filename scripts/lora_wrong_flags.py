"""E6 follow-up: why did the LoRA vlm_table raise P3's wrong flags? Compares the flags of two sets of P3 runs (saved traces).

    python scripts/lora_wrong_flags.py --base v3_test_informed v3_dev_informed ... --lora lora_test_informed ...

For each set: how many flags, which tools gave the readings behind each flag, and the same for the wrong ones.
No model is called.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from chart_claim_verifier.evaluation.metrics import join
from chart_claim_verifier.generator.build import load_truth
from chart_claim_verifier.pipeline import load_traces

SPLITS = ("test", "dev", "holdout", "holdout2", "holdout3")


def rows(run: str):
    d = Path(run) if "/" in run else Path("runs/local") / run
    ids = json.loads((d / "truths.json").read_text())
    truths = [load_truth(Path("data/local/generated") / r.rsplit("_", 1)[0] / r) for r in ids]
    return join(load_traces(d / "traces.jsonl"), truths)


def describe(name: str, runs: list[str]) -> list[str]:
    flags, wrong = Counter(), Counter()
    for run in runs:
        for r in rows(run):
            if r.verdict == "MISMATCH":
                key = "+".join(sorted(r.trace.tool_values))
                flags[key] += 1
                if r.gold != "error":
                    wrong[key] += 1
    same = lambda c: sum(v for k, v in c.items() if "vlm_table" in k and "vlm_crop" in k)
    return [f"| {name} | {sum(flags.values())} | {sum(wrong.values())} | {same(flags)} | {same(wrong)} | "
            f"{', '.join(f'{k} {v}' for k, v in wrong.most_common())} |"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", nargs="+", default=[f"v3_{s}_informed" for s in SPLITS[:4]] + ["u17old_holdout3_informed"])
    ap.add_argument("--lora", nargs="+", default=[f"lora_{s}_informed" for s in SPLITS])
    ap.add_argument("--extra", nargs="*", default=[], metavar="NAME=RUN,RUN,...")
    args = ap.parse_args()
    lines = ["| P3 runs | Flags | Wrong flags | Flags resting on both Qwen tools | Wrong among them | Tools behind the wrong flags |",
             "|---|---|---|---|---|---|"]
    lines += describe("base vlm_table", args.base) + describe("LoRA vlm_table", args.lora)
    for e in args.extra:
        name, runs = e.split("=")
        lines += describe(name, runs.split(","))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
