"""Tests for the curation pipeline. Run from the study folder:

    python -m unittest discover -s tests -v

Uses only the standard library test runner and a fictional vendor page.
"""

from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
STUDY = HERE.parent
sys.path.insert(0, str(STUDY / "scripts"))

import jsonschema  # noqa: E402

from common import load_vendors, page_id  # noqa: E402
from discover import classify, normalize  # noqa: E402
from extract import Section, count_entity, extract_sections, features, segment, word_count  # noqa: E402
from sample import select, stratum  # noqa: E402
from segment import index_row, passages_for_page  # noqa: E402

FIXTURE = (HERE / "fixtures" / "lumen_flags_platform.html").read_text(encoding="utf-8")
LUMEN = {"id": "lumenflags", "name": "Lumen Flags", "category": "feature_flagging",
         "aliases": ["Lumen Flags", "Lumen Flags Cloud"]}
DRIFT = {"id": "driftline", "name": "Driftline", "category": "feature_flagging", "aliases": ["Driftline"]}
VENDORS = [LUMEN, DRIFT]


def load_schema(name: str) -> dict:
    return json.loads((STUDY / "schemas" / name).read_text())


class ExtractTests(unittest.TestCase):
    def setUp(self):
        self.sections = extract_sections(FIXTURE)
        self.all_text = " ".join(p for s in self.sections for p in s.paragraphs)

    def test_drops_page_chrome(self):
        self.assertNotIn("script text", self.all_text)
        self.assertNotIn("newsletter", self.all_text)
        self.assertNotIn("All rights reserved", self.all_text)

    def test_keeps_div_only_card_text(self):
        self.assertIn("Roll out to 5% of users", self.all_text)

    def test_heading_paths(self):
        paths = [s.heading_path for s in self.sections]
        self.assertIn(("Feature flags without the network hop",), paths)
        self.assertIn(("Feature flags without the network hop", "Built for safe releases", "Kill switches"), paths)

    def test_no_duplicate_paragraphs(self):
        paras = [p for s in self.sections for p in s.paragraphs]
        self.assertEqual(len(paras), len(set(paras)))


class SegmentTests(unittest.TestCase):
    def setUp(self):
        self.passages = segment(extract_sections(FIXTURE))

    def test_word_bounds(self):
        for _, text in self.passages:
            self.assertGreaterEqual(word_count(text), 25, text)
            self.assertLessEqual(word_count(text), 200, text)

    def test_cards_merge_under_parent_heading(self):
        merged = [(h, t) for h, t in self.passages if "Kill switches" in t]
        self.assertEqual(len(merged), 1)
        heading, text = merged[0]
        self.assertEqual(heading, ("Feature flags without the network hop", "Built for safe releases"))
        self.assertIn("Percentage rollouts.", text)
        self.assertIn("Targeting rules.", text)

    def test_short_orphan_section_dropped(self):
        self.assertFalse(any("Just a few words" in t for _, t in self.passages))

    def test_expected_passage_count(self):
        self.assertEqual(len(self.passages), 4)

    def test_long_paragraph_splits_at_sentences(self):
        sentence = "Lumen Flags stores every flag change in an audit log with the author and time. "
        long = Section(heading_path=("Audit",), paragraphs=[sentence * 30])
        out = segment([long])
        self.assertGreater(len(out), 1)
        for _, text in out:
            self.assertLessEqual(word_count(text), 200)
            self.assertTrue(text.rstrip().endswith("."))

    def test_deterministic(self):
        self.assertEqual(self.passages, segment(extract_sections(FIXTURE)))


class FeatureTests(unittest.TestCase):
    def setUp(self):
        self.by_heading = {h[-1]: t for h, t in segment(extract_sections(FIXTURE))}

    def test_brand_voice_passage(self):
        f = features(self.by_heading["Feature flags without the network hop"], LUMEN, VENDORS)
        self.assertEqual(f["entity_mentions"], 0)
        self.assertFalse(f["entity_explicit"])
        self.assertEqual(f["first_person_refs"], 2)   # Our, we
        self.assertEqual(f["pronoun_refs"], 3)        # It, them, sentence-initial That
        self.assertEqual(f["generic_refs"], 1)        # the API
        self.assertTrue(f["has_number"])              # 5 ms, 14 languages

    def test_standards_are_not_numbers(self):
        f = features(self.by_heading["Security and compliance"], LUMEN, VENDORS)
        self.assertTrue(f["has_named_standard"])
        self.assertFalse(f["has_number"])             # SOC 2 is a standard, not a number
        self.assertEqual(f["entity_mentions"], 1)     # "Lumen Flags Cloud" counted once

    def test_other_vendor_mentions(self):
        f = features(self.by_heading["How we compare"], LUMEN, VENDORS)
        self.assertEqual(f["entity_mentions"], 1)
        self.assertEqual(f["other_vendor_mentions"], 2)

    def test_relative_that_not_counted(self):
        f = features("Lumen Flags ships rules that update in seconds across regions.", LUMEN, VENDORS)
        self.assertEqual(f["pronoun_refs"], 0)

    def test_us_country_code_not_first_person(self):
        f = features("Lumen Flags hosts data in US and EU regions.", LUMEN, VENDORS)
        self.assertEqual(f["first_person_refs"], 0)

    def test_case_sensitive_alias(self):
        temporal = {"id": "temporal", "aliases": ["Temporal"], "case_sensitive": True}
        self.assertEqual(count_entity("Temporal handles temporal drift.", temporal), 1)

    def test_alias_with_symbol(self):
        dagster = {"id": "dagster", "aliases": ["Dagster", "Dagster+"]}
        self.assertEqual(count_entity("Dagster+ adds hosting to Dagster.", dagster), 2)


