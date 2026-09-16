# Plan: per-quote tags across the collection

Status: proposed, 2026-09-15. Not yet started.

## Why

Today a quote carries no tags at all — the key does not exist in
`schema/collection.schema.json` or in any `collections/<id>.json`. The only tag a
user ever sees from a public import is the **collection's category**, applied to
every quote in the file by `PublicCollectionBulkImporter`. Adding
`how-i-met-your-mother` tags 97 quotes "Television" and stops there.

There are 19 categories for 2,863 quotes. Tags are the only field that can say
what a quote is *about*, and the only one that can connect a Marcus Aurelius line
to a Michael Jordan line.

## The shape of the data

### `schema/tags.json` — a controlled vocabulary

Free-form tagging over 2,863 quotes produces `perseverance`, `persistence`,
`grit` and `determination` as four separate tags, which is the same as having
none: the entire value of a tag is that two quotes from different collections
land on it. So the vocabulary is a closed, validator-enforced list.

```json
{
  "version": 1,
  "tags": [
    {
      "slug": "perseverance",
      "displayName": "Perseverance",
      "facet": "theme",
      "colorName": "amber",
      "useWhen": "Continuing through difficulty over time. Not one brave act — that is courage."
    }
  ]
}
```

Four things each entry must carry, and why:

- **`slug`** is what the collection files reference. Lowercase, hyphenated,
  stable forever.
- **`displayName`** is what the app creates the tag as. Without it, an imported
  library mixes Title Case category tags ("Faith") with slugs
  ("present-moment"), which looks broken.
- **`colorName`** is a Palette 2.0 token. `TagHelper.findOrCreate` assigns a
  **random** color to each new tag; a bulk import that mints 40 tags otherwise
  produces 40 random colors.
- **`useWhen`** is a one-line gloss that draws the boundary against the nearest
  neighbouring tag. This is what keeps batch 2 and batch 14 tagging the same way
  — it is the single highest-value field in the file.

### Three facets

- **`theme`** (~100 tags) — what the quote is about. `courage`, `grief`,
  `ambition`, `mortality`, `friendship`, `doubt`, `craft`, `time`, `justice`,
  `wilderness`, `forgiveness`, `failure`, `curiosity`, `legacy`.
- **`occasion`** (~20 tags) — when you would reach for it. `wedding`, `eulogy`,
  `condolences`, `graduation`, `new-year`, `retirement`, `new-baby`,
  `farewell`, `toast`, `hard-times`, `encouragement`, `thank-you`. Nothing else
  in the record can express this, and it is what people actually open a quote
  app looking for.
- **`tone`** (~15 tags) — how it reads, and its form. `humor`, `satire`,
  `aphorism`, `one-liner`, `advice`, `warning`, `blessing`, `prayer`,
  `paradox`, `defiance`, `rallying-cry`, `tender`.

Deliberately excluded: author, source, work, era, category, and anything naming
the show or book. Those are already fields. A tag that restates a field is noise
in every list that renders tags.

### On the quote

```json
"tags": ["mortality", "acceptance", "aphorism", "eulogy"]
```

- **3–5 tags** is the target, **6** the hard cap in the validator. The app's
  `QuoteValidator.maxTagsPerQuote` is 8 and the category tag consumes one slot,
  so 6 leaves deliberate headroom for a user's own tags.
- **At least one `theme`** tag. A quote tagged only `humor` has not been tagged.
- **Ordered most-specific-first.** The ordering is the ranking: it is what lets
  bulk import take the top 2 and leave the rest for search. `["grief",
  "faith", "consolation", "condolences"]` — not alphabetical, not source order.

A collection may also carry a top-level `tags` array (its 5–8 most
characteristic tags). That serves a future browse-by-tag surface, not import.

## Phase 0 — contract first, no data touched

**Status: done, uncommitted.** One PR, no quote changes, validator green on the
fully untagged repo.

1. `schema/tags.json` — the vocabulary, drafted at ~135 tags.
2. `schema/collection.schema.json` — add `tags` to the quote definition:
   `array`, `maxItems: 6`, `uniqueItems: true`, items matching `^[a-z0-9-]+$`.
3. `scripts/validate_collections.py`:
   - unknown slug → **error**, and a slug on some tag's `avoid` list is told
     which tag to use instead
   - more than 6, or duplicates, or not a list → **error**
   - no `theme` tag on a quote that has tags → **error**
   - no `tags` at all → **silent**, unless `--require-tags` is passed.
     It cannot be a warning: CI runs `--strict`, where warnings *are* failures,
     so warning on untagged quotes would redden `main` for the whole rollout.
     Coverage is tracked by `tag_report.py` instead, and the flag goes into CI
     in the last batch's PR.
4. `scripts/tag_report.py` (new) — usage histogram, dead tags (0 uses),
   over-broad tags, thin tags, per-collection coverage, mean tags/quote, and
   facet coverage. `--check` exits 1 on a threshold breach so a batch can gate
   on it; `--json` for scripting.

## Phase 1 — pilot, 4 collections (115 quotes) — **done**

Chosen to break the vocabulary in four different ways:

| Collection | What it stresses |
|---|---|
| `mark-twain-wit` | tone/form tags, and whether `humor` swallows everything |
| `christian-saints` | the faith theme cluster, and `prayer`/`blessing` |
| `legend-of-zelda` | fiction — does it drift into describing the game? |
| `grit-perseverance` | the hard one: generic inspiration is where a vocabulary collapses to five tags |

