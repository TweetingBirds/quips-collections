---
name: add-collection
description: Create a brand-new Quips collection with its quotes and register it in the index. Use when the user wants to add, create, or start a new collection (e.g. "create a Friends collection", "add a new collection of JFK quotes"). Creates collections/<id>.json and adds the matching entry to collections.json.
---

# Add a new collection

This skill operates in the **quips-collections** repo (the public data repo, served from
`data.quipsapp.com`). Run it with this repo as the working directory.

A collection is two coordinated edits: a new `collections/<id>.json` file holding the full
quotes, and a new entry in the root `collections.json` index. Both must agree.

Quote-level mechanics — field shape, the verification bar, in-batch dedup, and id format —
are owned by the **`add-quotes`** skill. This skill does not restate them; it follows them,
and only covers what's unique to creating a collection: the collection metadata, the index
entry, and `previewQuotes`.

## Steps

1. **Gather the collection metadata.** Ask the user for anything missing:
   - `id` — kebab-case, also the filename (e.g. `how-i-met-your-mother`). Must not collide
     with an existing collection id / file in `collections/`.
   - `name` — display title (e.g. `How I Met Your Mother`).
   - `description` — one inviting sentence.
   - `author` — defaults to `Quips Editorial` unless told otherwise.
   - `category` — reuse an existing one when it fits: `Creativity`, `Inspiration`,
     `Literature`, `Movies`, `Philosophy`, `Technology`, `Television`, `Wellness`. Add a new
     one only if none fit.
   - `colorName` + `colorLightHex` + `colorDarkHex` — pick one token from the Quips
     Palette 2.0 (16 OKLCH tokens) and set the matching light/dark hex pair. All three
     fields are required, on both the file and the index entry. Pick the token whose hue
     fits the theme; the hex pair is fixed per token:

     | token | light | dark | token | light | dark |
     |-------|-------|------|-------|-------|------|
     | `rose` | `#E03063` | `#F66E89` | `sky` | `#1F9ED4` | `#45C2FC` |
     | `red` | `#E92528` | `#FA7064` | `blue` | `#116BDF` | `#4790FB` |
     | `orange` | `#E1791C` | `#FDA260` | `indigo` | `#494BEC` | `#6A7BF3` |
     | `amber` | `#E2A520` | `#FBB620` | `violet` | `#8839E9` | `#A174F0` |
     | `yellow` | `#F7E120` | `#DAC720` | `purple` | `#B632CA` | `#DE56F3` |
     | `lime` | `#9EDB2A` | `#9DDC21` | `magenta` | `#D72D97` | `#F762B7` |
     | `green` | `#27AE57` | `#2BD66A` | `gray` | `#8A8D90` | `#9CA0A3` |
     | `teal` | `#27A98A` | `#2BD1AA` | `cyan` | `#29ACB2` | `#2DD3DA` |

     Cross-platform clients render from the hex pair; iOS prefers `colorName`. Match an
     existing collection's token when the new one is thematically similar, for consistency.
   - `iconName` — an SF Symbol. Match an existing collection's when the theme is
     similar; `collections.json` shows what each one uses.

     **Pick from `schema/website-icons.json`.** Being a valid SF Symbol is
     necessary but not sufficient: quipsapp.com draws collections from its own
     inline-SVG set, and its build fails on an `iconName` it has no drawing for.
     That file mirrors the names the website can render, and
     `validate_collections.py` errors on anything outside it — so a bad icon is
     caught here, while you are writing the collection, rather than after release
     as a red `main` on the website.

     To use an icon that isn't in the list yet, the website has to learn it first:
     add the SVG to quipsapp.com's `js/icons.js`, let that deploy, then run
     `python3 scripts/refresh_website_icons.py` to pull the name into the mirror.
     The ordering is the point — a name is not usable until it is drawable.

