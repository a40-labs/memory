#!/usr/bin/env python3
"""The store-only head-to-head: five retrieval stores, one reader, one judge, the same 1,540 questions."""
import sys, os, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import load, rate, mcnemar, table, check

STORES = ["hybrid", "place_organized", "entity_time_cloud", "entity_time_oss", "entity_time_oss_bge"]
LABEL = {"hybrid": "Hybrid", "place_organized": "Place-organized (MemPalace)",
         "entity_time_cloud": "Entity-and-time (Zep Cloud)", "entity_time_oss": "Entity-and-time (Graphiti OSS)",
         "entity_time_oss_bge": "Entity-and-time (Graphiti, bge-m3)", "hybrid_local35b": "Hybrid, local 35B reader"}
PUBLISHED = {"hybrid": 0.7825, "place_organized": 0.7792, "entity_time_cloud": 0.7461,
             "entity_time_oss": 0.5338, "entity_time_oss_bge": 0.5286, "hybrid_local35b": 0.7130}
CTX = {"hybrid": 4048, "place_organized": 3536, "entity_time_cloud": 21529,
       "entity_time_oss": 7857, "entity_time_oss_bge": 7896}


def main():
    data = {s: load("head_to_head", f"{s}.json") for s in STORES + ["hybrid_local35b"]}
    for d in data.values():
        d["rows"].sort(key=lambda r: r["qa_id"])
    ok = True

    print("== Accuracy and retrieval context (Tables 7 and 8) ==")
    rows = []
    for s in STORES:
        r = data[s]["rows"]
        med = statistics.median(x["context_chars"] for x in r)
        rows.append([LABEL[s], len(r), f"{rate(r):.4f}", f"{med:,.0f}"])
    table(["store", "n", "accuracy", "median context (chars)"], rows, ["<", ">", ">", ">"])

    print("\n== Cross-check against the published figures ==")
    for s in STORES + ["hybrid_local35b"]:
        r = data[s]["rows"]
        ok &= check(f"{LABEL[s]} accuracy", rate(r), PUBLISHED[s])
        # every bundle also carries the score its own run recorded
        ok &= check(f"{LABEL[s]} vs its manifest", rate(r), data[s]["manifest"]["headline"]["score"])
    for s in STORES:
        med = statistics.median(x["context_chars"] for x in data[s]["rows"])
        ok &= check(f"{LABEL[s]} median context", med, CTX[s], tol=1)

    print("\n== Paired McNemar, every pair on the same 1,540 questions ==")
    rows = []
    for i, a in enumerate(STORES):
        for b in STORES[i + 1:]:
            bo, co, chi2, p = mcnemar(data[a]["rows"], data[b]["rows"])
            verdict = "significant" if p < 0.05 else "not significant"
            rows.append([f"{LABEL[a]} vs {LABEL[b]}", f"{bo}/{co}", f"{chi2:.2f}", f"{p:.2e}", verdict])
    table(["pair", "discordant", "chi2", "p", "verdict"], rows, ["<", ">", ">", ">", "<"])

    print("\n== The reader, measured against the architectural differences ==")
    a, b = data["hybrid"]["rows"], data["hybrid_local35b"]["rows"]
    swing = (rate(a) - rate(b)) * 100
    print(f"  identical retrieval, frontier reader {rate(a):.4f} vs local 35B reader {rate(b):.4f}"
          f"  ({swing:+.1f} points)")
    diffs = sorted(((abs(rate(data[x]["rows"]) - rate(data[y]["rows"])) * 100, x, y)
                    for i, x in enumerate(STORES) for y in STORES[i + 1:]), reverse=True)
    smaller = [d for d in diffs if d[0] < swing]
    print(f"  that swing is larger than {len(smaller)} of the {len(diffs)} store-vs-store differences:")
    for d, x, y in reversed(smaller):
        print(f"     {d:5.1f}  {LABEL[x]} vs {LABEL[y]}")
    print(f"  and smaller than the {len(diffs)-len(smaller)} that involve the starved open engine "
          f"({min(d for d, _, _ in diffs if d > swing):.1f} to {max(d for d, _, _ in diffs):.1f} points).")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