Then run `tag_report.py` against the bar:

- ≥60% of the vocabulary used at least once
- no single tag on >25% of pilot quotes
- 30 hand-checked quotes read right

**Then revise the vocabulary.** This is the whole point of the pilot — expect to
add 10–20 tags and merge or kill several. Revising after batch 12 instead means
re-tagging twelve batches.

### Result (run 2026-09-15)

113/115 tagged, **3.77 tags per quote**, **108/156 slugs used (69%)**, theme on
100% of tagged quotes. Bar met.

What it changed:

- **Three tags added** (vocabulary v2): `shame`, `envy`, `pride`. Each was a
  real hole found by a quote that forced a wrong tag — Twain's "Man is the only
  animal that blushes" was tagged `sin`, a religious frame Twain would have
  enjoyed refusing; "the annoyance of a good example" was tagged `integrity`,
  which describes the exemplar rather than the envy the joke is actually about.
- **The glosses work.** `perseverance`/`resilience` co-occur at Jaccard 0.05 and
  `adversity`/`perseverance` at 0.04 in a collection *about* perseverance. That
  is the single most important number here: the near-synonym collapse the
  controlled vocabulary exists to prevent did not happen.
- **`aphorism` and `one-liner` are not redundant** (Jaccard 0.24, 14 of 59
  quotes carry both) — they were measured before being merged, and kept.
- **The over-broad check had to become facet-aware.** `aphorism` at 38% of
  pilot quotes read as a failure against a flat 25% ceiling, but tone tags are
  legitimately broad and never lead, so they never drive an import. Tone now
  has its own ceiling (50%); theme and occasion keep 25%, where the worst
  offender is `perseverance` at 13%.
- **The thin-tag check needed an absolute sample floor.** At 97% coverage of
  115 quotes it flagged 75 slugs as underused, all of them artifacts of a tiny
  sample. It now also waits for 1,000 tagged quotes.

Two findings that are not vocabulary problems:

- **Some quotes have no subject.** Zelda's "It's a secret to everybody" and
  "Hey! Listen!" are famous for being iconic, not for being about anything.
  They are left untagged rather than stretched onto a theme, and the
  theme-required rule is what surfaces them. Expect a handful per fiction
  collection; they still import with their category tag.
- **Occasion coverage is 17%**, which is fine — none of these four are
  occasion-bearing collections. `wedding`, `birthday`, `retirement` and friends
  stay unused until the pass reaches `marriage-and-weddings`, `friendship` and
  `gratitude`. Judge occasion coverage at corpus scale, not per batch.

## Phase 2 — full pass, batched and resumable

`.tag-state.json`, a sibling of `.audit-state.json`: same `order` array
(alphabetical collection ids), its own cursor, its own pass counter. Batches are
deterministic and a stopped run resumes where it left off.

**5 collections (~165 quotes) per PR — about 17 PRs.**

Per batch, in order:

```bash
python3 scripts/compute_hashes.py
python3 scripts/validate_collections.py --strict
python3 scripts/tag_report.py --since HEAD
```

The hash refresh is not optional: every batch edits collection files, which is
exactly the failure mode CLAUDE.md is written against. Note this repo's rule is
**branch and PR, never push to `main`** — the opposite of the app repo.

Each batch loads `schema/tags.json` with its `useWhen` glosses, and tags each
quote from its `content`, `source`, `notes`, and the collection it sits in.
Collection context is what disambiguates a Zelda line about courage from
Churchill on courage.

## Phase 3 — consuming the tags

All additive; already-shipped clients ignore an unknown `tags` key, because
`PublicQuote` decodes every field with `decodeIfPresent`. Data can land first.

1. **`PublicQuote`** (`QuotebookCore/.../PublicCollectionStorageModels.swift`) —
   add `public let tags: [String]?`, a `CodingKey`, and a `decodeIfPresent` line.
2. **Slug resolution** — ship `tags.json` in the app (or fetch it) so slugs
   become display names and canonical colors. Without this step imports land as
   lowercase-hyphenated tags in random colors.
3. **`PublicCollectionBulkImporter`** — category tag plus the **first 2** ranked
   tags per quote, deduped against the category, capped at `maxTagsPerQuote`.
4. **`ImportPublicQuoteSheet`** — category plus **all** the quote's tags. A
   deliberate one-quote save should get the rich set.
5. **`scripts/build_search_index.py`** — add `tags` to `FIELDS`, so Discover
   search matches "eulogy". `search-index.json` is already 1.1 MB; measure the
   growth.
6. Later, optionally: browse-by-tag in Discover, which is the surface that makes
   the occasion tags pay off.

Data ships as patch releases per CONTRIBUTING; the app change is a minor.

## What will go wrong

1. **Vocabulary drift across 17 batches.** The `useWhen` glosses are the
   mitigation, plus `tag_report.py` run against the whole repo each batch, not
   just the diff.
2. **Fiction collections drift into describing the work.** A Naruto line gets
   tagged `ninja`. Tags describe the quote, not its source.
3. **Inspiration collections flatten.** Everything becomes `hope, courage,
   perseverance`. The over-broad check in the report is aimed squarely at this.
4. **Occasion tags are a claim.** `wedding` on a line nobody would actually read
   at a wedding is worse than no tag at all. The bar is use, not topic.
5. **Stale hashes.** See CLAUDE.md. Every batch, every time.
