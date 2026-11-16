"""Phi-4-multimodal as the second model family (run_log I6/I7), in the tool slots Granite used (vlm2_crop, vlm2_table).

    python scripts/analysis/phi_eval.py --profile-only     # I6 screen; exit code 0 = GO, 3 = NO-GO
    python scripts/analysis/phi_eval.py --out results/phi.md

I6 reads the tool profile from calibration_tables/local_phi (same charts and points as Granite's I1, so the tables line
up). I7 pools the six splits of runs/v3 and runs/v3_phi.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vlm2_eval as base  # noqa: E402

PROFILE = Path("calibration_tables/local_phi") / ("_".join(base.OLD + base.NEW) + ".profile.json")
QWEN = ("vlm_table", "vlm_crop")
f = base.f


def screen(p: dict) -> tuple[list[str], bool]:
    L, _ = base.profile_section(p)
    L = [l for l in L if not l.startswith("**Rule I1**")]
    L[0] = "## I6: Phi-4-multimodal on the calibration charts (live calls to Phi, the rest from the cache)"
    lh = (p["situations"].get("line|hard") or {}).get("vlm2_crop") or {}
    off = lh.get("success_off_tick")
    qwen_pairs = []
    for key, d in (p["pairs"].get("line|hard") or {}).items():
        a, b = key.split("~")
        if ({a, b} & set(base.NEW)) and ({a, b} & set(QWEN)):
            ok = d["wrong_when_agree"] <= 0.05 and d["agree"] >= 20 and d.get("figures", 0) >= 5
            qwen_pairs.append((key, d["wrong_when_agree"], d["agree"], ok))
    passed = any(ok for *_, ok in qwen_pairs)
    go = passed and off is not None and off >= 0.5
    L += ["", "Phi-Qwen pairs on line|hard: " + "; ".join(f"{k} {f(w)} of {n} agreements ({'passes' if ok else 'fails'})"
                                                        for k, w, n, ok in sorted(qwen_pairs)),
          "", f"**Rule I6** (on line|hard: vlm2_crop answers >= 50% at x without a tick label, and a Phi-Qwen pair passes "
          f"the gate): answers {f(off)}, a Phi-Qwen pair passes: {'yes' if passed else 'no'}. **{'GO' if go else 'NO-GO'}**"]
    return L, go


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile-only", action="store_true")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    L, go = screen(json.loads(PROFILE.read_text()))
    if not args.profile_only and Path("runs/v3_phi").exists():
        a_rows, _ = base.pooled(Path("runs/v3"), "v3")
        b_rows, b_split = base.pooled(Path("runs/v3_phi"), "v3_phi")
        a, b = base.counts(a_rows), base.counts(b_rows)
        unsafe = sum(m["run"].get("lms_unsafe_executed", 0) or 0 for _, m in b_split.values())
        L += ["", "## I7: six splits, v3 against v3 plus Phi-4-multimodal", "", "| | v3 | v3 + Phi |", "|---|---|---|"]
        for k in ("claims", "coverage", "wrong_flags", "missed", "accuracy", "not_sure"):
            L.append(f"| {k} | {f(a[k]) if isinstance(a[k], float) else a[k]} | {f(b[k]) if isinstance(b[k], float) else b[k]} |")
        L += ["", "| split | coverage v3 / Phi | wrong flags v3 / Phi | missed v3 / Phi |", "|---|---|---|---|"]
        _, a_split = base.pooled(Path("runs/v3"), "v3")
        for s in base.SPLITS:
            if s in a_split and s in b_split:
                ca, cb = base.counts(a_split[s][0]), base.counts(b_split[s][0])
                L.append(f"| {s} | {f(ca['coverage'])} / {f(cb['coverage'])} | {ca['wrong_flags']} / {cb['wrong_flags']} | "
                         f"{ca['missed']} / {cb['missed']} |")
        no_worse = b["coverage"] >= a["coverage"] and b["wrong_flags"] <= a["wrong_flags"] and b["missed"] <= a["missed"]
        better = b["coverage"] > a["coverage"] or b["wrong_flags"] < a["wrong_flags"] or b["missed"] < a["missed"]
        keep = no_worse and better and unsafe == 0
        L += ["", f"**Rule I7**: unsafe actions {unsafe}. **{'KEEP' if keep else 'NOT KEPT'}**"]
    text = "\n".join(L)
    print(text)
    if args.out:
        Path(args.out).write_text("# Phi-4-multimodal as the second model family (run_log I6/I7)\n\n" + text + "\n")
    sys.exit(0 if go else 3)


if __name__ == "__main__":
    main()
