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
        "colorLightHex": "#116BDF",
        "colorDarkHex": "#4790FB",
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


def second_collection(first_text, status="verified", author="Ada Lovelace"):
    """(index entry, file) for an 'other' collection whose first quote reads `first_text`."""
    quotes = [
        {
            "id": f"oth-00{n}",
            "content": text,
            "authorName": author,
            "source": "Notes",
            "sourceType": "book",
            "quoteDate": "1843",
            "verificationStatus": status if n == 1 else "verified",
            "notes": "",
            "tags": ["courage"],
            "addedAt": STAMP,
        }
        for n, text in ((1, first_text), (2, "A line found nowhere else."))
    ]
    shared = dict(valid_tree()["file"], id="other", name="Other")
    shared.pop("quotes")
    entry = dict(
        shared,
        quoteCount=2,
        previewQuotes=[first_text, "A line found nowhere else."],
        contentHash="sha256-BBBB",
        bytes=512,
    )
    return entry, dict(shared, quotes=quotes)


def run_validator(tree, *args):
    """Writes `tree` out and validates it. Returns (exit code, everything printed).

    A tree may also carry "other", a second collection as (index entry, file),
    and "exceptions", the document for schema/known-standing-disagreements.json.
    """
    with tempfile.TemporaryDirectory() as root:
        os.makedirs(os.path.join(root, "collections"))
        os.makedirs(os.path.join(root, "schema"))
        documents = {
            "collections.json": tree["index"],
            os.path.join("collections", "demo.json"): tree["file"],
            os.path.join("schema", "tags.json"): tree["tags"],
            os.path.join("schema", "website-icons.json"): {"names": ["book"]},
            os.path.join("schema", "palette.json"): {
                "tokens": {"blue": {"light": "#116BDF", "dark": "#4790FB"}}
            },
        }
        if "other" in tree:
            entry, file = tree["other"]
            tree["index"]["collections"].append(entry)
            documents[os.path.join("collections", "other.json")] = file
        if "exceptions" in tree:
            documents[os.path.join("schema", "known-standing-disagreements.json")] = tree["exceptions"]
        for relative, document in documents.items():
            with open(os.path.join(root, relative), "w", encoding="utf-8") as f:
                json.dump(document, f)
        done = subprocess.run(
            [sys.executable, SCRIPT, "--root", root, "--strict", "--require-tags", *args],
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

    # --- colour

    def test_colour_name_must_be_a_palette_token(self):
        for side, where in ((lambda: self.file, "demo: file"), (lambda: self.entry, "demo: index")):
            with self.subTest(where=where):
                self.setUp()
                side()["colorName"] = "navyBlue"
                self.assert_rejected(f"{where}: colorName 'navyBlue' is not a Palette 2.0 token")

    def test_hex_pair_must_be_the_tokens_pair(self):
        for side, where in ((lambda: self.file, "demo: file"), (lambda: self.entry, "demo: index")):
            with self.subTest(where=where):
                self.setUp()
                side()["colorDarkHex"] = "#000000"
                self.assert_rejected(f"{where}: colorDarkHex '#000000' is not 'blue''s #4790FB")

    def test_hex_pair_is_required(self):
        del self.file["colorLightHex"]
        self.assert_rejected("demo: file: colorLightHex is missing")

    def test_hex_case_does_not_matter(self):
        self.file["colorLightHex"] = "#116bdf"
        self.assert_accepted()


def exception_for(text, *members):
    """An entry for the known-disagreements file: members are (id, collection, status)."""
    return {
        "text": text,
        "quotes": [
            {"id": i, "collection": c, "verificationStatus": st} for i, c, st in members
        ],
    }


class StandingTests(unittest.TestCase):
    """The same quote text must carry the same verificationStatus in every collection."""

    TEXT = "Quote number 1."

    def tree_with(self, other_text=TEXT, other_status="verified", **extra):
        tree = valid_tree()
        tree["other"] = second_collection(other_text, other_status)
        tree.update(extra)
        return tree

    def disagreeing_exceptions(self, *entries):
        return {"note": "tests", "groups": list(entries)}

    DISAGREEMENT = exception_for(
        "quote number 1", ("demo-001", "demo", "verified"), ("oth-001", "other", "attributed")
    )

    def assert_accepted(self, tree, *args):
        code, output = run_validator(tree, *args)
        self.assertEqual(code, 0, output)
        return output

    def assert_rejected(self, tree, naming, *args):
        code, output = run_validator(tree, *args)
        self.assertEqual(code, 1, output)
        self.assertIn(naming, output)
        self.assertNotIn("Traceback", output)
        return output

    def test_a_group_that_agrees_passes(self):
        output = self.assert_accepted(self.tree_with())
        self.assertIn("1 duplicate-text group(s)", output)
        self.assertIn("0 disagreeing", output)

    def test_a_group_that_agrees_on_something_other_than_verified_passes(self):
        tree = self.tree_with(other_status="attributed")
        tree["file"]["quotes"][0]["verificationStatus"] = "attributed"
        self.assert_accepted(tree)

    def test_a_new_disagreement_fails_and_names_every_copy(self):
        output = self.assert_rejected(
            self.tree_with(other_status="attributed"), "different verificationStatus values"
        )
        self.assertIn("demo-001 (demo) verified", output)
        self.assertIn("oth-001 (other) attributed", output)

    def test_without_a_known_list_a_disagreement_fails(self):
        tree = self.tree_with(other_status="unverified")
        self.assertNotIn("exceptions", tree)
        self.assert_rejected(tree, "standing:")

    def test_a_known_disagreement_passes(self):
        tree = self.tree_with(
            other_status="attributed", exceptions=self.disagreeing_exceptions(self.DISAGREEMENT)
        )
        output = self.assert_accepted(tree)
        self.assertIn("1 disagreeing, 1 on the known list", output)

    def test_a_known_disagreement_may_change_standings_while_it_still_disagrees(self):
        tree = self.tree_with(
            other_status="unverified", exceptions=self.disagreeing_exceptions(self.DISAGREEMENT)
        )
        self.assert_accepted(tree)

    def test_an_entry_whose_group_now_agrees_is_stale(self):
        tree = self.tree_with(exceptions=self.disagreeing_exceptions(self.DISAGREEMENT))
        output = self.assert_rejected(tree, "the entry for 'quote number 1' is stale")
        self.assertIn("Delete the entry", output)
        self.assertIn("all its copies now agree", output)

    def test_an_entry_whose_quotes_are_gone_is_stale(self):
        tree = valid_tree()
        tree["exceptions"] = self.disagreeing_exceptions(self.DISAGREEMENT)
        self.assert_rejected(tree, "no group of duplicate quotes matches it any more")

    def test_a_listed_group_that_gains_a_copy_fails(self):
        listed = exception_for("quote number 1", ("oth-001", "other", "attributed"))
        tree = self.tree_with(other_status="attributed", exceptions=self.disagreeing_exceptions(listed))
        self.assert_rejected(tree, "has gained ['demo-001']")

    def test_a_malformed_known_list_is_reported_not_raised(self):
        for document in ({"groups": "nope"}, {"groups": [{"text": "x"}]}, {"groups": [7]}):
            with self.subTest(document=document):
                tree = self.tree_with(exceptions=document)
                self.assert_rejected(tree, "known-standing-disagreements.json")

    def test_an_entry_must_be_written_in_normalized_form(self):
        listed = exception_for("Quote number 1.", ("demo-001", "demo", "verified"))
        tree = self.tree_with(other_status="attributed", exceptions=self.disagreeing_exceptions(listed))
        self.assert_rejected(tree, "is not in normalized form")

    def test_punctuation_case_and_quote_style_do_not_hide_a_disagreement(self):
        for variant in (
            "QUOTE NUMBER 1",
            "\u201cQuote number 1.\u201d",
            "Quote  number\n1!",
            "Quote number 1\u2026",
        ):
            with self.subTest(variant=variant):
                self.assert_rejected(
                    self.tree_with(other_text=variant, other_status="unverified"), "standing:"
                )

    def test_different_words_do_not_collide(self):
        for other in ("Quote number 11.", "Quote number one.", "Quote, number 1 and more."):
            with self.subTest(other=other):
                output = self.assert_accepted(self.tree_with(other_text=other, other_status="unverified"))
                self.assertIn("0 duplicate-text group(s)", output)

    def test_a_scoped_run_checks_groups_that_include_its_collection(self):
        tree = self.tree_with(other_status="attributed")
        self.assert_rejected(tree, "standing:", "--collection", "other")

    def test_a_scoped_run_does_not_report_stale_entries(self):
        tree = self.tree_with(exceptions=self.disagreeing_exceptions(self.DISAGREEMENT))
        self.assert_accepted(tree, "--collection", "demo")


class NormalizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, os.path.dirname(SCRIPT))
        import validate_collections

        cls.normalize = staticmethod(validate_collections.normalize_quote_text)

    def test_the_same_words_normalize_alike(self):
        same = [
            "It\u2019s not what happens to you.",
            "it's NOT what happens to you",
            "\u201cIt\u2019s not what happens to you,\u201d",
            "It's not what happens\n  to you...",
        ]
        self.assertEqual({self.normalize(t) for t in same}, {"it s not what happens to you"})

    def test_dashes_and_ellipses_are_unified(self):
        self.assertEqual(self.normalize("fear itself\u2014nameless"), self.normalize("fear itself--nameless"))
        self.assertEqual(self.normalize("done\u2026 and"), self.normalize("done . . . and"))

    def test_other_scripts_and_accents_survive(self):
        self.assertEqual(self.normalize("Estée Lauder"), "estée lauder")
        self.assertEqual(self.normalize("\u0928\u092e\u0938\u094d\u0924\u0947!"), "\u0928\u092e\u0938\u094d\u0924\u0947")

    def test_different_words_stay_different(self):
        self.assertNotEqual(self.normalize("its"), self.normalize("it's"))
        self.assertNotEqual(self.normalize("Stay hungry."), self.normalize("Stay hungry. Stay foolish."))


if __name__ == "__main__":
    unittest.main()
