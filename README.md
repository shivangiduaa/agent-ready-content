# agent-ready-content

Open tools and research on how AI agents and generative search engines retrieve, cite, and reuse content, and what content needs to change so it stays **retrievable** and **identifiable** to its source.

Agents don't read pages. They retrieve passages. A passage pulled out of its page can lose what identified it: the product name in the header, what "it" refers to, the scope set three paragraphs up. The fact survives into the answer, but the source doesn't. This repo measures that and tests content-side fixes.

## What's here

| Folder | What it holds | Status |
| --- | --- | --- |
| [`spec/`](spec/) | Best practices for agent-ready content, each tagged Tested, Observed, or Hypothesis | Being ported |
| [`studies/lost-in-the-chunk/`](studies/lost-in-the-chunk/) | First study: does agent retrieval separate content from its source, and can authors fix it? | Curating content |
| [`harness/`](harness/) | Runs prompt sets across engines, logs answers, citations, and model versions | Planned |
| [`skills/`](skills/) | Agent skills for writing and auditing content against the spec | Planned |

## Principles

- **Evidence labels on every rule.** A rule is Tested (controlled experiment), Observed (correlational), or Hypothesis. Rules move between labels as results come in.
- **Distributions, not snapshots.** AI answers are non-deterministic, so every metric is reported with an interval, per engine, with a date and model version.
- **Honest crawling.** Scripts identify themselves with a research user agent, respect robots.txt, and wait between requests.
- **No redistribution of third-party text.** Page text collected for studies stays local. The repo publishes URLs, checksums, passage offsets, and computed features, so anyone can rebuild the dataset from the source pages.

## License

Code is MIT licensed. See [LICENSE](LICENSE). Third-party page content is not included and remains the property of its owners.
