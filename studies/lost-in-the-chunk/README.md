# Lost in the Chunk

**Does agent retrieval separate content from its source, and can authors fix it?**

Agents retrieve passages, not pages. A passage pulled out of its page loses context the page supplied, like the product name in the title or what "it" and "we" refer to. When that passage shapes an AI answer, the fact can survive while the source's identity doesn't.

This study measures how often that happens and tests whether rewriting passages to be self-contained keeps them identifiable.

## Research questions

1. **Detachment.** How often does retrieved content shape an answer without being correctly attributed to its source?
2. **Passage properties.** Which properties of a passage (entity explicitness, self-containedness, claim specificity, distinctive terms) predict that it is retrieved, used, and still identifiable?
3. **Content-side fix.** Does rewriting passages to name the entity and resolve references raise identifiability without lowering retrieval?
4. **Memory vs retrieval.** Are claims an engine states from memory less identifiable than claims pulled from retrieved pages?

## Design

| Arm | What | Gives |
| --- | --- | --- |
| A | ~200 real passages, each in original and rewritten form, given to the models behind each engine in randomized sets | Cause, cheaply |
| B | 17 vendors, ~150 buyer questions, 3 engines, 4 windows two weeks apart | Real-world rates |
| C (optional) | Rewrite passages on pages the author controls, measure before and after | Live causal check |

**Categories:** feature flagging and workflow orchestration. See [`vendors.yaml`](vendors.yaml) for the vendors and exclusions.

## Status

- [x] Vendor list and curation rules ([`CURATION.md`](CURATION.md))
- [x] Data schemas ([`schemas/`](schemas/))
- [x] Pipeline: discover, fetch, segment, sample, tested on a fictional page
- [ ] Run discovery and review candidate pages
- [ ] First snapshot, segment, draw the Arm A sample
- [ ] Claim sets per vendor and passage rewrites
- [ ] Harness and Arm A runs

## Running the pipeline

Needs Python 3.10+.

```bash
cd studies/lost-in-the-chunk
python -m venv .venv && source .venv/bin/activate
pip install -r ../../requirements.txt

python scripts/discover.py          # writes data/candidates.csv
# review: set include=yes on the pages to keep, save as data/pages.csv
python scripts/fetch.py             # snapshots pages, appends to data/pages_manifest.jsonl
python scripts/segment.py --snapshot YYYY-MM-DD
python scripts/sample.py            # writes data/selected.csv for hand review

python -m unittest discover -s tests -v
```

Optionally set `ARC_UA_CONTACT` to a contact URL or email; it's appended to the crawler's user agent so site owners can reach you.

## Features computed per passage

| Feature | What it captures |
| --- | --- |
| `entity_mentions`, `entity_explicit` | Whether the passage names its own vendor or product |
| `entity_in_title` | Whether the page title or headings above name it. True here but false above is the detachment case |
| `first_person_refs` | "we," "our," "us": brand voice that loses its referent once chunked |
| `pronoun_refs`, `generic_refs` | "it," "they," sentence-initial "This," and "the platform": references that may point outside the passage |
| `unresolved_ref_rate` | All of the above per sentence |
| `has_number`, `has_named_standard` | Claim specificity; named standards like SOC 2 are not counted as numbers |
| `other_vendor_mentions` | Other study vendors in the same passage, where misattribution is most likely |

The reference counts are deliberately simple regex heuristics, so they're transparent and deterministic. A coreference model can replace them later; the tests pin down current behavior so any change is visible.
