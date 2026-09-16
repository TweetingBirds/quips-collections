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

**There is no `.tag-state.json`.** The plan called for one, a sibling of
`.audit-state.json` carrying an order array and a cursor. Building the batch
selector made it a liability instead: a stored cursor is a second copy of
something the data already knows, and a second copy that goes stale silently is
the exact failure this repo has a rule about at the top of CLAUDE.md. The pilot
had already broken such a cursor anyway by tagging four collections out of
alphabetical order.

`tag_report.py --next N` derives the next batch from the data instead, and git
history is the run log. A collection is done when every quote has a `tags` key —
which is why the empty array matters:

- **no `tags` key** — the pass has not reached this quote
- **`"tags": []`** — it was read and deliberately left untagged

Without that distinction a collection with one un-taggable line looks unfinished
forever and `--next` keeps handing it back. Partially decided collections sort
first, because a half-done collection is how a quote gets missed for good.

**5 collections (~170 quotes) per PR — about 17 PRs.**

### Batch 1 (2026-09-15): andor-rogue-one, avatar-last-airbender, battlestar-galactica, bhagavad-gita, bible-wisdom

156/172 tagged, 16 deliberately empty, 3.35 tags per tagged quote, no
over-broad flags. Corpus-wide this took coverage to 269/2928 (9.2%) and
vocabulary use to **129/156 slugs (83%)**.

`sacrifice` added (v3) — `service` covers working for others' good, but not the
cost, and Luthen's "What is my sacrifice? Everything!" and Yangchen's "selfless
duty calls you to sacrifice" both forced the wrong tag.

The facet-aware ceiling proved itself: `aphorism` was 38% of the pilot and is
22.7% across the corpus, already under even the stricter theme ceiling. Judging
tone at 25% would have sent the pilot chasing a number that dilution fixes on
its own.

The 16 empties are concentrated in Avatar (11 of 47) — a comedy-heavy show where
"Drink cactus juice" and "That's rough, buddy" are famous for being memes, not
for having a subject. Fiction collections should expect this; `bhagavad-gita`
and `bible-wisdom` have none.

### Batch 2 (2026-09-15): bob-dylan, champions-mindset, childrens-literature, civic-life-democracy, civil-rights-voices

149/153 tagged, 4 empty, 3.21 tags per tagged quote, no over-broad flags.
Corpus: **418/2928 (14.3%)**, vocabulary **137/157 (87%)**.

