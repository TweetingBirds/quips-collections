# Release-notes fragments

Each pull request that changes something a release publishes writes its release notes
here, in a file of its own named after its branch with `/` turned into `-`: the branch
`quotes/add-stoics` writes `quotes-add-stoics.md`. Pull requests then never edit the
same file.

A fragment is one or more of `### Added`, `### Changed`, `### Removed`, `### Fixed`,
`### Audited` and `### Notes`, each followed by the notes in the house style of the
newest `changelogs/<version>.md`, and nothing outside a section:

```markdown
### Added
Two quotes added to existing collections:
- **Daily Inspiration**: …
```

`python3 scripts/changelog.py check` validates them (CI runs it), and `preview` prints
what the next release's notes would be. The weekly release PR runs
`python3 scripts/changelog.py release <version>`, which writes `changelogs/<version>.md`
from them and deletes them. This README is not a fragment.
