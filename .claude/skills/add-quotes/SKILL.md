---
name: add-quotes
description: Add one or more new quotes to an existing Quips collection. Use when the user wants to add, append, or insert quotes into a collection (e.g. "add 5 quotes to seinfeld", "add this Barney line to How I Met Your Mother"). Handles the verification status, the quote objects, id numbering, and keeps the collections.json index in sync.
---

# Add quotes to a collection

This skill operates in the **quips-collections** repo (the public data repo, served from
`data.quipsapp.com`). Run it with this repo as the working directory, on a branch.

Quotes live in `collections/<id>.json` under the `quotes` array. The root `collections.json`
is an index of every collection and must be kept in sync (its `quoteCount` and `lastUpdated`).

## Verification — the point of the task, do not cut corners

Every quote carries a `verificationStatus`, and the app shows it as a badge. There are
four values (the schema's enum, and the app's `PublicQuoteVerification`):

| value | means |
|---|---|
| `verified` | Both axes below hold. |
| `attributed` | The conventional attribution, without a confirmed primary source: the person may well have said it, but the wording or the source can't be traced. |
| `unverified` | Checked, and the attribution could not be confirmed, or is contested or wrong. |
| `folk-wisdom` | A proverb or saying with no single author to attribute it to. |

`verified` is a claim, not a feeling. Model confidence is exactly the failure mode: the most
quoted lines on the internet are also the most misattributed. Set it **only when both axes
hold**:

- **Wording is exact** — matches the primary source (allowing honest punctuation/transcription
  variance), not a popular paraphrase.
- **Attribution is real** — speaker *and* source trace to a primary or authoritative record:
  the actual episode/transcript, book (edition/page where possible), recorded speech, or
  published interview.

Rules:

- Aggregator sites (BrainyQuote, Goodreads, AZQuotes, Pinterest, "quotes about X" listicles)
  establish **neither** axis. A quote found only there is not `verified`.
- Be actively suspicious of lines attributed to magnet names — Einstein, Twain, Lincoln,
  Gandhi, Monroe, Mandela, Churchill. Trace it to a real source or drop it.
- For show/film quotes the primary source is the episode itself (or a faithful transcript):
  confirm the named character actually says the line, in that wording.
- When one axis fails, the status is `attributed` or `unverified`, never `verified` — name
  the failing axis in `notes` ("Attribution is the failing axis: …", as the existing
  entries do). Use `attributed` when the line is credibly the person's but untraceable, and
  `unverified` when the evidence points elsewhere or nowhere.
- Never invent or approximate a source, and never pad a batch to hit a number. Four solidly
  verified quotes beat seven shaky ones.

## Steps

1. **Identify the collection.** Match the user's request to a file in `collections/`. If
   ambiguous, list candidates and ask. The filename (minus `.json`) is the collection `id`.

2. **Read the collection file — as it is on `origin/main`** — to learn:
   - the quote `id` prefix and the current highest number. Quote ids are `<prefix>-NNN`,
     zero-padded to 3 digits (e.g. `himym-040`, `seinfeld-025`). Prefixes are per-collection
     — read it from the file, don't assume (e.g. `inspiration-daily` uses `di`,
     `tech-visionaries` uses `tv`).
   - the **exact field shape of existing entries**. The object in step 4 is illustrative; if
     the real entries carry extra or differently-named fields, match the file, not the template.

   Number from `origin/main`, not from a local branch: several sessions add quotes in
   parallel, and two branches that each took "max + 1" from a stale copy collide on merge
   (history is full of "Merge main; renumber…" commits). Fetch first, and check again
   after merging `main` into your branch:
   ```bash
   git fetch origin main
   git show origin/main:collections/<id>.json | python3 -c "import json,sys; print(max(q['id'] for q in json.load(sys.stdin)['quotes']))"
   ```

