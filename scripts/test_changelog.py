#!/usr/bin/env python3
"""Tests for changelog.py: folding fragments into a version file, and its refusals.

Each test builds a small changelogs/ tree in a temporary directory. Stdlib only.

    python3 scripts/test_changelog.py
"""

import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import changelog  # noqa: E402

OLD_VERSION = """## [1.0.0] - 2026-06-27
### Added
The first collections.
"""


class ChangelogTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="changelog-test-")
        os.makedirs(os.path.join(self.root, "changelogs", "unreleased"))
        self.write("changelogs/1.0.0.md", OLD_VERSION)
        self.write("changelogs/unreleased/README.md", "Not a fragment.\n")
        changelog.write_index(self.root)

    def tearDown(self):
        shutil.rmtree(self.root)

    def write(self, relative, text):
        with open(os.path.join(self.root, relative), "w", encoding="utf-8") as handle:
            handle.write(text)

    def read(self, relative):
        with open(os.path.join(self.root, relative), encoding="utf-8") as handle:
            return handle.read()

    def exists(self, relative):
        return os.path.exists(os.path.join(self.root, relative))

    def fragment(self, name, text):
        self.write(f"changelogs/unreleased/{name}.md", text)
        changelog.write_index(self.root)

    def assertRefused(self, call, needle):
        with self.assertRaises(changelog.ChangelogError) as caught:
            call()
        self.assertIn(needle, str(caught.exception))

    def test_release_folds_sections_in_order_and_bodies_by_file_name(self):
        self.fragment("quotes-b", "### Fixed\n- **B**: fixed.\n\n### Added\nB's quotes,\nwrapped.\n")
        self.fragment("audit-a", "### Audited\nA audited.\n\n### Added\n- **A**: added.\n")
        changelog.release(self.root, "1.1.0", "2026-10-31")
        self.assertEqual(
            self.read("changelogs/1.1.0.md"),
            "## [1.1.0] - 2026-10-31\n"
            "### Added\n- **A**: added.\n\nB's quotes,\nwrapped.\n\n"
            "### Fixed\n- **B**: fixed.\n\n"
            "### Audited\nA audited.\n",
        )

    def test_release_deletes_the_fragments_keeps_the_readme_and_rewrites_the_index(self):
        self.fragment("quotes-a", "### Added\nA.\n")
        changelog.release(self.root, "1.1.0", "2026-10-31")
        self.assertFalse(self.exists("changelogs/unreleased/quotes-a.md"))
        self.assertTrue(self.exists("changelogs/unreleased/README.md"))
        index = self.read("changelogs/README.md")
        self.assertLess(index.index("[1.1.0]"), index.index("[1.0.0]"))
        self.assertNotIn("Unreleased:", index)
        changelog.check(self.root)

    def test_extend_adds_new_fragments_to_an_open_release_and_keeps_its_edits(self):
        self.fragment("quotes-a", "### Added\nA.\n")
        changelog.release(self.root, "1.1.0", "2026-10-31")
        self.write("changelogs/1.1.0.md", self.read("changelogs/1.1.0.md").replace("A.", "A, as reviewed."))
        self.fragment("quotes-b", "### Fixed\nB fixed.\n\n### Added\nB.\n")
        changelog.release(self.root, "1.1.0", "2026-11-07", extend=True)
        self.assertEqual(
            self.read("changelogs/1.1.0.md"),
            "## [1.1.0] - 2026-11-07\n### Added\nA, as reviewed.\n\nB.\n\n### Fixed\nB fixed.\n",
        )
        self.assertFalse(self.exists("changelogs/unreleased/quotes-b.md"))
        changelog.check(self.root)

    def test_extend_refuses_a_version_with_no_file(self):
        self.fragment("quotes-a", "### Added\nA.\n")
        self.assertRefused(lambda: changelog.release(self.root, "1.1.0", "2026-10-31", extend=True), "does not exist")

    def test_notes_are_the_file_without_its_heading(self):
        self.assertEqual(changelog.notes(self.root, "1.0.0"), "### Added\nThe first collections.\n")

    def test_notes_refuse_a_version_with_no_file(self):
        self.assertRefused(lambda: changelog.notes(self.root, "1.0.1"), "not found")

    def test_release_refuses_with_no_fragments(self):
        self.assertRefused(lambda: changelog.release(self.root, "1.1.0", "2026-10-31"), "no fragments")

    def test_release_refuses_an_existing_version(self):
        self.fragment("quotes-a", "### Added\nA.\n")
        self.assertRefused(lambda: changelog.release(self.root, "1.0.0", "2026-10-31"), "already exists")
        self.assertTrue(self.exists("changelogs/unreleased/quotes-a.md"))

    def test_check_refuses_malformed_fragments(self):
        cases = [
            ("Loose text, no section.\n", "outside any"),
            ("### Improved\nX.\n", "unknown section"),
            ("### Added\n\n", "no entries"),
            ("## [1.1.0] - 2026-10-31\n### Added\nX.\n", "unexpected heading"),
        ]
        for text, needle in cases:
            with self.subTest(needle=needle):
                self.fragment("bad", text)
                self.assertRefused(lambda: changelog.check(self.root), needle)

    def test_check_refuses_a_version_file_whose_heading_disagrees_with_its_name(self):
        self.write("changelogs/1.0.1.md", "## [1.0.2] - 2026-07-01\n### Fixed\nX.\n")
        self.assertRefused(lambda: changelog.check(self.root), "must start with '## [1.0.1]")

    def test_a_version_file_may_open_with_a_paragraph(self):
        self.write("changelogs/1.0.1.md", "## [1.0.1] - 2026-07-01\nBackfilled later.\n\n### Fixed\nX.\n")
        changelog.write_index(self.root)
        changelog.check(self.root)

    def test_check_refuses_a_stale_index(self):
        self.write("changelogs/1.0.1.md", "## [1.0.1] - 2026-07-01\n### Fixed\nX.\n")
        self.assertRefused(lambda: changelog.check(self.root), "out of date")

    def test_the_index_counts_waiting_fragments(self):
        self.fragment("quotes-a", "### Added\nA.\n")
        self.assertIn("Unreleased: 1 fragment", self.read("changelogs/README.md"))

    def test_this_repository_passes(self):
        changelog.check(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


if __name__ == "__main__":
    unittest.main()
