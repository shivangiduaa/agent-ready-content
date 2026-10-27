# Curation guidelines

How we choose the pages, passages, and claims for the Lost in the Chunk study. The aim is that anyone following this file would pick roughly the same content.

## Targets

| Set | Size | Used for |
| --- | --- | --- |
| Pages | 4 to 8 per vendor, ~100 total | Source pool for passages and claim sets |
| Passages | ~200, about 100 per category | Arm A, the controlled rewrite experiment |
| Claims | 5 to 10 checkable claims per vendor | Arm B, matching claims in live answers back to their source |

## Pipeline

```
discover.py  →  candidates.csv  →  you review  →  pages.csv
fetch.py     →  raw HTML snapshot + page manifest
segment.py   →  passages + features
sample.py     →  stratified sample of ~200 passages for Arm A
by hand      →  claims.jsonl and rewrites.jsonl
```

Everything you decide by hand gets written down in a CSV or JSONL file, so it can be audited later.

## 1. Which pages to include

Mark `include = yes` in `candidates.csv` for:

| Page type | Why | Notes |
| --- | --- | --- |
| `home` | The canonical product description | One per vendor |
| `product` | Product, platform, and feature pages, where most capability claims live | The core of the set |
| `integrations` | Named integrations are easy to check | Prefer an overview page over one page per integration |
| `security` | Certifications and standards (SOC 2, ISO 27001, HIPAA) are checkable | |
| `docs_intro` | The "what is X" or introduction page in the docs | Often the cleanest definitions |
| `comparison` | Vendor-owned "X vs Y" or alternatives pages | Both brands appear in one passage, which is exactly where misattribution happens |
| `pricing` | Plan limits are checkable | Tag as volatile; prices change between windows |

Leave out: blog posts, changelogs, careers, legal, events, customer stories, and anything behind a login. Blog posts are time-bound opinion, and customer stories mix in third-party claims. Both can come back in a later study.

## 2. What counts as a checkable claim

A claim is checkable if a reader could verify it as true or false from the vendor's own pages or docs.

| Checkable | Not checkable (exclude) |
| --- | --- |
| A number: SDK count, latency, uptime SLA, plan limits | Superlatives: "best-in-class," "fastest," "most powerful" |
| A named integration: "integrates with Datadog" | Vague breadth: "works with all your tools" |
| A named standard or certification: "SOC 2 Type II" | Feelings: "developers love it," "delightful" |
| A specific capability: "supports percentage rollouts by user attribute" | Outcomes without a mechanism: "ship faster with confidence" |
| A deployment fact: "self-hosted or cloud" | Unscoped comparisons: "better than the alternatives" |

When a sentence mixes both, keep only the checkable part as the claim.

## 3. What counts as a passage

A passage is one contiguous block from a single section of a page:

- 25 to 200 words
- Stays under one heading
- Contains at least one checkable claim about the vendor or its product

`segment.py` proposes passages automatically. When selecting for Arm A, drop any that fail these rules.

## 4. Selecting the ~200 for Arm A

`sample.py` samples to balance two properties the study cares about:

| | Entity named in the passage | Entity not named ("it," "we," "the platform") |
| --- | --- | --- |
| **Has a number or named standard** | ~50 | ~50 |
| **Capability only** | ~50 | ~50 |

It also caps any one vendor at 15 passages, so no single writing style dominates.

## 5. Writing the rewrites

Each selected passage gets one rewrite that applies the four content-side fixes from the outline:

1. Name the product in every sentence that makes a claim about it.
2. Replace references that point outside the passage ("it," "this," "the platform," "we") with what they refer to.
3. One checkable claim per sentence, keeping its number or named standard.
4. Use one distinctive term per concept, the same way the vendor uses it elsewhere.

Rules for the rewriter:

- **Add no new claims.** Every fact in the rewrite must be in the original passage or its page.
- **Keep the meaning and scope.** Don't strengthen, weaken, or generalize anything.
- **Stay within 20% of the original word count**, so length doesn't explain the results.
- **Get a second check.** Someone other than the rewriter confirms each rewrite adds and drops nothing.

### Example (fictional vendor)

Original, from a page titled "Lumen Flags Platform":

> It evaluates flags locally in under 5 ms, so there's no network call on the hot path. Our SDKs cover 14 languages, and we keep them in sync with the API.

Rewrite:

> Lumen Flags evaluates feature flags locally in under 5 ms, so Lumen Flags adds no network call on the hot path. Lumen Flags offers SDKs for 14 languages, kept in sync with the Lumen Flags API.

The rewrite resolves "It," "Our," and "we," names the product in every claim sentence, and adds nothing. A real rewrite should read a little less repetitively than this one; the example is deliberately heavy to show the changes.

## 6. Snapshots

Pages change. Re-run `fetch.py` at the start of each measurement window. The page manifest records a checksum of the extracted text, so we can tell which passages changed between windows and exclude or re-code them.
