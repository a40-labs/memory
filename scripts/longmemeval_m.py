#!/usr/bin/env python3
"""LongMemEval-M: the long-haystack variant (~500-session histories).

Only the place-organized store's fresh-sample row is reproducible from published data.
The hybrid's 0.632 is an agent-loop run over the complete 500 and is reported as a
historical aggregate; its store-only row on this sample was still running at publication.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import load, by, table, check

def main():
    rows = load("longmemeval_m", "place_organized_sample100.json")
    score = sum(1 for r in rows if r["official_judge"]) / len(rows)
    print("== LongMemEval-M, pre-registered 100-question sample (seed 20260812) ==")
    print(f"  place-organized (MemPalace, store-only): {score:.3f}  (n={len(rows)})")
    ok = check("place-organized fresh sample", score, 0.600, tol=1e-3)

    print("\n  Per category:")
    g = by(rows, "category")
    table(["category", "n", "score"],
          [[c, len(v), f"{sum(1 for r in v if r['official_judge'])/len(v):.3f}"] for c, v in g.items()],
          ["<", ">", ">"])

    print("\n  Not reproducible from this repo, and why:")
    print("   - hybrid 0.632: an agent-loop run over the complete 500 questions, a different")
    print("     harness and a different sample, so it is directional against the row above.")
    print("   - an earlier place-organized run scored 0.530 on a sample whose per-question rows")
    print("     were lost; both arms were re-drawn on this pre-registered sample as a result.")
    print("   - entity-and-time: not run. Ingest alone measures ~12 GPU-days, or ~$7,000 hosted.")
    return ok

if __name__ == "__main__":
    sys.exit(0 if main() else 1)