class DiscoverTests(unittest.TestCase):
    def test_classify(self):
        cases = {
            "https://flipt.io/": "home",
            "https://flipt.io/pricing": "pricing",
            "https://flipt.io/blog/launch-week": None,
            "https://flipt.io/integrations": "integrations",
            "https://flipt.io/integrations/slack": None,
            "https://flipt.io/vs/launchdarkly": "comparison",
            "https://flipt.io/launchdarkly-alternative": "comparison",
            "https://flipt.io/features/rollouts": "product",
            "https://flipt.io/security": "security",
            "https://docs.flipt.io/introduction": "docs_intro",
            "https://docs.flipt.io/guides/self-host": None,
            "https://flipt.io/de/pricing": None,
            "https://flipt.io/about": "other",
            "https://example.com/": None,
        }
        for url, expected in cases.items():
            self.assertEqual(classify(url, "flipt.io"), expected, url)

    def test_normalize(self):
        self.assertEqual(normalize("http://Flipt.io/pricing/?utm=x#top"), "https://flipt.io/pricing")
        self.assertEqual(normalize("https://flipt.io"), "https://flipt.io/")


class SampleTests(unittest.TestCase):
    def _passage(self, i, vendor, category, named, specific):
        return {"passage_id": f"{vendor}:{i:012x}:p000", "vendor": vendor, "category": category,
                "page_type": "product", "word_count": 50,
                "features": {"entity_explicit": named, "has_number": specific, "has_named_standard": False}}

    def test_balanced_and_capped(self):
        passages, i = [], 0
        for cat in ["feature_flagging", "workflow_orchestration"]:
            for vendor in [f"{cat[:4]}a", f"{cat[:4]}b", f"{cat[:4]}c"]:
                for named in (True, False):
                    for specific in (True, False):
                        for _ in range(5):
                            passages.append(self._passage(i, vendor, cat, named, specific))
                            i += 1
        chosen, shortfall = select(passages, n=32, vendor_cap=4)
        self.assertEqual(len(chosen), 24)               # cap of 4 x 6 vendors binds before 32
        self.assertTrue(shortfall)
        per_vendor = {}
        for p in chosen:
            per_vendor[p["vendor"]] = per_vendor.get(p["vendor"], 0) + 1
        self.assertTrue(all(c <= 4 for c in per_vendor.values()))
        again, _ = select(passages, n=32, vendor_cap=4)
        self.assertEqual([p["passage_id"] for p in chosen], [p["passage_id"] for p in again])

    def test_stratum_labels(self):
        self.assertEqual(stratum(self._passage(0, "v", "c", True, True)), "named_specific")
        self.assertEqual(stratum(self._passage(0, "v", "c", False, False)), "unnamed_capability")


class SchemaTests(unittest.TestCase):
    def test_passages_match_schema(self):
        page = {"page_id": page_id("lumenflags", "https://lumenflags.example/platform"),
                "page_type": "product", "snapshot": "2027-01-05"}
        rows = passages_for_page(FIXTURE, page, LUMEN, VENDORS)
        schema = load_schema("passage.schema.json")
        for row in rows:
            jsonschema.validate(row, schema)
            self.assertNotIn("text", index_row(row))
        # The opening passage never names the product, but the page title does: the detachment case.
        first = rows[0]
        self.assertEqual(first["page_title"], "Lumen Flags Platform")
        self.assertTrue(first["entity_in_title"])
        self.assertFalse(first["features"]["entity_explicit"])

    def test_manifest_row_matches_schema(self):
        row = {"page_id": page_id("lumenflags", "https://lumenflags.example/"), "vendor": "lumenflags",
               "url": "https://lumenflags.example/", "page_type": "home", "volatile": False,
               "snapshot": "2027-01-05", "fetched_at": "2027-01-05T17:00:00+00:00", "http_status": 200,
               "robots_allowed": True, "raw_path": "data/raw/x.html", "html_sha256": "a" * 64,
               "text_sha256": "b" * 64, "error": None}
        jsonschema.validate(row, load_schema("page.schema.json"))

    def test_real_vendor_config_loads(self):
        vendors = load_vendors()
        self.assertGreaterEqual(len(vendors), 15)
        for v in vendors:
            self.assertTrue(v["aliases"])
            self.assertIn(v["category"], {"feature_flagging", "workflow_orchestration"})


if __name__ == "__main__":
    unittest.main()
