#!/usr/bin/env python3
"""LongMemEval-M: the long-haystack variant (~500-session histories).

Both store-only arms ran on the same pre-registered 100-question sample
(seed 20260812), one retrieval and one reader call each, judged with the
benchmark's official per-question-type prompts. That makes the comparison
paired, and it is the run that settles whether structure pays at long
histories.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import load, by, mcnemar, table, check


def main():
    place = load("longmemeval_m", "place_organized_sample100.json")
    hyb = load("longmemeval_m", "hybrid_storeonly_sample100.json")
    for r in place + hyb:
        r["correct"] = bool(r["official_judge"])
    place.sort(key=lambda r: r["question_id"])
    hyb.sort(key=lambda r: r["question_id"])
    assert [r["question_id"] for r in place] == [r["question_id"] for r in hyb], \
        "arms must pair on the same questions"

    print("== LongMemEval-M, pre-registered 100-question sample (seed 20260812) ==")
    sp = sum(r["correct"] for r in place) / len(place)
    sh = sum(r["correct"] for r in hyb) / len(hyb)
    print(f"  hybrid (store-only):                     {sh:.3f}  (n={len(hyb)})")
    print(f"  place-organized (MemPalace, store-only): {sp:.3f}  (n={len(place)})")
    ok = check("hybrid store-only fresh sample", sh, 0.750, tol=1e-3)
    ok &= check("place-organized fresh sample", sp, 0.600, tol=1e-3)

    bo, co, _, p = mcnemar(hyb, place)
    print(f"\n  Paired McNemar: hybrid rescued {bo}, lost {co}, exact two-sided p = {p:.5f}")
    ok &= check("paired discordant b", bo, 22, tol=0)
    ok &= check("paired discordant c", co, 7, tol=0)
    ok &= check("paired two-sided p", p, 0.00813, tol=5e-5)

    print("\n  Per category (hybrid / place-organized):")
    gh, gp = by(hyb, "category"), by(place, "category")
    table(["category", "n", "hybrid", "place"],
          [[c, len(v), f"{sum(r['correct'] for r in v)/len(v):.3f}",
            f"{sum(r['correct'] for r in gp[c])/len(gp[c]):.3f}"] for c, v in gh.items()],
          ["<", ">", ">", ">"])

    print("\n  Context, not reproducible from this repo:")
    print("   - hybrid agent-loop 0.632: over the complete 500 questions, a different harness")
    print("     and sample, so it is directional beside the paired rows above.")
    print("   - an earlier place-organized run scored 0.530 on a sample whose per-question rows")
    print("     were lost; both arms were re-drawn on this pre-registered sample as a result.")
    print("   - entity-and-time: not run. Ingest alone measures ~12 GPU-days, or ~$7,000 hosted.")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
