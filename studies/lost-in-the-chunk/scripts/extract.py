"""Turn a page's HTML into heading-scoped sections, then into passages with features.

Deterministic on purpose: the same HTML always yields the same passages, so
snapshots from different measurement windows can be compared directly.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, NavigableString, Tag

MIN_WORDS = 25
MAX_WORDS = 200

# Removed before extraction: page chrome, not content.
DROP_TAGS = ["script", "style", "noscript", "svg", "nav", "header", "footer", "aside", "form", "iframe", "template", "button"]
HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4}
BLOCK_TAGS = {"p", "li", "blockquote", "dd", "td"}
# Many marketing sites put body copy in plain divs. A div counts as a text block
# when it holds no structural elements of its own (a "leaf" div).
LEAF_CANDIDATES = {"div", "section"}
STRUCTURAL = set(HEADING_TAGS) | BLOCK_TAGS | {"div", "section", "article", "ul", "ol", "table", "dl", "dt", "h5", "h6"}
CAPTURED_PARENTS = list(BLOCK_TAGS | set(HEADING_TAGS))
MIN_LEAF_WORDS = 3


def _is_leaf_block(el: Tag) -> bool:
    if el.name not in LEAF_CANDIDATES:
        return False
    if el.find(lambda t: isinstance(t, Tag) and t.name in STRUCTURAL) is not None:
        return False
    return word_count(el.get_text(" ")) >= MIN_LEAF_WORDS


@dataclass
class Section:
    heading_path: tuple[str, ...]
    paragraphs: list[str] = field(default_factory=list)

    @property
    def words(self) -> int:
        return sum(word_count(p) for p in self.paragraphs)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def word_count(text: str) -> int:
    return len(text.split())


def page_title(html: str | bytes) -> str:
    """The page's <title>. Kept per passage because it is context a chunk loses."""
    soup = BeautifulSoup(html, "lxml")
    return clean(soup.title.get_text(" ")) if soup.title else ""


def extract_sections(html: str | bytes) -> list[Section]:
    """Return content sections in document order, each with its heading path."""
    soup = BeautifulSoup(html, "lxml")
    for name in DROP_TAGS:
        for tag in soup.find_all(name):
            tag.decompose()
    root = soup.find("main") or soup.find("article") or soup.body or soup

    sections: list[Section] = [Section(heading_path=())]
    path: list[tuple[int, str]] = []

    for el in root.descendants:
        if not isinstance(el, Tag):
            continue
        if el.name in HEADING_TAGS:
            level = HEADING_TAGS[el.name]
            text = clean(el.get_text(" "))
            if not text:
                continue
            path = [(lvl, t) for lvl, t in path if lvl < level] + [(level, text)]
            sections.append(Section(heading_path=tuple(t for _, t in path)))
        elif el.name in BLOCK_TAGS or _is_leaf_block(el):
            # Skip anything inside a block or heading we already capture whole.
            if el.find_parent(CAPTURED_PARENTS) is not None:
                continue
            text = clean(el.get_text(" "))
            if text:
                sections[-1].paragraphs.append(text)

    return [s for s in sections if s.paragraphs]


SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


def sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_SPLIT.split(text) if s.strip()]


def _split_long(paragraph: str, max_words: int) -> list[str]:
    """Split one paragraph over max_words at sentence boundaries."""
    chunks, current = [], []
    for sent in sentences(paragraph):
        if current and word_count(" ".join(current + [sent])) > max_words:
            chunks.append(" ".join(current))
            current = []
        current.append(sent)
    if current:
        chunks.append(" ".join(current))
    return chunks


def _pack(paragraphs: list[str], max_words: int) -> list[str]:
    """Pack consecutive paragraphs into chunks of at most max_words."""
    pieces: list[str] = []
    for p in paragraphs:
        pieces.extend(_split_long(p, max_words) if word_count(p) > max_words else [p])
    chunks, current = [], []
    for piece in pieces:
        if current and word_count(" ".join(current + [piece])) > max_words:
            chunks.append(" ".join(current))
            current = []
        current.append(piece)
    if current:
        chunks.append(" ".join(current))
    return chunks


