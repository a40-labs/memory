"""Shared loaders and statistics for the verification scripts.

Deliberately dependency-free: standard library only, so `python3 scripts/verify_all.py`
works on a clean checkout with no install step.
"""
import json
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")


def load(*parts):
    with open(os.path.join(DATA, *parts)) as f:
        return json.load(f)


def rate(rows, key="correct"):
    n = len(rows)
    return (sum(1 for r in rows if r[key]) / n) if n else 0.0


def by(rows, field):
    out = {}
    for r in rows:
        out.setdefault(r[field], []).append(r)
    return dict(sorted(out.items(), key=lambda kv: str(kv[0])))


PAIR_ID_FIELDS = ("qa_id", "question_id", "game", "idx", "session")


def assert_aligned(a, b):
    """Paired stats are only valid on identically ordered questions. If both
    row sets carry a recognised id field, require the sequences to match."""
    assert len(a) == len(b), "paired test needs equal-length, aligned rows"
    for f in PAIR_ID_FIELDS:
        if a and f in a[0] and f in b[0]:
            ids_a = [r[f] for r in a]
            ids_b = [r[f] for r in b]
            assert ids_a == ids_b, f"paired rows misaligned on {f}"
            return


def mcnemar(a, b, key="correct"):
    """Exact two-sided McNemar over paired rows, matched on position.

    Returns (b_only, c_only, chi2, p). b_only = a correct where b wrong.
    """
    assert_aligned(a, b)
    bo = sum(1 for x, y in zip(a, b) if x[key] and not y[key])
    co = sum(1 for x, y in zip(a, b) if y[key] and not x[key])
    n = bo + co
    chi2 = ((abs(bo - co) - 1) ** 2) / n if n else 0.0
    # exact binomial two-sided
    if n == 0:
        return bo, co, 0.0, 1.0
    k = min(bo, co)
    tail = sum(math.comb(n, i) for i in range(0, k + 1)) / (2 ** n)
    return bo, co, chi2, min(1.0, 2 * tail)


def mcnemar_one_sided(a, b, key="correct"):
    """One-sided exact McNemar: P(a beats b is this lopsided or more, by chance).

    The agentic memory ablations were pre-declared one-sided in the study log ("memory helps"),
    so this is the convention their p-values are quoted under.
    """
    bo, co, _, _ = mcnemar(a, b, key)
    n = bo + co
    if n == 0:
        return bo, co, 1.0
    p = sum(math.comb(n, i) for i in range(co + 1)) / (2 ** n)
    return bo, co, min(1.0, p)


def post_stratified(rows, weights, cat="category"):
    """Re-weight per-category rates to a reference category mix."""
    groups = by(rows, cat)
    total = sum(weights.values())
    return sum(weights[c] / total * rate(groups[c]) for c in weights if c in groups)


def paired_bootstrap(a, b, n=10000, seed=1234, key="correct"):
    """Percentile CI for the paired difference mean(a) - mean(b)."""
    assert_aligned(a, b)
    rng = random.Random(seed)
    idx = range(len(a))
    diffs = []
    for _ in range(n):
        s = [rng.randrange(len(a)) for _ in idx]
        da = sum(1 for i in s if a[i][key]) / len(s)
        db = sum(1 for i in s if b[i][key]) / len(s)
        diffs.append(da - db)
    diffs.sort()
    return diffs[int(0.025 * n)], diffs[int(0.975 * n)]


def paired_value_bootstrap(a, b, value, n=10000, seed=1234):
    """Percentile CI for the paired difference of a continuous per-row value
    (e.g. WebShop reward), resampling pairs."""
    assert_aligned(a, b)
    rng = random.Random(seed)
    d = [x[value] - y[value] for x, y in zip(a, b)]
    out = []
    for _ in range(n):
        s = [d[rng.randrange(len(d))] for _ in d]
        out.append(sum(s) / len(s))
    out.sort()
    return sum(d) / len(d), out[int(0.025 * n)], out[int(0.975 * n)]


def cluster_bootstrap(rows, cluster="conv_id", n=10000, seed=1234, key="correct"):
    """Percentile CI resampling whole clusters (LoCoMo's 10 conversations)."""
    rng = random.Random(seed)
    groups = list(by(rows, cluster).values())
    out = []
    for _ in range(n):
        pick = [groups[rng.randrange(len(groups))] for _ in groups]
        flat = [r for g in pick for r in g]
        out.append(rate(flat, key))
    out.sort()
    return out[int(0.025 * n)], out[int(0.975 * n)]


def cluster_paired_bootstrap(a, b, cluster="conv_id", n=10000, seed=1234, key="correct"):
    """Percentile CI for the paired difference mean(a) - mean(b), resampling
    whole clusters (LoCoMo's conversations) with pairs kept together."""
    assert_aligned(a, b)
    rng = random.Random(seed)
    convs = sorted({r[cluster] for r in a})
    by_c = {c: [(x, y) for x, y in zip(a, b) if x[cluster] == c] for c in convs}
    out = []
    for _ in range(n):
        pick = [convs[rng.randrange(len(convs))] for _ in convs]
        pairs = [p for c in pick for p in by_c[c]]
        out.append(sum(x[key] for x, _ in pairs) / len(pairs)
                   - sum(y[key] for _, y in pairs) / len(pairs))
    out.sort()
    return out[int(0.025 * n)], out[int(0.975 * n)]


def table(headers, rows, align=None):
    align = align or ["<"] * len(headers)
    widths = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    line = "  ".join(f"{h:{'>' if align[i] == '>' else '<'}{widths[i]}}" for i, h in enumerate(headers))
    print(line)
    print("  ".join("-" * w for w in widths))
    for r in rows:
        print("  ".join(f"{str(c):{'>' if align[i] == '>' else '<'}{widths[i]}}" for i, c in enumerate(r)))


def check(label, got, want, tol=5e-4):
    ok = abs(got - want) <= tol
    print(f"  [{'OK ' if ok else 'FAIL'}] {label}: computed {got:.4f}, published {want:.4f}")
    return ok
