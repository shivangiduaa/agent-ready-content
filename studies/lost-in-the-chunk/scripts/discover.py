"""Find candidate pages for each vendor from robots.txt sitemaps and the homepage.

Writes data/candidates.csv with a guessed page type and an empty `include`
column. Review it by hand (see CURATION.md section 1), set include=yes on the
pages to keep, and save the result as data/pages.csv.

Usage:
    python scripts/discover.py                 # all vendors
    python scripts/discover.py --vendor flipt  # one vendor
"""

from __future__ import annotations

import argparse
import csv
import gzip
import sys
from urllib.parse import urljoin, urlsplit, urlunsplit

from lxml import etree

from common import DATA_DIR, PoliteClient, load_vendors

MAX_SITEMAPS_PER_HOST = 12
MAX_URLS_PER_VENDOR = 5000
MAX_CANDIDATES_PER_VENDOR = 60

EXCLUDE_SEGMENTS = {
    "blog", "changelog", "careers", "jobs", "legal", "privacy", "terms", "events", "event",
    "customers", "case-studies", "customer-stories", "news", "press", "webinars", "webinar",
    "podcast", "authors", "author", "tags", "tag", "category", "community", "newsletter",
    "releases", "release-notes", "api-reference", "reference", "login", "signup", "sign-up",
}
LOCALE_PREFIXES = {"de", "fr", "es", "ja", "ko", "zh", "pt", "pt-br", "it", "nl", "zh-cn", "zh-tw"}
DOCS_INTRO_WORDS = ("intro", "introduction", "overview", "what-is", "getting-started", "concepts")
TYPE_PRIORITY = ["home", "product", "docs_intro", "security", "integrations", "comparison", "pricing", "other"]


def normalize(url: str) -> str:
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, "", ""))


def classify(url: str, domain: str) -> str | None:
    """Guess the page type from the URL. None means exclude."""
    parts = urlsplit(url)
    host = parts.netloc.lower()
    segments = [s.lower() for s in parts.path.split("/") if s]
    if not (host == domain or host.endswith("." + domain)):
        return None
    if segments and segments[0] in LOCALE_PREFIXES:
        return None
    if any(s in EXCLUDE_SEGMENTS for s in segments):
        return None
    joined = "/".join(segments)
    is_docs = host.startswith("docs.") or (segments and segments[0] in {"docs", "documentation"})

    if is_docs:
        if len(segments) <= 1 and host.startswith("docs."):
            return "docs_intro"
        return "docs_intro" if any(w in joined for w in DOCS_INTRO_WORDS) else None
    if not segments:
        return "home"
    if segments[0] == "pricing":
        return "pricing"
    if segments[0] in {"security", "trust", "compliance", "trust-center"}:
        return "security"
    if segments[0] == "integrations":
        return "integrations" if len(segments) == 1 else None  # overview only
    if segments[0] in {"compare", "comparison", "vs", "alternatives"} or "-vs-" in joined or "alternative" in joined:
        return "comparison"
    if segments[0] in {"product", "products", "platform", "features", "feature", "solutions", "use-cases", "cloud"}:
        return "product"
    if len(segments) == 1:
        return "other"  # top-level marketing page; review by hand
    return None


def _parse_sitemap(content: bytes) -> tuple[list[str], list[str]]:
    """Return (child sitemap URLs, page URLs)."""
    if content[:2] == b"\x1f\x8b":
        content = gzip.decompress(content)
    try:
        root = etree.fromstring(content, parser=etree.XMLParser(recover=True, resolve_entities=False, no_network=True))
    except etree.XMLSyntaxError:
        return [], []
    if root is None:
        return [], []
    locs = [el.text.strip() for el in root.iter() if isinstance(el.tag, str) and el.tag.endswith("loc") and el.text]
    if root.tag.endswith("sitemapindex"):
        return locs, []
    return [], locs


def sitemap_urls(client: PoliteClient, host: str) -> list[str]:
    origin = f"https://{host}"
    parser = client.robots(origin + "/")
    queue = list(parser.site_maps() or []) if parser else []
    if not queue:
        queue = [origin + "/sitemap.xml"]
    seen, pages = set(), []
    while queue and len(seen) < MAX_SITEMAPS_PER_HOST and len(pages) < MAX_URLS_PER_VENDOR:
        sm = queue.pop(0)
        if sm in seen:
            continue
        seen.add(sm)
        try:
            resp, allowed = client.get(sm)
        except Exception as exc:
            print(f"  ! sitemap {sm}: {exc}", file=sys.stderr)
            continue
        if not allowed or resp is None or resp.status_code != 200:
            continue
        children, locs = _parse_sitemap(resp.content)
        queue.extend(children)
        pages.extend(locs)
    return pages


def homepage_links(client: PoliteClient, domain: str) -> list[str]:
    from bs4 import BeautifulSoup

    home = f"https://{domain}/"
    try:
        resp, allowed = client.get(home)
    except Exception as exc:
        print(f"  ! homepage {home}: {exc}", file=sys.stderr)
        return []
    if not allowed or resp is None or resp.status_code != 200:
        return []
    soup = BeautifulSoup(resp.content, "lxml")
    return [home] + [urljoin(home, a["href"]) for a in soup.find_all("a", href=True)]


def discover(vendor: dict, client: PoliteClient) -> list[dict]:
    domain = vendor["domain"]
    raw = sitemap_urls(client, domain) + sitemap_urls(client, f"docs.{domain}") + homepage_links(client, domain)
    found: dict[str, str] = {}
    for url in raw:
        url = normalize(url)
        ptype = classify(url, domain)
        if ptype and url not in found:
            found[url] = ptype
    ranked = sorted(found.items(), key=lambda kv: (TYPE_PRIORITY.index(kv[1]), len(kv[0])))
    return [
        {"vendor": vendor["id"], "category": vendor["category"], "url": url, "page_type": ptype,
         "volatile": "yes" if ptype == "pricing" else "", "include": "", "notes": ""}
        for url, ptype in ranked[:MAX_CANDIDATES_PER_VENDOR]
    ]


FIELDS = ["vendor", "category", "url", "page_type", "volatile", "include", "notes"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vendor", help="Only this vendor id")
    ap.add_argument("--out", default=str(DATA_DIR / "candidates.csv"))
    args = ap.parse_args()

    vendors = [v for v in load_vendors() if not args.vendor or v["id"] == args.vendor]
    if not vendors:
        sys.exit(f"No vendor with id {args.vendor!r}")
    client = PoliteClient()
    rows = []
    for v in vendors:
        print(f"{v['id']}: discovering on {v['domain']}")
        found = discover(v, client)
        print(f"  {len(found)} candidates")
        rows.extend(found)

    with open(args.out, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"Wrote {len(rows)} candidates to {args.out}. Review them, set include=yes, save as data/pages.csv.")


if __name__ == "__main__":
    main()