2. **Choose a quote id prefix** — a short slug unique to the collection (e.g. `himym`,
   `seinfeld`, `marvel`). Quote ids follow the `add-quotes` format (`<prefix>-NNN`, zero-padded
   to 3 digits) starting at `001`. Check `collections/` for prefixes already in use and pick
   one that's free.

3. **Build the quotes following the `add-quotes` skill** — its field shape, its verification
   bar (`verified` requires *both* exact wording *and* a real primary source; aggregator sites
   establish neither; magnet names like Einstein/Twain/Lincoln get extra suspicion), its
   in-batch dedup, and its `notes` rules. Number ids from `<prefix>-001`.
   - Target ~30 quotes (existing collections run 25–40) unless the user specifies a count —
     but every quote still clears the verification bar. Don't pad to a number with shaky
     quotes; if you can't verify enough for a substantial collection, surface that rather than
     filling the gap.

4. **Create `collections/<id>.json`.** Match the shape of existing collection files (the block
   below is illustrative — if the real files carry other fields, match them):
   ```json
   {
     "id": "<id>",
     "name": "<name>",
     "description": "<description>",
     "author": "Quips Editorial",
     "colorName": "<colorName>",
     "colorLightHex": "<#RRGGBB>",
     "colorDarkHex": "<#RRGGBB>",
     "iconName": "<iconName>",
     "category": "<category>",
     "addedAt": "<today>T12:00:00Z",
     "lastUpdated": "<today>T12:00:00Z",
     "quotes": [ /* quote objects per the add-quotes skill, ids <prefix>-001, -002, … */ ]
   }
   ```
   - `addedAt` — **required** dataset-recency timestamp (see `add-quotes`). Every
     quote in a brand-new collection shares this same `<today>T12:00:00Z` value,
     since they all enter the dataset together.

5. **Add the index entry to `collections.json`** in the `collections` array (append, or place
   thematically). It mirrors the file plus index-only fields:
   ```json
   {
     "id": "<id>",
     "name": "<name>",
     "description": "<description>",
     "author": "Quips Editorial",
     "quoteCount": <number of quotes>,
     "previewQuotes": [
       "A short, punchy quote from the collection.",
       "A second representative quote."
     ],
     "colorName": "<colorName>",
     "colorLightHex": "<#RRGGBB>",
     "colorDarkHex": "<#RRGGBB>",
     "iconName": "<iconName>",
     "category": "<category>",
     "addedAt": "<today>T12:00:00Z",
     "lastUpdated": "<today>T12:00:00Z"
   }
   ```
   - `quoteCount` must equal the number of quotes in the collection file.
   - `colorName`, `colorLightHex`, `colorDarkHex` must match the collection file exactly.
   - `addedAt` must match the collection file's `addedAt` exactly.
   - `previewQuotes` — pick 2 of the most recognizable/short **verified** lines.
   - Bump the index's top-level `lastUpdated` to `<today>T12:00:00Z`.

6. **Refresh the index hashes.** Run `compute_hashes.py` to fill in the new entry's
   `contentHash` + `bytes` (and refresh any others) from the files on disk. These drive
   progressive downloads — clients re-fetch only collections whose hash changed — and CI
   rejects a stale index, so this is not optional:
   ```bash
   python3 scripts/compute_hashes.py
   ```

7. **Validate.** Run the shared validator as a full sweep — no `--collection` — so the
   cross-collection prefix-uniqueness check runs and catches a new collection that reuses an
   existing prefix. It also confirms both files parse, `quoteCount` matches the actual count,
   ids are unique and well-formed, required fields are present, and there's no duplicate quote
   text. Don't report success until it passes.
   ```bash
   python3 scripts/validate_collections.py --strict
   ```

8. **Publish.** A new collection reaches users only through a release — follow the
   **Publishing** section of the `add-quotes` skill. Use a **minor** version bump for a new
   collection (branch and PR, tag `vX.Y.Z` once merged, then bump `.data-version` in the
   quipsapp.com repo to ship to the website).

9. **Report** the new collection id, quote count, the released version, and any quotes marked
   `unverified` (with reason).
