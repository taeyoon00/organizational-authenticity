"""
Run the Part 1 collection pipeline end to end.

Steps 2 and 3 can reject a snapshot (dead page, archived error page,
JavaScript shell); step 1 then picks the next-closest capture or the next
candidate URL. Steps 1-3 are therefore repeated until a round rejects
nothing new (at most MAX_ROUNDS), then step 4 (change) and 4c (gap report)
run once on the final text.
Every step caches its network results, so later rounds only fetch what
changed.
"""
import runpy
import sys
from pathlib import Path

from common import EXCLUSIONS_CSV, load_exclusions

HERE = Path(__file__).parent
MAX_ROUNDS = 6


def step(script):
    print(f"\n=== {script} ===", flush=True)
    runpy.run_path(str(HERE / script), run_name="__main__")


def main():
    for round_no in range(1, MAX_ROUNDS + 1):
        before = len(load_exclusions())
        print(f"\n##### round {round_no} ({before} rejected snapshots so far)")
        for script in ("01_find_snapshots.py", "02_download_snapshots.py", "03_extract_text.py"):
            step(script)
        if len(load_exclusions()) == before:
            break
    else:
        print(f"stopped after {MAX_ROUNDS} rounds; see {EXCLUSIONS_CSV.name}", file=sys.stderr)
    step("04_detect_change.py")
    step("04c_gap_report.py")


if __name__ == "__main__":
    main()
