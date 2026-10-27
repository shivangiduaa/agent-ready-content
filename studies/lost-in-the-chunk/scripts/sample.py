"""Draw the stratified Arm A sample from data/passages.jsonl.

Strata: entity named or not, crossed with specific (number or named standard)
or capability only. Balanced across both categories, capped per vendor, and
seeded so the same input always gives the same sample. See CURATION.md section 4.

Writes data/selected.csv with an empty `keep` column. Check each passage by hand
against CURATION.md section 3 and mark keep=yes or keep=no with a reason.

Usage:
    python scripts/sample.py            # 200 passages
    python scripts/sample.py --n 120
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from collections import Counter, defaultdict

from common import DATA_DIR

SEED = 2026
VENDOR_CAP = 15
FIELDS = ["passage_id", "vendor", "category", "page_type", "stratum", "word_count", "keep", "reason"]


def stratum(p: dict) -> str:
    f = p["features"]
    named = "named" if f["entity_explicit"] else "unnamed"
    specific = "specific" if (f["has_number"] or f["has_named_standard"]) else "capability"
    return f"{named}_{specific}"


def select(passages: list[dict], n: int, vendor_cap: int = VENDOR_CAP, seed: int = SEED) -> tuple[list[dict], dict]:
    rng = random.Random(seed)
    categories = sorted({p["category"] for p in passages})
    strata = ["named_specific", "named_capability", "unnamed_specific", "unnamed_capability"]
    per_cell = n // (len(categories) * len(strata))

    cells: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for p in sorted(passages, key=lambda p: p["passage_id"]):
        cells[(p["category"], stratum(p))].append(p)

    chosen: list[dict] = []
    per_vendor: Counter = Counter()
    shortfall = {}
    for cat in categories:
        for st in strata:
            pool = cells[(cat, st)][:]
            rng.shuffle(pool)
            taken = 0
            for p in pool:
                if taken == per_cell:
                    break
                if per_vendor[p["vendor"]] >= vendor_cap:
                    continue
                chosen.append(p)
                per_vendor[p["vendor"]] += 1
                taken += 1
            if taken < per_cell:
                shortfall[f"{cat}/{st}"] = per_cell - taken
    return chosen, shortfall


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=200)
    args = ap.parse_args()

    with open(DATA_DIR / "passages.jsonl", encoding="utf-8") as f:
        passages = [json.loads(line) for line in f]
    chosen, shortfall = select(passages, args.n)

    with open(DATA_DIR / "selected.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for p in chosen:
            writer.writerow({"passage_id": p["passage_id"], "vendor": p["vendor"], "category": p["category"],
                             "page_type": p["page_type"], "stratum": stratum(p), "word_count": p["word_count"],
                             "keep": "", "reason": ""})
    counts = Counter(f"{p['category']}/{stratum(p)}" for p in chosen)
    print(f"Selected {len(chosen)} passages into data/selected.csv")
    for cell, c in sorted(counts.items()):
        print(f"  {cell:<45} {c}")
    if shortfall:
        print("Short cells (collect more pages of this kind):")
        for cell, missing in sorted(shortfall.items()):
            print(f"  {cell:<45} missing {missing}")


if __name__ == "__main__":
    main()
