"""Do two runs give the same verdicts? The check behind every "0 verdicts change" rule (run_log.md, section H).

    python scripts/analysis/same_verdicts.py runs/v2/v2_test_informed runs/v3/v3_test_informed [--layer raw]

Claims are matched by (report, sentence id, atom); a claim present in only one run counts as a difference.
Exit code 1 when anything differs, so the check can be scripted.
"""
import argparse
import json
import sys
from pathlib import Path


def load(run: Path, layer: str) -> dict:
    name = "traces_raw.jsonl" if layer == "raw" else "traces.jsonl"
    out = {}
    for line in (run / name).read_text().splitlines():
        if line.strip():
            t = json.loads(line)
            out[(t["report_id"], t["sentence_id"], t.get("atom", 0))] = t
    return out


def compare(a: Path, b: Path, layer: str = "final") -> list[tuple]:
    ta, tb = load(a, layer), load(b, layer)
    diffs = []
    for k in sorted(set(ta) | set(tb)):
        va = ta[k]["decision"]["verdict"] if k in ta else "(missing)"
        vb = tb[k]["decision"]["verdict"] if k in tb else "(missing)"
        if va != vb:
            diffs.append((k, va, vb, (tb.get(k) or ta.get(k))["sentence"]))
    return diffs


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("a")
    ap.add_argument("b")
    ap.add_argument("--layer", default="final", choices=["final", "raw"])
    ap.add_argument("--show", type=int, default=20)
    args = ap.parse_args()
    diffs = compare(Path(args.a), Path(args.b), args.layer)
    n = len(load(Path(args.a), args.layer))
    print(f"{len(diffs)} of {n} verdicts differ ({Path(args.a).name} vs {Path(args.b).name})")
    for (rid, sid, atom), va, vb, sent in diffs[:args.show]:
        print(f"  {sid}#{atom}: {va} -> {vb}  | {sent[:100]}")
    return 1 if diffs else 0


if __name__ == "__main__":
    sys.exit(main())