3. **Check for duplicates.** Before appending, confirm the quote — and any near-paraphrase of
   it — is not already in the collection. Skip duplicates and report them rather than adding them.
   The same text may already be in *another* collection, and that is allowed — but the copy you
   add must carry the same `verificationStatus` as the existing one, or the validator fails.
   Search the other collections' `content` first; if they disagree with what you found, settle
   all copies together rather than adding a new disagreement.

4. **Append each new quote** to the `quotes` array with all fields. When adding several at
   once, number them sequentially from the current max (`max+1`, `max+2`, …):
   ```json
   {
     "id": "himym-041",
     "content": "The exact quote text.",
     "authorName": "Character Name (Actor Name)",
     "source": "Show/Book/Film, S1E1 'Episode Title' (Year)",
     "quoteDate": "2005-09-19",
     "verificationStatus": "verified",
     "sourceType": "television",
     "notes": "One sentence of context about the quote.",
     "tags": ["friendship", "loyalty", "one-liner"],
     "addedAt": "2026-01-15T12:00:00Z"
   }
   ```
   - `authorName` — for shows/films use `Character (Actor)`; for people, the person's name.
   - `sourceType` — *optional* category for the kind of source, mirroring the app's
     `QuoteSourceType`. Match the file's existing entries: if they carry `sourceType`,
     include it; if they don't, leave it off. Allowed values (use the exact rawValue):
     `book`, `article`, `newspaper`, `magazine`, `comic`, `movie`, `television`,
     `podcast`, `radio`, `song`, `speech`, `interview`, `website`, `socialMedia`,
     `video`, `letter`, `poem`, `play`, `lecture`, `documentary`, `inPerson`,
     `unspecified`.
     E.g. a sitcom line is `television`, a film line `movie`, a conference talk or
     address `speech`, a book passage `book`, a comic-book/graphic-novel line `comic`.
   - `source` — be as specific as the evidence allows. Use `Show (2005-2014)` when you can't
     pin the episode.
   - `quoteDate` — `YYYY-MM-DD` when known; otherwise `c. YYYY` for an approximate year.
     Never invent a specific date to look precise.
   - `verificationStatus` — one of the four values above. Promote to `verified` only when
     the bar is met.
   - `notes` — a single sentence of context (and, if not `verified`, which axis failed).
   - `tags` — 3–5 slugs (hard max 6) from the controlled vocabulary in
     `schema/tags.json`. **Read that file's `useWhen` line for each tag you are
     considering** — the glosses are what keep the same idea from being tagged
     `perseverance` one week and `grit` the next, and the validator rejects any
     slug not listed. Rules:
     - **Ordered most-specific-first.** The ordering is the ranking: bulk import
       applies only the leading few, so lead with the tag that most distinguishes
       this quote from its neighbours, not the most generic one.
     - **At least one `theme` tag.** A quote tagged only `humor` and `one-liner`
       has not been tagged — tone and occasion say how you would *use* it, never
       what it is *about*.
     - **Tag the quote, not its source.** A Naruto line is not tagged `ninja`;
       the show is already in `source`, the genre already in `category`. A tag
       that restates another field is noise in every list that renders tags.
     - **An `occasion` tag is a claim about use.** `wedding` belongs on a line
       someone would actually read at a wedding, not on every quote mentioning
       love. Wrong here is worse than absent.
     - **If the quote is not about anything, write `"tags": []`.** Some lines are
       famous for being iconic, not for having a subject ("Hey! Listen!").
       An empty array records that you read it and decided; omitting the key
       means nobody has looked yet. Stretching a theme onto such a line is
       worse than leaving it bare — it still imports with its category tag.
     - Match the file: if the collection's existing entries have no `tags`, it
       has not been through the tagging pass — tag your new quotes anyway.
   - `addedAt` — ISO-8601 UTC timestamp of when the quote is added, as
     `<today>T12:00:00Z` (the same value you set for `lastUpdated` in step 5).
     **Required** — CI (`validate_collections.py --strict`) fails without it. It
     records dataset-recency (not when the quote was said — that's `quoteDate`)
     and drives dynamic collections like Recently Added. Never backdate it.

5. **Update the collection file's** top-level `lastUpdated` to today in `YYYY-MM-DDT12:00:00Z`.

6. **Update `collections.json`** — find the matching entry in the `collections` array:
   - Set `quoteCount` to the new total length of the `quotes` array.
   - Set that entry's `lastUpdated` to today (`YYYY-MM-DDT12:00:00Z`).
   - Bump the file's top-level `lastUpdated` to the same value.
   - Only touch `previewQuotes` if the user asks to feature a new quote.

7. **Refresh the index hashes.** Run `compute_hashes.py` to rewrite each entry's
   `contentHash` + `bytes` from the files on disk. These drive progressive downloads (clients
   re-fetch only collections whose hash changed), and CI rejects a stale index, so this is not
   optional. Run it after every edit to `collections.json` or any collection file:
   ```bash
   python3 scripts/compute_hashes.py
   # Which entries' hashes moved? Every id printed must be one you are committing.
   git show HEAD:collections.json | python3 -c "
   import json, sys
   old = {e['id']: e.get('contentHash') for e in json.load(sys.stdin)['collections']}
   new = {e['id']: e.get('contentHash') for e in json.load(open('collections.json'))['collections']}
   print(sorted(i for i in new if old.get(i) != new[i]))"
   ```
   **It hashes whatever is on disk, including edits you are not committing.** If the working
   tree carries someone's uncommitted changes to other collections, their hashes land in
   the index too, and CI's `compute_hashes.py --check` goes red on the commit that leaves
   those files out. After every run, confirm the only entries whose `contentHash` changed
   are collections you are committing, and restore any others from `HEAD`. To see exactly
   what CI will see, check a clean copy of the index you are about to commit:
   ```bash
   tmp=$(mktemp -d); git archive "$(git write-tree)" | tar -x -C "$tmp"
   (cd "$tmp" && python3 scripts/compute_hashes.py --check && python3 scripts/validate_collections.py --strict)
   ```

8. **Validate.** Run the shared validator, scoped to the collection you changed. It confirms
   both files parse, `quoteCount` matches the actual count, ids are unique and well-formed,
   required fields are present, the colour and icon are ones the clients can render, and
   there's no duplicate quote text. Don't report success until it passes.
   ```bash
   python3 scripts/validate_collections.py --strict --collection <id>
   ```

9. **Commit and open a PR** — see **Publishing** below. Your part ends at the PR.

10. **Report** how many quotes were added, the new total, the PR, anything not `verified`
    (with its status and reason), and any duplicates skipped.

## Publishing — how edits reach the site and app

Nothing changes for users until a **release** is cut. A release builds the data, uploads it to
R2 behind `data.quipsapp.com`, and creates a GitHub Release — public and hard to undo, so
**it is a human step: don't push a release tag.**

1. **Commit on a branch and open a PR** — this repo doesn't take direct pushes to `main`
   (CI validates the PR). Stage only the files you changed:
   ```bash
   git add collections.json collections/<id>.json
   git commit -m "Add N quotes to <id>"
   git push -u origin HEAD
   ```
   Don't edit `CHANGELOG.md`: release notes are written when a release is cut.
2. **The release.** Every Saturday a scheduled check decides whether merged changes warrant
   a release, picks the tier (patch for quote additions and edits, minor for a new
   collection), writes the `CHANGELOG.md` section, and opens a `release/<version>` PR.
   Nate merges it and pushes the `vX.Y.Z` tag, which publishes. Merging alone publishes
   nothing — if a `release/*` PR has been merged and `git tag -l v<version>` is empty,
   tell Nate.
3. **The app** picks up a release automatically (it reads `latest/manifest.json`). **The
   website** follows by itself too: quipsapp.com's `data-version-bump.yml` notices the new
   manifest and opens its own PR bumping `.data-version`.
