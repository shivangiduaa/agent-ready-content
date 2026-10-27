# Data

Vendor page text belongs to the vendors, so it never goes in the repo. What's committed is enough for anyone to rebuild the dataset from the live pages and verify they got the same content.

| File | Contents | Committed |
| --- | --- | --- |
| `candidates.csv` | Pages found by `discover.py`, before review | Yes |
| `pages.csv` | Reviewed pages, `include=yes` on the ones in the study | Yes |
| `pages_manifest.jsonl` | One row per page per snapshot: URL, status, checksums | Yes |
| `raw/` | Raw HTML snapshots | **No** |
| `passages.jsonl` | Passages with full text and features | **No** |
| `passages_index.csv` | Same passages without text: IDs, headings, checksums, features | Yes |
| `selected.csv` | Arm A sample with hand-review decisions | Yes |
| `claims.jsonl` | Checkable claims per vendor, short statements | Yes |
| `rewrites.jsonl` | Rewritten passages | **No** (examples go in the paper) |

To verify a rebuild, compare `text_sha256` in `passages_index.csv` with your own run. A mismatch means the page changed since that snapshot.
