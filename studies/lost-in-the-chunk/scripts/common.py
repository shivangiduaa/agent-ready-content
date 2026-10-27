"""Shared helpers: paths, vendor config, IDs, checksums, and a polite HTTP client."""

from __future__ import annotations

import hashlib
import os
import time
import urllib.robotparser
from pathlib import Path
from urllib.parse import urlsplit

import yaml

STUDY_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = STUDY_DIR / "data"
VENDORS_PATH = STUDY_DIR / "vendors.yaml"

USER_AGENT = "agent-ready-content-research/0.1 (academic research crawler; respects robots.txt)"
if os.environ.get("ARC_UA_CONTACT"):
    USER_AGENT += f" contact: {os.environ['ARC_UA_CONTACT']}"

MIN_DELAY_SECONDS = 1.0
TIMEOUT_SECONDS = 20


def load_vendors(path: Path = VENDORS_PATH) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    vendors = config["vendors"]
    ids = [v["id"] for v in vendors]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate vendor id in vendors.yaml")
    return vendors


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def page_id(vendor: str, url: str) -> str:
    return f"{vendor}:{hashlib.sha1(url.encode('utf-8')).hexdigest()[:12]}"


def passage_id(pid: str, index: int) -> str:
    return f"{pid}:p{index:03d}"


class PoliteClient:
    """HTTP client that identifies itself, obeys robots.txt, and waits between requests to a host."""

    def __init__(self, user_agent: str = USER_AGENT, min_delay: float = MIN_DELAY_SECONDS):
        import requests  # imported here so offline modules don't need it

        self.session = requests.Session()
        self.session.headers["User-Agent"] = user_agent
        self.user_agent = user_agent
        self.min_delay = min_delay
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._last_hit: dict[str, float] = {}

    def _wait(self, host: str, crawl_delay: float | None = None) -> None:
        delay = max(self.min_delay, crawl_delay or 0)
        last = self._last_hit.get(host)
        if last is not None:
            remaining = delay - (time.monotonic() - last)
            if remaining > 0:
                time.sleep(remaining)
        self._last_hit[host] = time.monotonic()

    def robots(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        """Return the parser for the URL's host. None means robots.txt could not be read safely."""
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        parser = urllib.robotparser.RobotFileParser()
        self._wait(parts.netloc)
        try:
            resp = self.session.get(f"{origin}/robots.txt", timeout=TIMEOUT_SECONDS)
        except Exception:
            self._robots[origin] = None  # unreachable: treat as disallowed
            return None
        if resp.status_code in (401, 403):
            parser.disallow_all = True
        elif 400 <= resp.status_code < 500:
            parser.allow_all = True  # no robots.txt means no restrictions
        elif resp.status_code >= 500:
            self._robots[origin] = None
            return None
        else:
            parser.parse(resp.text.splitlines())
        self._robots[origin] = parser
        return parser

    def allowed(self, url: str) -> bool:
        parser = self.robots(url)
        return bool(parser and parser.can_fetch(self.user_agent, url))

    def get(self, url: str):
        """GET a URL after checking robots.txt. Returns (response or None, robots_allowed)."""
        if not self.allowed(url):
            return None, False
        parser = self._robots.get(f"{urlsplit(url).scheme}://{urlsplit(url).netloc}")
        crawl_delay = parser.crawl_delay(self.user_agent) if parser else None
        self._wait(urlsplit(url).netloc, float(crawl_delay) if crawl_delay else None)
        return self.session.get(url, timeout=TIMEOUT_SECONDS), True
