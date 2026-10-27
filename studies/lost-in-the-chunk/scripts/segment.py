"""Split each fetched page in a snapshot into passages and compute their features.

Writes:
  data/passages.jsonl       full passages with text (local only, gitignored)
  data/passages_index.csv   the same rows without text (safe to commit)

Usage:
    python scripts/segment.py --snapshot 2027-01-05
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from common import DATA_DIR, STUDY_DIR, load_vendors, passage_id, sha256_text
from extract import count_entity, extract_sections, features, page_title, segment, word_count

INDEX_FIELDS = [
    "passage_id", "page_id", "vendor", "category", "page_type", "snapshot", "index", "page_title",
    "entity_in_title", "heading_path", "word_count", "text_sha256", "entity_mentions", "entity_explicit",
    "other_vendor_mentions",
    "first_person_refs", "pronoun_refs", "generic_refs", "unresolved_ref_rate", "has_number",
    "has_named_standard", "sentence_count",
]


def passages_for_page(html: bytes | str, page: dict, vendor: dict, all_vendors: list[dict]) -> list[dict]:
    rows = []
    title = page_title(html)
    for i, (heading_path, text) in enumerate(segment(extract_sections(html))):
        rows.append({
            "passage_id": passage_id(page["page_id"], i),
            "page_id": page["page_id"],
            "vendor": vendor["id"],
            "category": vendor["category"],
            "page_type": page["page_type"],
            "snapshot": page["snapshot"],
            "index": i,
            "page_title": title,
            # Entity named in the page title or headings above the passage: context a chunk can lose.
            "entity_in_title": count_entity(" ".join([title, *heading_path]), vendor) > 0,
            "heading_path": list(heading_path),
            "text": text,
            "word_count": word_count(text),
            "text_sha256": sha256_text(text),
            "features": features(text, vendor, all_vendors),
        })
    return rows


def index_row(p: dict) -> dict:
    row = {k: p[k] for k in INDEX_FIELDS if k in p}
    row["heading_path"] = " > ".join(p["heading_path"])
    row.update(p["features"])
    return row


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", required=True)
    ap.add_argument("--manifest", default=str(DATA_DIR / "pages_manifest.jsonl"))
    args = ap.parse_args()

    vendors = load_vendors()
    by_id = {v["id"]: v for v in vendors}
    pages = []
    with open(args.manifest, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec["snapshot"] == args.snapshot and rec.get("raw_path") and not rec.get("error"):
                pages.append(rec)
    # Keep the latest fetch per page if a snapshot was re-run.
    latest = {p["page_id"]: p for p in pages}

    all_rows = []
    for page in latest.values():
        html = (STUDY_DIR / page["raw_path"]).read_bytes()
        rows = passages_for_page(html, page, by_id[page["vendor"]], vendors)
        all_rows.extend(rows)
        print(f"  {page['vendor']:<12} {len(rows):>3} passages  {page['url']}")

    with open(DATA_DIR / "passages.jsonl", "w", encoding="utf-8") as f:
        for r in all_rows:
            f.write(json.dumps(r) + "\n")
    with open(DATA_DIR / "passages_index.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        writer.writerows(index_row(r) for r in all_rows)
    print(f"{len(all_rows)} passages from {len(latest)} pages.")


if __name__ == "__main__":
    main()
