#!/usr/bin/env python3
"""The agentic benchmarks: does a retrieved experience bank make an agent better at doing?

ALFWorld is scored as macro success rate (per-category mean). WebShop reports both the
partial-credit score (100 x mean reward) and the strict success rate.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import load, by, mcnemar, mcnemar_one_sided, table, check

PUBLISHED = {
    "alfworld_35b_baseline": 0.603, "alfworld_35b_memory": 0.645,
    "alfworld_frontier_baseline": 0.959, "alfworld_frontier_memory": 0.973,
    "webshop_35b_baseline": (63.5, 0.376), "webshop_35b_memory": (66.0, 0.418),
    "webshop_frontier_baseline": (65.1, 0.444), "webshop_frontier_memory": (65.2, 0.450),
}
BAR = {"alfworld": "MemHarness, published: 0.852 in-distribution, 0.859 out-of-distribution",
       "webshop": "MemHarness, published: 87.4 score / 0.756 success rate"}


def macro(rows):
    groups = by(rows, "category")
    return sum(sum(1 for r in g if r["won"]) / len(g) for g in groups.values()) / len(groups)


def main():
    ok = True
    print("== ALFWorld, 134 unseen games (Table 9) ==")
    alf = {a: load("agentic", f"alfworld_{a}.json") for a in
           ("35b_baseline", "35b_memory", "frontier_baseline", "frontier_memory")}
    for a in alf.values():
        a.sort(key=lambda r: r["game"])
    rows = []
    for a, r in alf.items():
        micro = sum(1 for x in r if x["won"]) / len(r)
        rows.append([a, len(r), f"{macro(r):.3f}", f"{micro:.3f}",
                     f"{sum(x['steps'] for x in r)/len(r):.1f}"])
    table(["column", "n", "macro SR", "micro SR", "avg steps"], rows, ["<", ">", ">", ">", ">"])
    print(f"  {BAR['alfworld']}")

    for a, r in alf.items():
        ok &= check(f"alfworld {a} macro", macro(r), PUBLISHED[f"alfworld_{a}"], tol=1e-3)

    print("\n== ALFWorld memory ablations, paired per game ==")
    for tier in ("35b", "frontier"):
        b, m = alf[f"{tier}_baseline"], alf[f"{tier}_memory"]
        for x, y in zip(b, m):
            x["correct"], y["correct"] = x["won"], y["won"]
        _, _, p1 = mcnemar_one_sided(m, b)
        bo, co, _, p2 = mcnemar(m, b)
        print(f"  {tier:9} memory rescued {bo}, cost {co}   one-sided p {p1:.3f}   two-sided p {p2:.3f}")

    print("\n== WebShop, 500 sessions (Table 10) ==")
    web = {a: load("agentic", f"webshop_{a}.json") for a in
           ("35b_baseline", "35b_memory", "frontier_baseline", "frontier_memory")}
    for a in web.values():
        a.sort(key=lambda r: r["idx"])
    rows = []
    for a, r in web.items():
        score = 100 * sum(x["reward"] for x in r) / len(r)
        sr = sum(1 for x in r if x["success"]) / len(r)
        rows.append([a, len(r), f"{score:.1f}", f"{sr:.3f}"])
        ps, psr = PUBLISHED[f"webshop_{a}"]
        ok &= check(f"webshop {a} score", score, ps, tol=0.05)
        ok &= check(f"webshop {a} success rate", sr, psr, tol=1e-3)
    table(["column", "n", "score", "success rate"], rows, ["<", ">", ">", ">"])
    print(f"  {BAR['webshop']}")

    print("\n== WebShop memory ablations, paired per session ==")
    for tier in ("35b", "frontier"):
        b, m = web[f"{tier}_baseline"], web[f"{tier}_memory"]
        for x, y in zip(b, m):
            x["correct"], y["correct"] = x["success"], y["success"]
        _, _, p1 = mcnemar_one_sided(m, b)
        bo, co, _, p2 = mcnemar(m, b)
        print(f"  {tier:9} memory rescued {bo}, cost {co}   one-sided p {p1:.3f}   two-sided p {p2:.3f}")
    print("\n== The store swap: the trained system's own bank on its own frozen actor (Table 12) ==")
    swap = {a: load("agentic", f"webshop_frozen7b_{a}.json") for a in
            ("baseline", "their_bank", "situation_match")}
    for a in swap.values():
        a.sort(key=lambda r: r["idx"])
    rows = []
    for a, r in swap.items():
        score = 100 * sum(x["reward"] for x in r) / len(r)
        sr = sum(1 for x in r if x["success"]) / len(r)
        rows.append([a, len(r), f"{score:.1f}", f"{sr:.3f}"])
    table(["arm", "n", "score", "success rate"], rows, ["<", ">", ">", ">"])
    PUB_SWAP = {"baseline": (71.0, 0.300), "their_bank": (69.5, 0.306),
                "situation_match": (69.1, 0.298)}
    for a, r in swap.items():
        score = 100 * sum(x["reward"] for x in r) / len(r)
        sr = sum(1 for x in r if x["success"]) / len(r)
        ok &= check(f"frozen7b {a} score", score, PUB_SWAP[a][0], tol=0.05)
        ok &= check(f"frozen7b {a} success rate", sr, PUB_SWAP[a][1], tol=1e-3)
    for x in swap["baseline"] + swap["their_bank"] + swap["situation_match"]:
        x["correct"] = x["success"]
    for a, b, pub in (("their_bank", "baseline", (14, 11)),
                      ("situation_match", "baseline", (14, 15)),
                      ("situation_match", "their_bank", (9, 13))):
        bo, co, _, p2 = mcnemar(swap[a], swap[b])
        print(f"  {a} vs {b}: rescued {bo} / cost {co}, two-sided p {p2:.3f}")
        ok &= check(f"swap {a}-vs-{b} discordant b", bo, pub[0], tol=0)
        ok &= check(f"swap {a}-vs-{b} discordant c", co, pub[1], tol=0)
    print("  Three-way statistical tie: at a frozen actor, neither the trained system's own")
    print("  released bank nor a different retrieval semantics over it moves the needle. The")
    print("  published margin is the training, not the bank content or retrieval mechanics.")

    print("\n  Convention note, because the campaign log is not uniform on this: the ablations were")
    print("  pre-registered one-sided (direction: memory helps), and ALFWorld's weak-actor p is quoted")
    print("  one-sided (0.164). The three others are quoted two-sided (0.022, 0.500, 0.801). Both")
    print("  columns are printed here so either convention can be read off directly; the verdicts")
    print("  do not change under either.")
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
