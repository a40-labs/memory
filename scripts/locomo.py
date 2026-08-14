#!/usr/bin/env python3
"""LoCoMo: the second opinion, published under both scopes (with and without adversarial)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import load, rate, by, cluster_bootstrap, cluster_paired_bootstrap, table, check

PUBLISHED = {
    ("no_memory", "all"): 0.217, ("file_based", "all"): 0.387, ("structured", "all"): 0.497,
    ("no_memory", "excl"): 0.017, ("file_based", "excl"): 0.356, ("structured", "excl"): 0.561,
}
COST = {"file_based": (22.4, 58.0), "structured": (11.6, 23.3)}


def main():
    arms = {a: load("locomo", f"{a}.json") for a in ("no_memory", "file_based", "structured")}
    for r in arms.values():
        r.sort(key=lambda x: (x["conv_id"], x["qa_index"]))
    ok = True

    print("== Accuracy under both scopes (Table 4) ==")
    rows = []
    for a, r in arms.items():
        excl = [x for x in r if not x["adversarial"]]
        rows.append([a, len(r), f"{rate(r):.3f}", len(excl), f"{rate(excl):.3f}"])
    table(["arm", "n", "all", "n", "excl-adversarial"], rows, ["<", ">", ">", ">", ">"])

    print("\n== Cross-check against the published figures ==")
    for a, r in arms.items():
        ok &= check(f"{a}, all questions", rate(r), PUBLISHED[(a, "all")], tol=1e-3)
        ok &= check(f"{a}, excl-adversarial", rate([x for x in r if not x["adversarial"]]),
                    PUBLISHED[(a, "excl")], tol=1e-3)

    print("\n== Paired differences, structured minus file-based ==")
    for label, keep in (("all", lambda x: True), ("excl-adversarial", lambda x: not x["adversarial"])):
        s = [x for x in arms["structured"] if keep(x)]
        f = [x for x in arms["file_based"] if keep(x)]
        print(f"  {label:18} {rate(s) - rate(f):+.3f}")

    print("\n== Cluster bootstraps over the 10 conversations ==")
    key = lambda r: (r["conv_id"], str(r.get("qa_id") or r.get("question_id") or ""))
    st = sorted(arms["structured"], key=key)
    fb = sorted(arms["file_based"], key=key)
    lo_d, hi_d = cluster_paired_bootstrap(st, fb)
    print(f"  paired difference, all questions: CI95 [{lo_d:+.3f}, {hi_d:+.3f}]")
    ok &= check("diff CI all, low", lo_d, -0.007, tol=2e-3)
    ok &= check("diff CI all, high", hi_d, 0.240, tol=2e-3)
    st_x = [r for r in st if r["category"] != "Adversarial"]
    fb_x = [r for r in fb if r["category"] != "Adversarial"]
    lo_d, hi_d = cluster_paired_bootstrap(st_x, fb_x)
    print(f"  paired difference, excluding adversarial: CI95 [{lo_d:+.3f}, {hi_d:+.3f}]")
    ok &= check("diff CI excl-adv, low", lo_d, 0.063, tol=2e-3)
    ok &= check("diff CI excl-adv, high", hi_d, 0.356, tol=2e-3)
    lo, hi = cluster_bootstrap(arms["structured"], n=2000)
    print(f"  CI95 [{lo:.3f}, {hi:.3f}]  (questions cluster inside conversations, so"
          f" conversations are resampled, not questions)")

    print("\n== Per category (Figure 10) ==")
    cs, cf = by(arms["structured"], "category"), by(arms["file_based"], "category")
    rows = [[c, len(cs[c]), f"{rate(cs[c]):.3f}", f"{rate(cf[c]):.3f}",
             "file-based" if rate(cf[c]) > rate(cs[c]) else ""] for c in sorted(cs)]
    table(["category", "n", "structured", "file-based", "winner"], rows, ["<", ">", ">", ">", "<"])

    print("\n== Token ledger, ingest amortized per question (Table 5) ==")
    g = lambda r, k: r.get(k) or 0
    rows = []
    for a in ("file_based", "structured"):
        r = arms[a]
        n = len(r)
        ans = sum(g(x, "answer_prompt_tokens") + g(x, "answer_completion_tokens") for x in r) / n
        ing = {x["conv_id"]: g(x, "conv_ingest_prompt_tokens") + g(x, "conv_ingest_completion_tokens") for x in r}
        emb = {x["conv_id"]: g(x, "conv_ingest_embed_tokens") for x in r}
        ing_q, emb_q = sum(ing.values()) / n, sum(emb.values()) / n
        tot = ans + ing_q
        rows.append([a, f"{ing_q/1000:.1f}k", f"{ans/1000:.1f}k", f"{tot/1000:.1f}k",
                     f"{tot/rate(r)/1000:.0f}k", f"{emb_q/1000:.1f}k"])
        ok &= check(f"{a} total/question (k)", tot / 1000, COST[a][0], tol=0.1)
        ok &= check(f"{a} total/correct (k)", tot / rate(r) / 1000, COST[a][1], tol=0.6)
    table(["arm", "write", "answer", "total/question", "total/correct", "embedder"],
          rows, ["<", ">", ">", ">", ">", ">"])
    return ok


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
