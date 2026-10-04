#!/usr/bin/env python3
"""Tests for validate_collections.py: that the checks fire.

CI runs the validator against the real data, which proves only that today's data
passes. These build a small valid tree in a temporary directory, break one thing
at a time, and expect the validator to name it. Stdlib only.

    python3 scripts/test_validate_collections.py
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "validate_collections.py")
STAMP = "2026-01-02T03:04:05Z"


def valid_tree():
    """A tree the validator accepts: one collection of two quotes."""
    quotes = [
        {
            "id": f"demo-00{n}",
            "content": f"Quote number {n}.",
            "authorName": "Ada Lovelace",
            "source": "Notes",
            "sourceType": "book",
            "quoteDate": "1843",
            "verificationStatus": "verified",
            "notes": "",
            "tags": ["courage"],
            "addedAt": STAMP,
        }
        for n in (1, 2)
    ]
    shared = {
        "id": "demo",
        "name": "Demo",
        "description": "A collection for the validator's tests.",
        "author": "Quips Editorial",
        "colorName": "blue",
        "iconName": "book",
        "category": "Testing",
        "addedAt": STAMP,
        "lastUpdated": STAMP,
    }
    entry = dict(
        shared,
        quoteCount=2,
        previewQuotes=["Quote number 1.", "Quote number 2."],
        contentHash="sha256-AAAA",
        bytes=512,
    )
    return {
        "index": {"version": "1.0", "lastUpdated": STAMP, "collections": [entry]},
        "file": dict(shared, quotes=quotes),
        "tags": {
            "version": 1,
            "tags": [
                {"slug": "courage", "displayName": "Courage", "facet": "theme", "colorName": "red"}
            ],
        },
    }


def run_validator(tree):
    """Writes `tree` out and validates it. Returns (exit code, everything printed)."""
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "collections"))
        os.makedirs(os.path.join(root, "schema"))
        documents = {
            "collections.json": tree["index"],
            os.path.join("collections", "demo.json"): tree["file"],
            os.path.join("schema", "tags.json"): tree["tags"],
            os.path.join("schema", "website-icons.json"): {"names": ["book"]},
        }
        for relative, document in documents.items():
            with open(os.path.join(root, relative), "w", encoding="utf-8") as f:
                json.dump(document, f)
        done = subprocess.run(
            [sys.executable, SCRIPT, "--root", root, "--strict", "--require-tags"],
            capture_output=True,
            text=True,
            check=False,
        )
        return done.returncode, done.stdout + done.stderr


class ValidatorTests(unittest.TestCase):
    def setUp(self):
        self.tree = valid_tree()
        self.entry = self.tree["index"]["collections"][0]
        self.file = self.tree["file"]
        self.quote = self.file["quotes"][0]

    def assert_accepted(self):
        code, output = run_validator(self.tree)
        self.assertEqual(code, 0, output)

    def assert_rejected(self, naming):
        """The validator fails, says `naming`, and fails by reporting rather than raising."""
        code, output = run_validator(self.tree)
        self.assertEqual(code, 1, output)
        self.assertIn(naming, output)
        self.assertNotIn("Traceback", output)

    def test_the_valid_tree_is_accepted(self):
        self.assert_accepted()

    # --- collections.json, top level

    def test_index_top_level_keys_are_required(self):
        for key in ("version", "lastUpdated", "collections"):
            with self.subTest(key=key):
                self.tree = valid_tree()
                del self.tree["index"][key]
                self.assert_rejected(f"collections.json: top-level {key} is missing")

    def test_index_version_must_be_a_string(self):
        self.tree["index"]["version"] = 2
        self.assert_rejected("collections.json: top-level version is a number")

    def test_index_that_is_not_an_object_is_refused(self):
        self.tree["index"] = [self.entry]
        self.assert_rejected("collections.json is a list, not a JSON object")

    def test_index_entry_without_a_string_id_is_named_by_position(self):
        self.entry["id"] = 7
        self.assert_rejected("collections.json: entry 0 is not an object with a string id")

    def test_index_entry_listed_twice(self):
        self.tree["index"]["collections"].append(copy.deepcopy(self.entry))
        self.assert_rejected("demo: listed more than once in collections.json")

    # --- an index entry

    def test_entry_required_fields(self):
        strings = ("name", "description", "author", "colorName", "iconName", "category")
        for key in strings + ("quoteCount", "previewQuotes"):
            for state, value in (("missing", None), ("null", None)):
                with self.subTest(key=key, state=state):
                    self.tree = valid_tree()
                    entry = self.tree["index"]["collections"][0]
                    if state == "missing":
                        del entry[key]
                    else:
                        entry[key] = value
                    self.assert_rejected(f"demo: index {key} is {state}")
        for key in strings:
            with self.subTest(key=key, state="retyped"):
                self.tree = valid_tree()
                self.tree["index"]["collections"][0][key] = 5
                self.assert_rejected(f"demo: index {key} is a number")

    def test_entry_quote_count_must_be_an_integer(self):
        for value, kind in (("2", "a string"), (True, "a boolean"), (1.5, "a number")):
            with self.subTest(value=value):
                self.tree = valid_tree()
                self.tree["index"]["collections"][0]["quoteCount"] = value
                self.assert_rejected(f"demo: index quoteCount is {kind}")

    def test_entry_quote_count_may_be_a_whole_float(self):
        # Swift's Int decodes 2.0, so the validator does not refuse what the app takes.
        self.entry["quoteCount"] = 2.0
        self.assert_accepted()

    def test_entry_preview_quotes_must_all_be_strings(self):
        self.entry["previewQuotes"] = ["Quote number 1.", 2]
        self.assert_rejected("demo: index previewQuotes holds a value that is not a string")

    def test_entry_optional_fields_are_typed_when_present(self):
        for key, value, kind in (
            ("contentHash", 5, "a number"),
            ("bytes", "512", "a string"),
            ("addedAt", 5, "a number"),
            ("lastUpdated", 5, "a number"),
        ):
            with self.subTest(key=key):
                self.tree = valid_tree()
                self.tree["index"]["collections"][0][key] = value
                self.assert_rejected(f"demo: index {key} is {kind}")

    def test_entry_optional_fields_may_be_absent(self):
        del self.entry["contentHash"]
        del self.entry["bytes"]
        self.assert_accepted()

    # --- a collection file

    def test_file_required_fields(self):
        for key in ("name", "description", "author", "colorName", "iconName", "category", "lastUpdated"):
            for state in ("missing", "null", "a number"):
                with self.subTest(key=key, state=state):
                    self.tree = valid_tree()
                    if state == "missing":
                        del self.tree["file"][key]
                    else:
                        self.tree["file"][key] = None if state == "null" else 5
                    self.assert_rejected(f"demo: file {key} is {state}")

    def test_file_that_is_not_an_object(self):
        self.tree["file"] = [self.file]
        self.assert_rejected("demo: file is a list, not a JSON object")

    def test_file_quotes_must_all_be_objects(self):
        self.file["quotes"].append("a stray string")
        self.assert_rejected("demo: 'quotes' holds a value that is not an object")

    # --- a quote

    def test_quote_required_fields_must_be_strings(self):
        for key in ("content", "authorName", "source", "notes"):
            for value, kind in ((None, "null"), (5, "a number")):
                with self.subTest(key=key, kind=kind):
                    self.tree = valid_tree()
                    self.tree["file"]["quotes"][0][key] = value
                    self.assert_rejected(f"demo/demo-001: {key} is {kind}, not a string")

    def test_quote_id_that_is_not_a_string_is_reported_not_raised(self):
        self.quote["id"] = 5
        self.assert_rejected("id is a number, not a string")

    def test_quote_status_that_is_not_a_string_is_reported_not_raised(self):
        self.quote["verificationStatus"] = ["verified"]
        self.assert_rejected("demo/demo-001: invalid verificationStatus")

    def test_quote_date_written_as_a_number(self):
        self.quote["quoteDate"] = 1843
        self.assert_rejected("demo/demo-001: quoteDate is a number")

    def test_quote_date_may_be_null_or_absent(self):
        self.quote["quoteDate"] = None
        del self.file["quotes"][1]["quoteDate"]
        self.assert_accepted()

    def test_quote_optional_fields_are_typed_when_present(self):
        for key, value, kind in (
            ("authorDateOfBirth", 1815, "a number"),
            ("sourceCollection", 5, "a number"),
            ("newsletterIssue", "3", "a string"),
        ):
            with self.subTest(key=key):
                self.tree = valid_tree()
                self.tree["file"]["quotes"][0][key] = value
                self.assert_rejected(f"demo/demo-001: {key} is {kind}")

    def test_quote_tags_must_all_be_strings(self):
        self.quote["tags"] = ["courage", 5]
        self.assert_rejected("demo/demo-001: 'tags' holds a value that is not a string")

    # --- schema/tags.json

    def test_tag_entries_need_a_slug_and_a_display_name(self):
        for key in ("slug", "displayName"):
            with self.subTest(key=key):
                self.tree = valid_tree()
                self.tree["tags"]["tags"].append({"slug": "calm", "displayName": "Calm", "facet": "theme"})
                del self.tree["tags"]["tags"][1][key]
                self.assert_rejected(f"{key} is missing")

    def test_tag_entry_that_is_not_an_object(self):
        self.tree["tags"]["tags"].append("calm")
        self.assert_rejected("tag 1 is a string, not an object")


if __name__ == "__main__":
    unittest.main()
