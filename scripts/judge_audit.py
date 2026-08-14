#!/usr/bin/env python3
"""The cross-family judge audit: does the head-to-head survive an independent judge?

The head-to-head's judge shares a model family with nothing it scores, but the
main experiment's judge does, so a frontier judge from a different vendor
(claude-sonnet-5) re-judged the published responses of all five stores on a
frozen 100-question sample. This script recomputes the audit from its
per-question rows: per-arm scores under both judges, agreement, Cohen's kappa,
and the paired verdicts under the independent judge alone.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import load, by, mcnemar, table, check

ARMS = ("hybrid", "place_organized", "entity_time_cloud",
        "entity_time_oss", "entity_time_oss_bge")
PUBLISHED = {  # arm: (shipped, sonnet, agreement, kappa)
    "hybrid": (0.790, 0.750, 0.960, 0.887),
    "place_organized": (0.750, 0.680, 0.930, 0.829),
    "entity_time_cloud": (0.680, 0.620, 0.940, 0.869),
    "entity_time_oss": (0.560, 0.490, 0.930, 0.860),
    "entity_time_oss_bge": (0.610, 0.540, 0.910, 0.817),
}


def kappa(rows):
    po = sum(1 for r in rows if r["shipped_correct"] == r["sonnet_correct"]) / len(rows)
    p1 = sum(r["shipped_correct"] for r in rows) / len(rows)
    p2 = sum(r["sonnet_correct"] for r in rows) / len(rows)
    pe = p1 * p2 + (1 - p1) * (1 - p2)
    return (po - pe) / (1 - pe)


def main():
    rows = load("judge_audit", "sonnet_rows.json")
    arms = by(rows, "arm")
    ok = True

    print("== Cross-family judge audit, frozen 100-question sample per arm ==")
    out = []
    for a in ARMS:
        r = arms[a]
        sh = sum(x["shipped_correct"] for x in r) / len(r)
        so = sum(x["sonnet_correct"] for x in r) / len(r)
        ag = sum(1 for x in r if x["shipped_correct"] == x["sonnet_correct"]) / len(r)
        k = kappa(r)
        out.append([a, f"{sh:.3f}", f"{so:.3f}", f"{ag:.3f}", f"{k:.3f}"])
        for i, name in enumerate(("shipped", "sonnet", "agreement", "kappa")):
            ok &= check(f"{a} {name}", [sh, so, ag, k][i], PUBLISHED[a][i], tol=1e-3)
    table(["arm", "shipped judge", "sonnet judge", "agreement", "kappa"], out,
          ["<", ">", ">", ">", ">"])

    shifts = [sum(x["shipped_correct"] for x in arms[a]) / 100
              - sum(x["sonnet_correct"] for x in arms[a]) / 100 for a in ARMS]
    agrees = [sum(1 for x in arms[a]
                  if x["shipped_correct"] == x["sonnet_correct"]) / 100 for a in ARMS]
    print(f"\n  Level shift uniform: -{max(shifts):.2f} to -{min(shifts):.2f} "
          f"(sonnet grades stricter across the board)")
    print(f"  Agreement spread: {max(agrees) - min(agrees):.2f} "
          f"(within the pre-set 0.10 rule; note this bounds agreement only, and")
    print("   equal agreement can still conceal directionally different errors)")
    ok &= check("agreement spread", max(agrees) - min(agrees), 0.05, tol=1e-3)

    print("\n== Verdicts under the independent judge alone ==")
    for x in rows:
        x["correct"] = x["sonnet_correct"]
    aligned = {a: sorted(arms[a], key=lambda r: r["qa_id"]) for a in ARMS}
    bo, co, _, p = mcnemar(aligned["hybrid"], aligned["entity_time_cloud"])
    print(f"  hybrid vs entity-and-time cloud: rescued {bo} / lost {co}, p = {p:.3f}")
    ok &= check("hybrid-vs-cloud b", bo, 21, tol=0)
    ok &= check("hybrid-vs-cloud c", co, 8, tol=0)
    ok &= check("hybrid-vs-cloud p", p, 0.024, tol=5e-4)
    bo, co, _, p = mcnemar(aligned["hybrid"], aligned["place_organized"])
    print(f"  hybrid vs place-organized: rescued {bo} / lost {co}, p = {p:.3f} "
          "(the tie holds)")
    bo, co, _, p = mcnemar(aligned["hybrid"], aligned["entity_time_oss"])
    print(f"  hybrid vs graphiti oss: rescued {bo} / lost {co}, p = {p:.2e}")
    print("  The supported claim: on this frozen sample, every ranking from the shipped")
    print("  judge is preserved under the independent judge. The level shifts; the order")
    print("  does not.")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
