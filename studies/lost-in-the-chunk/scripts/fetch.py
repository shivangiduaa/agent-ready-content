"""Snapshot the pages marked include=yes in data/pages.csv.

Saves raw HTML locally (never committed) and appends one row per page to
data/pages_manifest.jsonl, which holds URLs and checksums but no page text.
Re-run at the start of each measurement window.

Usage:
    python scripts/fetch.py                       # snapshot dated today
    python scripts/fetch.py --snapshot 2027-01-05 # explicit date
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import sys
from pathlib import Path

from common import DATA_DIR, STUDY_DIR, PoliteClient, page_id, sha256_bytes, sha256_text
from extract import extract_sections

VALID_TYPES = {"home", "product", "integrations", "security", "docs_intro", "comparison", "pricing"}


def read_pages(path: Path) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("include", "").strip().lower() in {"yes", "y", "true", "1"}]
    bad = [r["url"] for r in rows if r["page_type"] not in VALID_TYPES]
    if bad:
        sys.exit(f"Set a valid page_type ({', '.join(sorted(VALID_TYPES))}) for: {bad}")
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pages", default=str(DATA_DIR / "pages.csv"))
    ap.add_argument("--snapshot", default=dt.date.today().isoformat())
    ap.add_argument("--manifest", default=str(DATA_DIR / "pages_manifest.jsonl"))
    args = ap.parse_args()

    rows = read_pages(Path(args.pages))
    print(f"{len(rows)} pages to fetch for snapshot {args.snapshot}")
    client = PoliteClient()
    ok = 0
    with open(args.manifest, "a", encoding="utf-8") as manifest:
        for row in rows:
            pid = page_id(row["vendor"], row["url"])
            record = {
                "page_id": pid, "vendor": row["vendor"], "url": row["url"], "page_type": row["page_type"],
                "volatile": row.get("volatile", "").strip().lower() == "yes", "snapshot": args.snapshot,
                "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
                "http_status": 0, "robots_allowed": None, "raw_path": None,
                "html_sha256": None, "text_sha256": None, "error": None,
            }
            try:
                resp, allowed = client.get(row["url"])
                record["robots_allowed"] = allowed
                if not allowed:
                    record["error"] = "disallowed by robots.txt"
                else:
                    record["http_status"] = resp.status_code
                    if resp.status_code == 200:
                        raw_path = DATA_DIR / "raw" / args.snapshot / row["vendor"] / f"{pid.split(':')[1]}.html"
                        raw_path.parent.mkdir(parents=True, exist_ok=True)
                        raw_path.write_bytes(resp.content)
                        text = "\n".join(p for s in extract_sections(resp.content) for p in s.paragraphs)
                        record.update(
                            raw_path=str(raw_path.relative_to(STUDY_DIR)),
                            html_sha256=sha256_bytes(resp.content),
                            text_sha256=sha256_text(text),
                        )
                        ok += 1
                    else:
                        record["error"] = f"HTTP {resp.status_code}"
            except Exception as exc:
                record["error"] = f"{type(exc).__name__}: {exc}"
            manifest.write(json.dumps(record) + "\n")
            status = "ok" if not record["error"] else record["error"]
            print(f"  {row['vendor']:<12} {status:<28} {row['url']}")
    print(f"Fetched {ok}/{len(rows)}. Manifest: {args.manifest}")


if __name__ == "__main__":
    main()
