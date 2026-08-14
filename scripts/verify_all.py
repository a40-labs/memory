#!/usr/bin/env python3
"""Run every verification script and report whether the published numbers reproduce."""
import subprocess, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = ["test_lib.py", "longmemeval_s.py", "longmemeval_m.py", "locomo.py", "head_to_head.py", "judge_audit.py", "agentic.py"]

def main():
    failed = []
    for s in SCRIPTS:
        print("\n" + "=" * 78)
        print(f"### {s}")
        print("=" * 78)
        r = subprocess.run([sys.executable, os.path.join(HERE, s)])
        if r.returncode != 0:
            failed.append(s)
    print("\n" + "=" * 78)
    if failed:
        print(f"FAILED: {', '.join(failed)}")
        return 1
    print("Every check passed: all published numbers THAT HAVE ROWS IN THIS REPO")
    print("reproduce from them. Published numbers with no rows here, and why:")
    print("  - LongMemEval-S store-only: hybrid 0.80, place-organized 0.60")
    print("      (contexts never persisted at run time; fixed forward)")
    print("  - LongMemEval-M agent-loop hybrid 0.632 (different harness, rows unpublished)")
    print("  - Graphiti under the local 35B extractor, 0.29 (study log only)")
    print("  - Zep Cloud's retrieved contexts (their data; measurements over it are here)")
    print("These carry their caveats wherever they appear.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
