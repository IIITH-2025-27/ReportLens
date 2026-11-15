"""A larger model of the same family (run_log I4/I5): Qwen3-VL-8B in place of the 4B for vlm_table and vlm_crop.

    python scripts/analysis/q8b_eval.py --profile-only     # I4 screen; exit code 0 = GO, 3 = NO-GO
    python scripts/analysis/q8b_eval.py --out results/q8b.md

I4 compares the tool profiles that calibration wrote for v3 (calibration_tables/local) and for v3_q8b
(calibration_tables/local_q8b): the same charts and points, so the numbers line up row by row. I5 pools the six splits
of runs/v3 and runs/v3_q8b, as in section I2.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vlm2_eval as base  # noqa: E402

TOOLS = ["ocr_pixel", "deplot", "vlm_table", "vlm_crop"]
NAME = "_".join(TOOLS) + ".profile.json"
OLD_P = Path("calibration_tables/local") / NAME
NEW_P = Path("calibration_tables/local_q8b") / NAME
f = base.f


def screen(old: dict, new: dict) -> tuple[list[str], bool]:
    L = ["## I4: Qwen3-VL-8B against the 4B on the calibration charts", "",
         "| situation | tool | points | answers 4B / 8B | badly wrong 4B / 8B | median error 4B / 8B |", "|---|---|---|---|---|---|"]
    for sit in ("line|hard", "bar|hard", "line|easy", "bar|easy", "*"):
        for t in ("vlm_table", "vlm_crop"):
            a = (old["situations"].get(sit) or {}).get(t)
            b = (new["situations"].get(sit) or {}).get(t)
            if a and b:
                L.append(f"| {sit} | {t} | {b['n']} | {f(a['success'])} / {f(b['success'])} | {f(a.get('big_error'))} / "
                         f"{f(b.get('big_error'))} | {f(a.get('median_error'), 2)} / {f(b.get('median_error'), 2)} |")
    L += ["", "| situation | pair | agreements 4B / 8B | wrong when agreeing 4B / 8B | passes the gate 4B / 8B |",
          "|---|---|---|---|---|"]
    gate = lambda d: d and d["wrong_when_agree"] <= 0.05 and d["agree"] >= 20 and d.get("figures", 0) >= 5
    for sit in ("line|hard", "bar|hard"):
        keys = sorted(set(old["pairs"].get(sit, {})) | set(new["pairs"].get(sit, {})))
        for k in keys:
            if not any(t in k.split("~") for t in ("vlm_table", "vlm_crop")):
                continue
            a, b = old["pairs"].get(sit, {}).get(k), new["pairs"].get(sit, {}).get(k)
            L.append(f"| {sit} | {k} | {a and a['agree']} / {b and b['agree']} | {f(a and a['wrong_when_agree'])} / "
                     f"{f(b and b['wrong_when_agree'])} | {'yes' if gate(a) else 'no'} / {'yes' if gate(b) else 'no'} |")
    lh = new["situations"].get("line|hard") or {}
    crop, table = (lh.get("vlm_crop") or {}).get("big_error"), (lh.get("vlm_table") or {}).get("big_error")
    go = any(v is not None and v < 0.20 for v in (crop, table))
    L += ["", "Cost per call (seconds, measured, 8B): " + ", ".join(
        f"{t} {c.get('seconds_per_read', 0):.2f} per read, {c.get('seconds_per_figure', 0):.1f} per figure"
        for t, c in new.get("cost", {}).items() if t in ("vlm_table", "vlm_crop")), "",
          f"**Rule I4** (on line|hard, the 8B vlm_crop or vlm_table badly wrong on < 20% of answered points; 4B: 33.5% / "
          f"33.6%): vlm_crop {f(crop)}, vlm_table {f(table)}. **{'GO' if go else 'NO-GO'}**"]
    return L, go


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile-only", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    L, go = screen(json.loads(OLD_P.read_text()), json.loads(NEW_P.read_text()))
    if not args.profile_only and Path("runs/v3_q8b").exists():
        a_rows, _ = base.pooled(Path("runs/v3"), "v3")
        b_rows, b_split = base.pooled(Path("runs/v3_q8b"), "v3_q8b")
        a, b = base.counts(a_rows), base.counts(b_rows)
        unsafe = sum(m["run"].get("lms_unsafe_executed", 0) or 0 for _, m in b_split.values())
        L += ["", "## I5: six splits, v3 (4B) against v3 with the 8B", "", "| | v3 (4B) | v3 (8B) |", "|---|---|---|"]
        for k in ("claims", "coverage", "wrong_flags", "missed", "accuracy", "not_sure"):
            L.append(f"| {k} | {f(a[k]) if isinstance(a[k], float) else a[k]} | {f(b[k]) if isinstance(b[k], float) else b[k]} |")
        no_worse = b["coverage"] >= a["coverage"] and b["wrong_flags"] <= a["wrong_flags"] and b["missed"] <= a["missed"]
        better = b["coverage"] > a["coverage"] or b["wrong_flags"] < a["wrong_flags"] or b["missed"] < a["missed"]
        keep = no_worse and better and unsafe == 0
        L += ["", f"**Rule I5**: unsafe actions {unsafe}. **{'KEEP' if keep else 'NOT KEPT'}**"]
    text = "\n".join(L)
    print(text)
    if args.out:
        Path(args.out).write_text("# A larger model of the same family (run_log I4/I5)\n\n" + text + "\n")
    sys.exit(0 if go else 3)


if __name__ == "__main__":
    main()
