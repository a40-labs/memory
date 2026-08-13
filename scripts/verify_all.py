#!/usr/bin/env python3
"""Run every verification script and report whether the published numbers reproduce."""
import subprocess, sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = ["longmemeval_s.py", "longmemeval_m.py", "locomo.py", "head_to_head.py", "agentic.py"]

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
    print("All published numbers reproduced from the per-question data.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