`tag_report.py` gains a **disagreement check**: the same quote text present in
two collections and tagged differently in each. Unlike every other flag this is
not a judgement call — identical wording, tagged two ways, months apart — so it
always fails `--check`. Matching is deliberately exact on wording, because
collections often carry different *lengths* of one passage (Douglass stops at
"plowing up the ground" in `grit-perseverance` and runs on to "rain without
thunder and lightning" in `civil-rights-voices`), and those are different
quotes a reader could reasonably tag differently. There are 61 cross-collection
duplicate texts in the corpus and, at 14% coverage, no pair yet has both copies
tagged. The check earns its keep later; it exists now so no batch can introduce
a disagreement unnoticed.

No new tags this batch. `citizenship` was tempting across all 35 quotes of
`civic-life-democracy` and was deliberately not added: `service`, `politics` and
`community` already cover it between them, and a fourth slug overlapping three
existing ones is the drift the vocabulary exists to prevent.

Occasion coverage fell to 5% for this batch (corpus 12%), which is what these
five collections are — politics, sport and songwriting are not occasion-bearing.
`graduation` had its first real use, on the three *Oh, the Places You'll Go!*
quotes.

### Batch 3 (2026-09-15): cosmos-space, courage-conviction, creative-minds, cs-lewis, curiosity-discovery

159/160 tagged, 1 empty ("Let's go!"), 3.35 tags per tagged quote, no flags.
Corpus: **577/2928 (19.7%)**, vocabulary **141/157 (90%)**.

**The disagreement check earned its keep before it ever fired.** Two quotes in
`courage-conviction` — John Lewis on good trouble, and Douglass on power
conceding nothing — are word-for-word identical to quotes already tagged in
`civil-rights-voices`. Querying for that *before* tagging meant reusing the
existing tags rather than re-deriving them and landing somewhere adjacent. Run
it at the start of every batch, not just at the end:

```
python3 - <<'PY'   # batch quotes that duplicate an already-tagged quote
...matches on the same folded text tag_report.py uses...
PY
```

`courage-conviction` was the mono-tagging risk of this batch — 33 quotes about
one concept. `courage` lands on 16 of them, which is honest, but the lead tag
varies: `fear` leads FDR and Rosa Parks, `justice` leads Tutu and Burke,
`dissent` leads Malala and Anthony, `sacrifice` leads Nathan Hale. Leads are
what bulk import applies, so that variation is what keeps the collection from
importing as 33 copies of one tag.

`pride` and `envy`, both added during the pilot, finally paid off together on
Lewis's "Pride gets no pleasure out of having something, only out of having
more of it than the next man."

### Batch 4 (2026-09-15): dc-comics, dhammapada, disney-animated, dream-big, dystopian-fiction

145/176 tagged, **31 empty**, 3.30 per tagged quote, no flags.
Corpus: **722/2928 (24.7%)**, vocabulary **142/157 (90%)**.

The empty rate is the story, and it splits cleanly by *medium* rather than by
genre:

| collection | empty | |
|---|---|---|
| `disney-animated` | 21/52 | **40%** |
| `dc-comics` | 9/35 | 26% |
| `dystopian-fiction` | 1/30 | 3% |
| `dhammapada` | 0/30 | 0% |
| `dream-big` | 0/29 | 0% |

Animation and comics quote *catchphrases* — "Squirrel!", "No capes!", "Pull the
lever, Kronk!", "I'm Batman." — which are beloved and have no subject. Prose
dystopia quotes *sentences*, and scripture and aspiration quote *claims*; both
tag at essentially 100%.

This is worth knowing before the remaining film and television collections:
expect roughly a third of an animated or superhero collection to come back
empty, and do not read it as an incomplete pass. A user importing
`disney-animated` still gets its category tag on all 52.

Two Emperor's New Groove runs (`disney-042` through `disney-050`) are empty
nearly end to end. That is the correct outcome, not a gap.

### Batch 5 (2026-09-15): earth-and-the-wild, edgar-allan-poe, entrepreneurs, fantasy-worlds, first-lines

150/165 tagged, 15 empty, 3.25 per tagged quote, no flags.
Corpus: **872/2928 (29.8%)**, vocabulary **144/157 (92%)**.

Batch 4 concluded that the empty rate tracks medium. `first-lines` refines that:
it is prose, and still comes in at **9/40 empty (23%)**. The reason is a third
category the earlier batches had not produced — quotes famous for their
*position* rather than their content. "Stately, plump Buck Mulligan came from
the stairhead" and "Mrs. Dalloway said she would buy the flowers herself" are
celebrated openings that, standing alone, describe a man on a stair and an
errand. "Call me Ishmael." is three words.

So the rule is not "fiction tags badly". It is that a quote needs a subject, and
three different things can leave it without one: a catchphrase (`disney`), a
running gag (`dc-comics`), or a famous first sentence that is pure scene-setting.

`edgar-allan-poe` was the opposite worry — 31 poetry fragments, several of them
couplets — and tagged at 100% with no empties. Fragments of verse still have
subjects: grief, longing, mortality, time. `lyrical` lands on 19 of 31, which is
what the facet-aware tone ceiling exists to permit.

`entrepreneurs` at 29/29 is the case for having cut `entrepreneurship` from the
vocabulary in Phase 0: `money`, `risk`, `effort`, `competition`, `craft` and
`leadership` carried the whole collection between them, and the leads spread
across all six.

### Batch 6 (2026-09-15): founding-fathers, friendship, gratitude, great-economists, great-poems

**174/174 tagged — the first batch with no empties at all.** 3.22 per tagged
quote, no flags. Corpus: **1046/2928 (35.7%)**, vocabulary **145/157 (92%)**.

Zero empties is the clean confirmation of the batch 4/5 finding: all five are
prose or verse making claims, and a quote that makes a claim always has a
subject to tag. Nothing here is a catchphrase, a running gag, or scene-setting.

`friendship` (28) and `gratitude` (30) were the mono-tagging risks — whole
collections about one word. Both were handled by moving the lead off the obvious
tag wherever something more specific was available: `patience` leads "the wish
for friendship comes quickly, friendship does not", `solitude` leads Emerson on
seldom using his friends, `contentment` leads "Gratitude turns what we have into
enough". The collection's namesake tag stays present but rarely leads, which is
what keeps a bulk import from applying it 28 times.

**`eulogy` and `wedding` finally earned their place.** `great-poems` alone
carries five eulogy quotes (Dickinson's "Because I could not stop for Death",
Whitman's "O Captain! my Captain!", Rossetti's "Remember me", Thomas's "Do not
go gentle", Donne's "Death, be not proud") and two wedding ones (Burns's "red,
red rose", Browning's "How do I love thee"). Occasion coverage is still only 7%
corpus-wide, and that is correct — it is concentrated exactly where someone
would actually reach for it, which was the whole argument for the facet.

### Batch 7 (2026-09-15): great-scientists, great-speeches, hadith, hanukkah

131/131 tagged, zero empties, 3.20 per tagged quote, no flags.
Corpus: **1177/2928 (40.2%)**, vocabulary **146/157 (93%)**.

**The batch was split.** `--next 5` offered these four plus
`how-i-met-your-mother`, which is 97 quotes on its own and would have made a
228-quote PR. The batch rule is ~165 quotes; "5 collections" was only ever a
proxy for that. HIMYM goes in its own PR, which it deserves anyway as the
sharpest test of the theme-required rule so far.

`great-speeches` pushed `rallying-cry` to 16 of 36 quotes (44%) — the highest
single-tag share in any collection to date, and correct: it is a collection of
speeches meant to move people. It sits under the 50% tone ceiling, where a flat
25% bar would have flagged it. That ceiling has now justified itself twice, on
Poe's `lyrical` and here.

`hanukkah` needed care on one quote. "Weeping may tarry for the night, but joy
cometh in the morning" is the same psalm as `bible-wisdom`'s "Weeping may endure
for a night" — different translations, so the disagreement check treats them as
different quotes and would not have caught a divergence. Tagged identically
anyway. **The check only enforces exact wording; near-variants across
translations still need a human eye**, and scripture collections are full of
them.

### Batch 8 (2026-09-15): how-i-met-your-mother

**66/97 tagged, 31 empty (32%)**, 3.19 per tagged quote, no flags.
Corpus: **1243/2928 (42.5%)**, vocabulary **146/157 (93%)**.

The largest collection in the repo, taken alone because it is 97 quotes, and
the sharpest test of the theme-required rule. The result settles the question
the film/TV block was raising: **it tags fine.**

The empties are almost entirely Barney's catchphrases and running bits — "Suit
up!", "Challenge accepted.", "True story.", "Lawyered!", "Slap bet!", the Bro
Code, the Naked Man, the Cheerleader Effect, the Hot/Crazy Scale. These are the
same category as "No capes!" and behave the same way.

What is left is not thin. Ted's narration is written to be reflective, and
Lily, Robin and Marshall get the emotional load of the show: `destiny` lands
nine times, `change` eight, `marriage` nine. Two quotes take `wedding` —
"There are two big days in any love story" and "none of us can vow to be
perfect... all we can do is promise to love each other" — and both are lines
someone would genuinely read at one.

So a sitcom splits into a tagged two-thirds that is about love, aging and time,
and an untagged third that is catchphrases. That is the right split, and it
means the remaining film and television collections need no rule change.

### Batch 9 (2026-09-16): iconic-game-lines, inspiration-daily, jane-austen, jewish-wisdom, john-muir

140/164 tagged, 24 empty, 3.17 per tagged quote, no flags.
Corpus: **1383/2928 (47.2%)**, vocabulary **146/157 (93%)**.

**Every one of the 24 empties is in `iconic-game-lines`** — 24 of its 31 quotes,
77%, by far the highest rate in the project. The other four collections came in
at zero. "Zug zug", "Wololo", "All your base are belong to us", "You have died
of dysentery": this collection's *premise* is catchphrases, so the outcome is
correct rather than a failure.

It is also the one collection where the theme-required rule has a real cost. A
user who bulk-imports it gets the category tag on 31 quotes and almost nothing
else. Everywhere else the rule has been free — HIMYM still gave two thirds — so
this is a single-collection problem, not an argument for changing the rule.
Worth revisiting once at the end as a one-off: `humor` and `one-liner` on the
catchphrases would make them searchable without touching the standard anywhere
else.

Eight quotes were pre-matched against already-tagged duplicates, the most in any
batch, five of them in `inspiration-daily`. That collection is a greatest-hits
set, so overlap with `dream-big` and `grit-perseverance` is structural. Running
the duplicate query *before* tagging has now prevented eight chances to drift.

### Batch 10 (2026-09-16): johnny-cash, lds-general-conference, leadership-vision, legendary-coaches, lego-movies

152/167 tagged, 15 empty, 3.16 per tagged quote, no flags.
Corpus: **1535/2928 (52.4%) — past halfway**, vocabulary **147/157 (94%)**.

All 15 empties are in `lego-movies` (15/27, 56%), second only to
`iconic-game-lines`. Same cause: LEGO Batman's one-liners are gags, not claims.

`lds-general-conference` (56) and `leadership-vision` (30) were both
single-subject collections needing the treatment `friendship` and `gratitude`
got in batch 6 — keep the namesake tag present, move the **lead** off it.
`leadership` appears on 24 of 30 quotes but leads on only 12; the rest lead on
`humility`, `service`, `integrity`, `teaching`, `power`, `self-control`,
`effort`, `truth` and `longing`. Same for the LDS set: `faith` is everywhere,
but `failure`, `anger`, `home`, `parenthood`, `forgiveness`, `loneliness` and
`wonder` take the lead where they fit.

`johnny-cash` was the surprise — 25/25, and the densest `confession` collection
in the corpus (9 uses). Addiction, faith and self-knowledge in one voice.

**A process miss worth recording**: `leadership-vision` was initially skipped.
Four of the five collections were dumped and tagged and the fifth was missed
until the per-collection decided-count ran before committing, where it showed
`0/30`. Run that check *before* writing the commit message, not after.

### Batch 11 (2026-09-16): literary-classics, love-and-romance, marriage-and-weddings, marvel-movies, michael-jordan

154/175 tagged, 21 empty, 3.14 per tagged quote, no flags.
Corpus: **1689/2928 (57.7%)**, vocabulary **148/157 (94%)**.

**Ten quotes pre-matched against already-tagged duplicates, the most in any
batch** — seven of them in `literary-classics`, which like `inspiration-daily`
is a greatest-hits set. Its overlap runs against `first-lines`,
`fantasy-worlds`, `dystopian-fiction` and `dream-big` simultaneously. Two
collections in this corpus exist to re-present quotes that live elsewhere, and
both were caught by the same query.

**`marriage-and-weddings` is what the occasion facet was for.** `wedding` went
from 10 uses to 27 across this batch, and `anniversary` got its first two
(Browning's "Grow old along with me" and McLaughlin's "falling in love many
times, always with the same person"). Occasion coverage is still 7% corpus-wide
and still concentrated: `encouragement` 39, `wedding` 27, `hard-times` 19,
`eulogy` 19, then a long tail. That shape is right — these tags earn their place
by being precise, not by being frequent.

`michael-jordan` (52/52) is the densest `confession` collection in the corpus,
overtaking `johnny-cash`: it is assembled from interviews and memoir, so the
speaker is talking about himself in most of it. `envy` found another use on "A
lot of people try to pull you down to their level because they can't achieve
certain things."

`marvel-movies` came in at 18/40 empty (45%), between `dc-comics` (26%) and
`lego-movies` (56%). Superhero franchises cluster in that band because their
most-quoted lines are battle cries and callbacks — "Wakanda forever!", "Avengers,
assemble", "I am Groot" — while the reflective ones are few but real.

### Batch 12 (2026-09-16): mindfulness, money-investing, naruto, on-leadership, one-liners

142/146 tagged, 4 empty, 3.13 per tagged quote, no flags.
Corpus: **1831/2928 (62.5%)**, vocabulary **148/157 (94%)**.

**`one-liners` settles what "catchphrase" actually means.** It is a pure comedy
collection — Groucho Marx, Dorothy Parker, Will Rogers — and it tagged **27/27
with zero empties**, against `iconic-game-lines` at 77% empty.

The difference is not that one is funnier. A comedian's one-liner is *about*
something: "I worked myself up from nothing to a state of extreme poverty" is
about `money` and `success`; "Everybody is ignorant, only on different subjects"
is about `ignorance` and `humility`; "Take my wife... please" is about
`marriage`. A game catchphrase — "Zug zug", "Wololo" — is about nothing; it is a
sound the player recognises.

So the empty predictor is not medium, and not comedy. **It is whether the line
makes a claim.** Batches 4, 5, 8 and 9 each got closer to this; this batch is
where it is unambiguous. Every earlier finding restates as a special case:
catchphrases and running gags make no claim, scene-setting first sentences make
no claim, and jokes almost always do.

`naruto`'s four empties are "Believe it!", "Sorry I'm late. I got lost on the
path of life.", "The power of youth!" and "What a drag." — catchphrases in a
collection that is otherwise 22/26 reflective.

`on-leadership` overlapped `leadership-vision` on four quotes, caught by the
pre-check. Two leadership collections in one corpus will do that; both now carry
identical tags on the shared quotes.

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