def segment(sections: list[Section], min_words: int = MIN_WORDS, max_words: int = MAX_WORDS) -> list[tuple[tuple[str, ...], str]]:
    """Return (heading_path, text) passages.

    A section long enough to stand alone becomes one or more passages under its
    own heading. Short sibling sections under the same parent heading, like a
    grid of feature cards, are merged under the parent, with each card's heading
    kept inline. That mirrors how retrieval chunkers treat short blocks.
    Anything still under min_words is dropped.
    """
    out: list[tuple[tuple[str, ...], str]] = []
    buf_parent: tuple[str, ...] | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf, buf_parent
        if buf and word_count(" ".join(buf)) >= min_words:
            for chunk in _pack(buf, max_words):
                if word_count(chunk) >= min_words:
                    out.append((buf_parent or (), chunk))
        buf, buf_parent = [], None

    for sec in sections:
        if sec.words >= min_words:
            flush()
            for chunk in _pack(sec.paragraphs, max_words):
                if word_count(chunk) >= min_words:
                    out.append((sec.heading_path, chunk))
            continue
        parent = sec.heading_path[:-1]
        leaf = sec.heading_path[-1] if sec.heading_path else ""
        text = " ".join(sec.paragraphs)
        item = f"{leaf}. {text}" if leaf and not leaf.endswith((".", "?", "!", ":")) else f"{leaf} {text}".strip()
        if buf_parent != parent or word_count(" ".join(buf + [item])) > max_words:
            flush()
            buf_parent = parent
        buf.append(item)
    flush()
    return out


# ---------- features ----------

FIRST_PERSON = re.compile(r"\b(?:[Ww]e|[Oo]urs?|us|Us)\b")
THIRD_PERSON = re.compile(r"\b(?:[Ii]ts?|[Tt]hey|[Tt]hem|[Tt]heir)\b")
SENTENCE_INITIAL_DEMONSTRATIVE = re.compile(r"^(?:This|These|That|Those)\b")
GENERIC = re.compile(
    r"\b[Tt]he (?:platform|product|tool|service|solution|system|app|application|engine|SDKs?|API)\b"
)
NAMED_STANDARDS = re.compile(
    r"\b(?:SOC ?[12](?: Type (?:I|II|1|2))?|ISO(?:/IEC)? ?(?:27001|27017|27018|27701|42001)|HIPAA|GDPR|CCPA|"
    r"PCI[- ]DSS|FedRAMP|OpenTelemetry|OpenFeature|SAML|SCIM|OIDC|OAuth ?2(?:\.0)?)\b"
)
NUMBER = re.compile(r"\d")


def _alias_pattern(alias: str, case_sensitive: bool) -> re.Pattern:
    flags = 0 if case_sensitive else re.IGNORECASE
    return re.compile(rf"(?<![\w]){re.escape(alias)}(?![\w])", flags)


def count_entity(text: str, vendor: dict) -> int:
    """Count mentions of a vendor's aliases, longest first, without double counting overlaps."""
    case_sensitive = bool(vendor.get("case_sensitive", False))
    masked = text
    total = 0
    for alias in sorted(vendor["aliases"], key=len, reverse=True):
        pattern = _alias_pattern(alias, case_sensitive)
        total += len(pattern.findall(masked))
        masked = pattern.sub(lambda m: "\0" * len(m.group(0)), masked)
    return total


def features(text: str, vendor: dict, all_vendors: list[dict]) -> dict:
    sents = sentences(text) or [text]
    mentions = count_entity(text, vendor)
    others = sum(count_entity(text, v) for v in all_vendors if v["id"] != vendor["id"])
    first_person = len(FIRST_PERSON.findall(text))
    pronouns = len(THIRD_PERSON.findall(text)) + sum(1 for s in sents if SENTENCE_INITIAL_DEMONSTRATIVE.match(s.strip()))
    generic = len(GENERIC.findall(text))
    has_standard = bool(NAMED_STANDARDS.search(text))
    without_standards = NAMED_STANDARDS.sub(" ", text)
    return {
        "entity_mentions": mentions,
        "entity_explicit": mentions > 0,
        "other_vendor_mentions": others,
        "first_person_refs": first_person,
        "pronoun_refs": pronouns,
        "generic_refs": generic,
        "unresolved_ref_rate": round((first_person + pronouns + generic) / len(sents), 3),
        "has_number": bool(NUMBER.search(without_standards)),
        "has_named_standard": has_standard,
        "sentence_count": len(sents),
    }
