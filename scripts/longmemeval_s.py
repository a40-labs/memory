#!/usr/bin/env python3
"""LongMemEval-S: the main experiment (no-memory / file-based / structured, plus the oracle control).

Recomputes every LongMemEval-S number the report publishes, from the per-question rows.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lib import load, rate, by, mcnemar, paired_bootstrap, post_stratified, table, check

PUBLISHED = {
    "structured": 0.7303, "file_based": 0.4410, "no_memory": 0.0983,
    "structured_ps": 0.7361, "file_based_ps": 0.4491, "diff_ps": 0.2869, "oracle_ps": 0.5706,
}
# the full LongMemEval-S category mix the holdout is re-weighted to
# The full LongMemEval-S category mix (all 500 questions), used to re-weight the
# holdout so its sample mix cannot flatter either arm. Counted from
# xiaowu0162/longmemeval-cleaned, longmemeval_s_cleaned.json.
MIX = {"temporal-reasoning": 127, "multi-session": 121, "knowledge-update": 72,
       "single-session-user": 64, "single-session-assistant": 56,
       "single-session-preference": 30, "abstention": 30}


def main():
    arms = {a: load("longmemeval_s", f"holdout_{a}.json")
            for a in ("no_memory", "file_based", "structured", "oracle")}
    for a in arms.values():
        a.sort(key=lambda r: r["question_id"])

    print("== Accuracy, held-out (356 non-tuning questions) ==")
    rows = []
    for name, r in arms.items():
        ps = post_stratified(r, MIX)
        rows.append([name, len(r), f"{rate(r):.4f}", f"{ps:.4f}"])
    table(["arm", "n", "raw", "post-stratified"], rows, ["<", ">", ">", ">"])

    ok = True
    print("\n== Cross-check against the published figures ==")
    for a in ("structured", "file_based", "no_memory"):
        ok &= check(f"{a} raw", rate(arms[a]), PUBLISHED[a])
    ok &= check("structured post-strat", post_stratified(arms["structured"], MIX), PUBLISHED["structured_ps"])
    ok &= check("file-based post-strat", post_stratified(arms["file_based"], MIX), PUBLISHED["file_based_ps"])

    d = post_stratified(arms["structured"], MIX) - post_stratified(arms["file_based"], MIX)
    ok &= check("oracle post-strat", post_stratified(arms["oracle"], MIX), PUBLISHED["oracle_ps"])
    ok &= check("paired difference (post-strat)", d, PUBLISHED["diff_ps"])

    print("\n== Per category (Table 1) ==")
    cs, cf = by(arms["structured"], "category"), by(arms["file_based"], "category")
    rows = [[c, len(cs[c]), f"{rate(cs[c]):.3f}", f"{rate(cf[c]):.3f}",
             "file-based" if rate(cf[c]) > rate(cs[c]) else ""] for c in sorted(cs)]
    table(["category", "n", "structured", "file-based", "winner"], rows, ["<", ">", ">", ">", "<"])

    print("\n== Gap split via the oracle control (descriptive, not causal) ==")
    f, o, s = (post_stratified(arms[a], MIX) for a in ("file_based", "oracle", "structured"))
    read, write = o - f, s - o
    print(f"  file-based {f:.4f} -> oracle {o:.4f} -> structured {s:.4f}")
    print(f"  aggregate read-side  {read:+.4f}  ({read/(s-f)*100:.0f}% of the gap)")
    print(f"  aggregate write-side {write:+.4f}  ({write/(s-f)*100:.0f}% of the gap)")
    for hi, lo, lab in ((arms["oracle"], arms["file_based"], "oracle vs file-based"),
                        (arms["structured"], arms["oracle"], "structured vs oracle")):
        a2 = sorted(hi, key=lambda r: r["question_id"])
        b2 = sorted(lo, key=lambda r: r["question_id"])
        bo2, co2, _, _ = mcnemar(a2, b2)
        print(f"  {lab}: rescued {bo2}, lost {co2}")
    print("  The interventions are non-monotonic per question (the oracle also changes how")
    print("  the context is presented), so this is an aggregate split between arms, not a")
    print("  per-question identification of where each point was lost.")

    print("\n== Paired test, structured vs file-based ==")
    bo, co, chi2, p = mcnemar(arms["structured"], arms["file_based"])
    lo, hi = paired_bootstrap(arms["structured"], arms["file_based"], n=2000)
    print(f"  discordant {bo}/{co}   chi2 {chi2:.2f}   exact p {p:.2e}")
    print(f"  unweighted paired difference CI95 [{lo:+.4f}, {hi:+.4f}] (2k resamples)")
    # The published CI is post-stratified: each resample is re-weighted to the
    # full category mix before differencing, matching the headline estimate.
    import random as _random
    rng = _random.Random(1234)
    st, fb = arms["structured"], arms["file_based"]
    n_rows = len(st)
    diffs = []
    for _ in range(10000):
        idx = [rng.randrange(n_rows) for _ in range(n_rows)]
        diffs.append(post_stratified([st[i] for i in idx], MIX)
                     - post_stratified([fb[i] for i in idx], MIX))
    diffs.sort()
    plo, phi = diffs[250], diffs[9750]
    print(f"  post-stratified paired difference CI95 [{plo:+.4f}, {phi:+.4f}]")
    print("  (published as [22.1, 35.1] points; bootstrap endpoints wobble ~0.1pt with")
    print("   seed and resampling detail)")
    ok &= check("post-strat CI low (pts)", plo * 100, 22.1, tol=0.2)
    ok &= check("post-strat CI high (pts)", phi * 100, 35.1, tol=0.2)

    print("\n== Token ledger, dev-144 (Table 2) ==")
    g = lambda r, k: r.get(k) or 0
    rows = []
    for a in ("file_based", "structured"):
        d = load("longmemeval_s", f"dev144_{a}.json")
        n = len(d)
        ans = sum(g(r, "answer_prompt_tokens") + g(r, "answer_completion_tokens") for r in d) / n
        ing = sum(g(r, "ingest_prompt_tokens") + g(r, "ingest_completion_tokens") for r in d) / n
        emb = sum(g(r, "ingest_embed_tokens") for r in d) / n
        ss = sum(g(r, "session_start_tokens") for r in d) / n
        acc = rate(d)
        rows.append([a, f"{ing:,.0f}", f"{ans+ss:,.0f}", f"{ing+ans+ss:,.0f}",
                     f"{(ing+ans+ss)/acc:,.0f}", f"{emb:,.0f}"])
    table(["arm", "write (ingest)", "answer", "total/question", "total/correct", "embedder"],
          rows, ["<", ">", ">", ">", ">", ">"])
    print("  note: the file-based ingest figure here is the results-row value; the report's 246.1k")
    print("  comes from the arm-separated ledger (the two arms shared a workdir on this run).")
    return ok


def sample100():
    """The head-to-head's LongMemEval-S column, official per-category rubric."""
    ok = True
    print("\n== Store-only LongMemEval-S, pre-drawn 100-question sample ==")
    g = load("longmemeval_s", "graphiti_oss_sample100.json")
    h = load("longmemeval_s", "hybrid_agentloop_sample100.json")
    sg = sum(bool(r["official_judge"]) for r in g) / len(g)
    sh = sum(bool(r["official_judge"]) for r in h) / len(h)
    ok &= check("graphiti oss store-only", sg, 0.350, tol=1e-3)
    ok &= check("hybrid agent-loop, same sample", sh, 0.720, tol=1e-3)
    print("  Rows that exist are published; two published scores have none, and why:")
    print("   - hybrid store-only 0.80 and place-organized 0.60: their runs never persisted")
    print("     per-question contexts (the arm was fixed forward after this was caught), and")
    print("     re-deriving contexts now would pair answers with retrievals that did not")
    print("     produce them. The scores stand in the post with this caveat attached.")
    return ok


if __name__ == "__main__":
    sys.exit(0 if (main() & sample100()) else 1)
