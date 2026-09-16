# Contributing

Thanks for helping improve the Quips collections. This repo holds data only —
quotes and their metadata — validated in CI.

## After every data edit

Any change to `collections.json` **or** to a `collections/<id>.json` file needs
both of these, in this order, before you commit:

```sh
python3 scripts/compute_hashes.py                  # refresh contentHash + bytes
python3 scripts/validate_collections.py --strict   # warnings fail too (CI uses this)
```

`compute_hashes.py` is not optional and it is easy to forget, because editing a
collection file quietly invalidates the index that points at it. Each index
entry stores a `contentHash` and `bytes` for its collection file; clients use
them to re-download only what changed. Touch the file without refreshing the
index and those two fields silently describe the *old* file. CI runs
`compute_hashes.py --check` and fails on the mismatch — including on pushes to
`main`, where a miss turns the branch red for everyone until someone notices.

Writing is idempotent: if nothing changed, the script produces no diff, so
running it when you didn't need it costs nothing. Run it whenever you're unsure.

Other useful validator invocations:

```sh
python3 scripts/validate_collections.py            # full check, warnings don't fail
python3 scripts/validate_collections.py --collection seinfeld
```

Scope matters: `--collection` skips the orphan and cross-collection prefix
checks, so run at least one full sweep before opening a PR.

Both scripts are stdlib-only (no install needed), and the validator is the
single source of truth for the rules below. JSON Schema in [`schema/`](schema/)
describes the file shapes for editors/tooling.

## Data model

### `collections.json` (index)

Top-level `version`, `lastUpdated`, and a `collections` array. Each entry
mirrors core fields of the collection file and adds `quoteCount` and two
`previewQuotes`. The entry's `name`, `author`, `category`, `colorName`, and
`iconName` must match the collection file exactly, and `quoteCount` must equal
the number of quotes in the file.

### `collections/<id>.json` (one collection)

```json
{
  "id": "seinfeld",
  "name": "Seinfeld",
  "description": "…",
  "author": "Quips Editorial",
  "colorName": "orange",
  "iconName": "tv.fill",
  "category": "Television",
  "lastUpdated": "2026-06-20T12:00:00Z",
  "quotes": [
    {
      "id": "seinfeld-001",
      "content": "No soup for you!",
      "authorName": "The Soup Nazi (Larry Thomas)",
      "source": "Seinfeld, S7E6 'The Soup Nazi' (1995)",
      "sourceType": "television",
      "quoteDate": "1995-11-02",
      "verificationStatus": "verified",
      "notes": "…"
    }
  ]
}
```

Rules enforced in CI:

- File `id` matches the filename; every file is in the index and vice versa.
- Quote `id` is `<prefix>-NNN` (3+ digits), unique within the collection; all
  quotes share one prefix, and each prefix is unique across all collections.
- Required quote fields: `id`, `content`, `authorName`, `source`,
  `verificationStatus`, `notes`.
- `verificationStatus` ∈ `verified`, `attributed`, `unverified`, `folk-wisdom`.
- `tags: []` (empty) means the quote was read and deliberately left untagged —
  distinct from having no `tags` key, which means the tagging pass has not
  reached it. Use it for a line that is iconic rather than about anything.
- `tags` (optional) must be slugs from `schema/tags.json`: at most 6, unique,
  ordered most-specific-first, and at least one of them a `theme` tag. Unknown
  slugs fail validation; a rejected spelling (e.g. `grit`) is told which tag to
  use instead. `--require-tags` turns "no tags at all" into an error — it stays
  off until the tagging pass reaches every collection.
- `sourceType` (optional) must be a known value — keep it in sync with
  `QuoteSourceType` in the iOS app.
- No duplicate quote text within a collection.

## Releasing

Maintainers cut a release by pushing a semver tag (`git tag v1.2.0 && git push
origin v1.2.0`). See [README](README.md#releasing).
