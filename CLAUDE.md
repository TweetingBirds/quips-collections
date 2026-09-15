# quips-collections

Data-only repo: quotes and their metadata, served from `data.quipsapp.com` and
validated in CI. There is no application code here.

## The one rule that is easy to get wrong

**Every edit to `collections.json` or any `collections/<id>.json` must be
followed by `compute_hashes.py`, then `validate_collections.py --strict`,
before you commit.**

```bash
python3 scripts/compute_hashes.py
python3 scripts/validate_collections.py --strict
```

Editing a collection file invalidates the index entry that points at it: each
entry carries a `contentHash` and `bytes` for its file, and clients use those to
decide what to re-download. Change the file, skip the refresh, and the index
silently describes the previous version.

This is the failure mode to design against, because nothing in your editing
session complains — the collection file looks perfectly correct on its own. It
surfaces only in CI, via `compute_hashes.py --check`. A run that edits quotes
and touches nothing else has almost certainly left the index stale.

It has already happened: commit 843cc20 edited `collections/christian-saints.json`
without updating `collections.json`, and `main` stayed red from that merge until
someone noticed days later.

Writing is idempotent — a clean tree produces no diff — so running it when it
wasn't needed is free. Run it whenever you're unsure. Never commit a data edit
without it.

Both scripts are stdlib-only; there is nothing to install.

## Recurring audit runs

Audit runs that fix a quote's sourcing, wording, or `verificationStatus` are
edits to a collection file like any other, and the rule above applies in full.
Two extra notes for these runs:

- Rewriting `.audit-state.json` alone is not a data edit and needs no hash
  refresh — but any run that *also* touched a collection file does.
- A run that finds every quote clean and changes nothing should commit nothing.
  Don't refresh the state cursor into an otherwise-empty commit and call it a
  no-op; a commit that touches a collection file is the signal that the hash
  refresh was required.

## Working conventions

- Use a branch and a PR. Don't push directly to `main`.
- Verification is a claim, not a feeling: `verified` requires *both* exact
  wording *and* a real primary source. Aggregator sites (BrainyQuote, Goodreads,
  AZQuotes) establish neither. See the `add-quotes` skill for the full bar.
- Derived feeds (`search-index.json`, `recently-added.json`, `on-this-day.json`,
  and friends) are rebuilt during release. Don't hand-edit them.
- `newsletter-issues.json` is the Quote Unquote log — hand-edited source, like
  `featured-schedule.json`, not an output. An entry's `status` is the whole
  point: only `sent` reaches `newsletter-picks.json`, and only a `sent` issue
  may carry an `issueNumber` it didn't already own publicly. Never write
  "Featured in Quote Unquote #N" into a collection quote's `notes` — membership
  is derived by `build_newsletter_picks.py`, and authoring it in prose is what
  put three unsent issues into three releases. `TweetingBirds/quote-unquote` has a
  `check_newsletter_sync.py` that verifies this file against the drafts.
- A collection's `iconName` must be one quipsapp.com can draw. The names it
  supports are mirrored in `schema/website-icons.json` and enforced by the
  validator; a new one has to reach the website's `js/icons.js` first, then
  `scripts/refresh_website_icons.py` pulls it into the mirror. Skipping that
  order ships a release that fails the website's deploy, not ours.
- Releases happen by pushing a semver tag: patch for quote edits, minor for a
  new collection. See [CONTRIBUTING.md](CONTRIBUTING.md).
