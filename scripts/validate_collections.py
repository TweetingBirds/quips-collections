#!/usr/bin/env python3
"""Validate the Quips collections data.

Single source of truth for the integrity checks the `add-quotes` and
`add-collection` skills rely on, and for CI. Stdlib only.

Checks (errors fail the run; warnings are reported but pass unless --strict):

  ERROR
    - collections.json and every collections/<id>.json parse as JSON
    - collections.json, each index entry and each collection file carry every
      field the shipped app's decoder requires, as the JSON type it demands
      (the APP_* tables below). The app drops a whole document over one
      missing, null or retyped value, for every installed copy, and only an
      app update repairs a copy already installed
    - fields the app decodes but does not require (contentHash, bytes,
      quoteDate, sourceType, …) have the right JSON type when they hold a value
    - no collection id is listed twice in the index
    - every entry of schema/tags.json, which is published to the app as it
      stands, has the string slug and displayName the app's decoder requires
    - every index entry has a matching file, and every file is in the index
    - index entry id matches its filename
    - quoteCount equals the actual number of quotes in the file
    - core fields agree between the index entry and the file
      (name, author, category, colorName, iconName)
    - quote ids are unique within a collection and match <prefix>-NNN (3+ digits)
    - all quotes in a collection share one prefix
    - each collection's prefix is unique across all collections (full run only)
    - every quote has the required fields, each of them a string, and a valid
      verificationStatus (verified, attributed, unverified, folk-wisdom)
    - sourceType, when present, is a known QuoteSourceType rawValue
      (speech, book, movie, podcast, …)
    - iconName is one the website can render, per schema/website-icons.json
      (skipped with a warning if that mirror is missing or unreadable)
    - colorName is a Palette 2.0 token and colorLightHex/colorDarkHex are that
      token's pair, on both the file and the index entry, per schema/palette.json
      (skipped with a warning if that mirror is missing or unreadable)
    - no duplicate quote text within a collection
    - the same quote text carries the same verificationStatus everywhere it
      appears, across every collection. Quotes are grouped by normalized text
      (see normalize_quote_text) and a group whose members disagree fails,
      unless it is on the checked-in list of known disagreements,
      schema/known-standing-disagreements.json. A listed group that no longer
      disagrees, or that gains a copy, fails too, so the list only shrinks.
      Under --collection only groups containing that collection are checked.
    - quote tags, when present, are known slugs from schema/tags.json, unique,
      at most MAX_TAGS_PER_QUOTE of them, and include at least one 'theme' tag
      (skipped with a warning if the vocabulary is missing or unreadable)
    - a quote has no `tags` key at all -- only under --require-tags. An empty
      `tags: []` passes: it records that the quote was read and deliberately
      left untagged (a catchphrase, a running gag, a line with no subject),
      which is a decision, not an omission.

  WARN
    - description differs between index entry and file
    - lastUpdated is not YYYY-MM-DDTHH:MM:SSZ
    - addedAt (collection index, collection file, or any quote) is missing or
      not YYYY-MM-DDTHH:MM:SSZ, or the index and file addedAt disagree
      (under --strict, i.e. in CI, these become errors — addedAt is required)
    - previewQuotes is not a list of 2 non-empty strings
    - quoteDate, when present, is not one of the accepted shapes
      (YYYY[-MM[-DD]], "c. YYYY", decade/year ranges, "c. N BCE/CE",
       "c. Nth century [BCE]")

Usage:
    validate_collections.py [--root ROOT] [--collection ID] [--strict]
                            [--require-tags]

    --root          repo root containing collections.json (default: .)
    --collection    validate only this collection + its index entry
                    (skips orphan and cross-collection prefix checks)
    --strict        treat warnings as errors (use in CI)
    --require-tags  error on any quote with no `tags` key, i.e. one the tagging
                    pass has not reached. An empty `tags: []` passes: absent
                    means "not looked at", [] means "looked at, deliberately
                    none", and only the first is a gap.

                    Off by default, and deliberately not a warning: CI runs
                    --strict, where a warning is a failure, so warning on
                    untagged quotes would redden main for the whole of a
                    multi-PR rollout. Turn it on in CI once every quote is
                    decided; scripts/tag_report.py tracks the gap until then.

Exit code 0 on success, 1 on failure.
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter

REQUIRED_QUOTE_FIELDS = {"id", "content", "authorName", "source", "verificationStatus", "notes"}
MIRRORED_FIELDS = ("name", "author", "category", "colorName", "iconName")
VALID_STATUS = {"verified", "attributed", "unverified", "folk-wisdom"}
# Optional per-quote source category. Mirrors QuoteSourceType.rawValue in the iOS
# app (QuotebookCore/.../Models/QuoteSourceType.swift) — keep in sync; values are
# additive only. Validated only when the field is present.
VALID_SOURCE_TYPES = {
    "unspecified", "inPerson", "book", "article", "newspaper", "magazine",
    "comic", "movie", "television", "podcast", "radio", "song", "speech",
    "interview", "website", "socialMedia", "video", "game", "letter", "poem",
    "play", "lecture", "documentary",
}
# What the shipped Quips app's decoders demand of the documents this script
# validates. The app decodes them with synthesized Codable and non-optional
# properties (PublicCollectionsResponse, PublicCollectionSummary,
# PublicCollectionDetail and PublicQuote, in the app repo's
# QuipsPublicCollections/Sources/QuipsPublicCollections/PublicCollectionModels.swift),
# so one missing, null or retyped value fails the WHOLE document for every
# installed copy, and nothing but an app update repairs a copy that is already
# installed. Keep these in sync with those types. A key may leave a REQUIRED
# table only once no app version still in use requires it.
#
# REQUIRED keys must be present, non-null and of the JSON type given. TYPED keys
# may be absent or null, but a value of the wrong type still throws in the app.
APP_INDEX_REQUIRED = {"version": str, "lastUpdated": str, "collections": list}
APP_ENTRY_REQUIRED = {
    "id": str, "name": str, "description": str, "author": str, "quoteCount": int,
    "previewQuotes": list, "colorName": str, "iconName": str, "category": str,
}
APP_ENTRY_TYPED = {"contentHash": str, "bytes": int, "addedAt": str, "lastUpdated": str}
# `quotes` is required too; validate_collection checks it on its own, because
# everything after it needs the list.
APP_FILE_REQUIRED = {
    "id": str, "name": str, "description": str, "author": str, "colorName": str,
    "iconName": str, "category": str, "lastUpdated": str,
}
# The quote fields the app decodes beyond REQUIRED_QUOTE_FIELDS. Its decoder
# tolerates a quote with none of them, and a null in any; what it cannot take is
# a year written as a number.
APP_QUOTE_TYPED = {
    "quoteDate": str, "authorDateOfBirth": str, "sourceType": str,
    "sourceCollection": str, "newsletterIssue": int,
}
# schema/tags.json is published verbatim as the app's tag vocabulary
# (TagVocabulary.Entry in the app repo). An entry without these fails the whole
# vocabulary, and imports then fall back to title-cased slugs.
APP_TAG_REQUIRED = {"slug": str, "displayName": str}
APP_TAG_TYPED = {"facet": str, "colorName": str}
# The app builds a collection's download URL and its deep link from the id, and
# refuses an id that is not this (isValidPublicID in the app's
# PublicCollectionsService+Validation.swift).
APP_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
JSON_TYPE_NAMES = {str: "a string", int: "an integer", list: "a list"}
# Mirror of the iconName values quipsapp.com can render. The drawings live in
# that repo's js/icons.js; only the names are mirrored here, because that is the
# whole constraint this side needs to enforce. Checked in rather than fetched so
# validation stays offline and stdlib-only; refresh with refresh_website_icons.py.
WEBSITE_ICONS_REL = os.path.join("schema", "website-icons.json")
# Mirror of the app's Palette 2.0: each colorName token and the light/dark hex
# pair the app derives from it (ColorTintOption.hexPair). Cross-platform clients
# render from the pair and iOS from the token, so a pair that drifts from its
# token shows a collection in two different colours depending on the device.
PALETTE_REL = os.path.join("schema", "palette.json")
# The cross-collection standing check's allowance for disagreements that were
# already in the data when the check arrived. See check_standing_agreement. The
# file may only ever lose entries: each one is a quote whose trust badge differs
# by collection, which is a defect waiting on editorial research, not a policy.
STANDING_EXCEPTIONS_REL = os.path.join("schema", "known-standing-disagreements.json")
# Controlled tag vocabulary. Tags are only worth having if two quotes in
# different collections land on the *same* one, so the set is closed and this
# file is the whole of it -- see its own "note" field.
TAGS_REL = os.path.join("schema", "tags.json")
# Mirrors the app's QuoteValidator.maxTagsPerQuote (8) minus the category tag
# import also applies, minus headroom for a user's own tags.
MAX_TAGS_PER_QUOTE = 6
ID_RE = re.compile(r"^[a-z0-9]+-\d{3,}$")
TS_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
# Accepts the date shapes actually used across the collections:
#   YYYY, YYYY-MM, YYYY-MM-DD
#   c. YYYY               c. 1969
#   c. YYYYs[-YYYYs]      c. 1950s, c. 1920s-1930s   (decade / decade range)
#   c. YYYY-YYYY          c. 2009-2014               (year range)
#   c. N[-N] BCE|CE       c. 500 BCE, c. 170-180 CE
#   c. Nth century [BCE]  c. 13th century, c. 6th century BCE
QUOTE_DATE_RE = re.compile(
    r"""^(
        \d{4}(-\d{2}(-\d{2})?)?
      | c\.\ \d{4}
      | c\.\ \d{4}s(-\d{4}s)?
      | c\.\ \d{4}-\d{4}
      | c\.\ \d{1,4}(-\d{1,4})?\ (BCE|CE)
      | c\.\ \d{1,2}(st|nd|rd|th)\ century(\ BCE)?
    )$""",
    re.VERBOSE,
)


class Report:
    def __init__(self):
        self.errors = []
        self.warnings = []

    def error(self, msg):
        self.errors.append(msg)

    def warn(self, msg):
        self.warnings.append(msg)


def load_json(path, rep):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        rep.error(f"missing file: {path}")
    except json.JSONDecodeError as e:
        rep.error(f"{path}: invalid JSON ({e})")
    return None


def decodes_as(value, expected):
    """Whether the app's decoder accepts `value` for a property of type `expected`."""
    if expected is int:
        # Swift's Int takes 3 and 3.0 and refuses 1.5, "3" and true. Python's
        # bool is an int, so it has to be turned away by name.
        if isinstance(value, bool):
            return False
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    return isinstance(value, expected)


def json_kind(value):
    """What a JSON value is, in the words a message needs."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "a boolean"
    if isinstance(value, (int, float)):
        return "a number"
    if isinstance(value, str):
        return "a string"
    if isinstance(value, list):
        return "a list"
    return "an object"


def check_app_fields(where, obj, required, typed, rep):
    """Report every key of `obj` the app could not decode.

    `where` opens each message and names the document: "collections.json:
    top-level", "<id>: index", "<id>: file", "<id>/<quote id>:".
    """
    for key, expected in required.items():
        value = obj.get(key)
        if value is None:
            state = "null" if key in obj else "missing"
            rep.error(
                f"{where} {key} is {state} — the app requires it and drops the whole "
                f"document without it"
            )
        elif not decodes_as(value, expected):
            rep.error(
                f"{where} {key} is {json_kind(value)} — the app decodes it as "
                f"{JSON_TYPE_NAMES[expected]} and drops the whole document otherwise"
            )
    for key, expected in typed.items():
        value = obj.get(key)
        if value is not None and not decodes_as(value, expected):
            rep.error(
                f"{where} {key} is {json_kind(value)} — when present the app decodes it "
                f"as {JSON_TYPE_NAMES[expected]} and drops the whole document otherwise"
            )


def load_website_icons(root, rep):
    """Names the website can render, or None if the mirror is unavailable.

    A missing mirror warns rather than errors: it makes the icon check
    unavailable, which is worth flagging, but it is not a defect in the data
    being validated.
    """
    path = os.path.join(root, WEBSITE_ICONS_REL)
    try:
        with open(path, encoding="utf-8") as f:
            names = json.load(f).get("names")
    except (OSError, json.JSONDecodeError) as e:
        rep.warn(f"{WEBSITE_ICONS_REL}: unreadable ({e}) — skipping the iconName check")
        return None
    if not isinstance(names, list) or not names:
        rep.warn(f"{WEBSITE_ICONS_REL}: no 'names' list — skipping the iconName check")
        return None
    return set(names)


def load_palette(root, rep):
    """{token: (light, dark)}, or None if the mirror is unavailable.

    Like the icon mirror, a missing file warns rather than errors: it disables
    the colour check rather than indicating bad data.
    """
    path = os.path.join(root, PALETTE_REL)
    try:
        with open(path, encoding="utf-8") as f:
            tokens = json.load(f).get("tokens")
    except (OSError, json.JSONDecodeError, AttributeError) as e:
        rep.warn(f"{PALETTE_REL}: unreadable ({e}) — skipping the colour check")
        return None
    if not isinstance(tokens, dict) or not tokens:
        rep.warn(f"{PALETTE_REL}: no 'tokens' object — skipping the colour check")
        return None
    return {name: (pair.get("light"), pair.get("dark")) for name, pair in tokens.items()
            if isinstance(pair, dict)}


def check_colour(where, obj, palette, rep):
    """colorName must be a palette token, and the hex pair must be that token's."""
    if palette is None or not isinstance(obj, dict):
        return
    name = obj.get("colorName")
    if name not in palette:
        rep.error(
            f"{where}: colorName {name!r} is not a Palette 2.0 token — pick one from {PALETTE_REL}"
        )
        return
    light, dark = palette[name]
    for key, expected in (("colorLightHex", light), ("colorDarkHex", dark)):
        actual = obj.get(key)
        if actual is None:
            rep.error(f"{where}: {key} is missing — {name!r} is {expected}")
        elif not isinstance(actual, str) or actual.upper() != expected.upper():
            rep.error(f"{where}: {key} {actual!r} is not {name!r}'s {expected} (see {PALETTE_REL})")


def load_tag_vocabulary(root, rep):
    """The tag vocabulary as (slugs, theme_slugs, avoid_map), or None.

    Unreadable warns rather than errors, for the same reason the icon mirror
    does: it makes a check unavailable, which is worth saying, but it is not a
    defect in the data under validation.

    `avoid_map` turns each tag's `avoid` list inside out, so a quote tagged
    "grit" is told to use "perseverance" instead of being told only that "grit"
    is unknown. Naming the replacement is the entire point -- a rollout spread
    over many PRs drifts precisely when a writer has to guess which near-synonym
    the vocabulary settled on.
    """
    path = os.path.join(root, TAGS_REL)
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f).get("tags")
    except (OSError, json.JSONDecodeError) as e:
        rep.warn(f"{TAGS_REL}: unreadable ({e}) - skipping the tag checks")
        return None
    if not isinstance(entries, list) or not entries:
        rep.warn(f"{TAGS_REL}: no 'tags' list - skipping the tag checks")
        return None

    slugs, themes, avoid_map = set(), set(), {}
    for position, e in enumerate(entries):
        if not isinstance(e, dict):
            rep.error(f"{TAGS_REL}: tag {position} is {json_kind(e)}, not an object")
            continue
        name = e.get("slug") if isinstance(e.get("slug"), str) else f"tag {position}"
        check_app_fields(f"{TAGS_REL}: {name}:", e, APP_TAG_REQUIRED, APP_TAG_TYPED, rep)
        slug = e.get("slug")
        if not slug or not isinstance(slug, str):
            continue
        slugs.add(slug)
        if e.get("facet") == "theme":
            themes.add(slug)
        for bad in e.get("avoid", []):
            avoid_map[bad] = slug
    return slugs, themes, avoid_map


def validate_quote_tags(cid, qid, tags, vocab, rep, require_tags):
    """Check one quote's `tags`. `vocab` is load_tag_vocabulary's triple."""
    slugs, themes, avoid_map = vocab

    if tags is None:
        if require_tags:
            rep.error(f"{cid}/{qid}: no 'tags' key — the tagging pass has not reached it")
        return
    if not isinstance(tags, list):
        rep.error(f"{cid}/{qid}: 'tags' is not a list")
        return
    if not all(isinstance(t, str) for t in tags):
        rep.error(f"{cid}/{qid}: 'tags' holds a value that is not a string")
        return
    # An empty list is a decision, not an omission, so --require-tags accepts
    # it. Treating [] as a gap would make the flag unusable: 343 quotes in this
    # corpus are catchphrases, running gags, scene-setting or context-dependent
    # answers, and none of them has a subject to tag.

    if len(tags) > MAX_TAGS_PER_QUOTE:
        rep.error(f"{cid}/{qid}: {len(tags)} tags (max {MAX_TAGS_PER_QUOTE})")
    dupes = sorted(t for t, n in Counter(tags).items() if n > 1)
    if dupes:
        rep.error(f"{cid}/{qid}: duplicate tags {dupes}")

    for t in tags:
        if t in slugs:
            continue
        if t in avoid_map:
            rep.error(f"{cid}/{qid}: tag {t!r} is a rejected spelling - use {avoid_map[t]!r}")
        else:
            rep.error(f"{cid}/{qid}: unknown tag {t!r} - add it to {TAGS_REL} or pick an existing slug")

    # A quote tagged only "humor" has not been tagged: tone and occasion say how
    # you would use it, never what it is about.
    if tags and not any(t in themes for t in tags):
        rep.error(f"{cid}/{qid}: no 'theme' tag among {tags}")


def has_quote_objects(data):
    """Whether `data` is a collection file whose quotes can be compared."""
    return (
        isinstance(data, dict)
        and isinstance(data.get("quotes"), list)
        and all(isinstance(q, dict) for q in data["quotes"])
    )


def prefix_of(quote_id):
    return quote_id.rsplit("-", 1)[0] if "-" in quote_id else quote_id


def validate_index_entry(cid, entry, rep, palette=None):
    """Check one index entry for what the app needs in order to decode it.

    Apart from validate_collection, whose index checks are comparisons with the
    file and so do not run when the file is missing or unreadable. The app
    decodes the index before it fetches any file, and one entry it cannot decode
    costs it the whole index.
    """
    check_app_fields(f"{cid}: index", entry, APP_ENTRY_REQUIRED, APP_ENTRY_TYPED, rep)
    if not APP_ID_RE.match(cid):
        rep.error(
            f"{cid}: index id is not one the app accepts "
            f"(letters, digits, '-' and '_', 100 at most)"
        )
    check_colour(f"{cid}: index", entry, palette, rep)
    preview = entry.get("previewQuotes")
    if isinstance(preview, list) and not all(isinstance(p, str) for p in preview):
        rep.error(
            f"{cid}: index previewQuotes holds a value that is not a string — the app "
            f"drops the whole index over one"
        )


def validate_collection(cid, data, entry, rep, icon_names=None, vocab=None, require_tags=False,
                        palette=None):
    """Validate one collection file against its index entry. Returns the
    collection's quote-id prefix (or None) for the cross-collection check."""
    if data is None:
        return None
    if not isinstance(data, dict):
        rep.error(f"{cid}: file is {json_kind(data)}, not a JSON object")
        return None

    check_app_fields(f"{cid}: file", data, APP_FILE_REQUIRED, {}, rep)

    if data.get("id") != cid:
        rep.error(f"{cid}: file id {data.get('id')!r} != filename")

    check_colour(f"{cid}: file", data, palette, rep)

    # The website renders from its own SVG set and fails its deploy on a name it
    # has no drawing for. Catching it here means a bad icon surfaces while the
    # collection is being written, not after it ships.
    if icon_names is not None and data.get("iconName") not in icon_names:
        rep.error(
            f"{cid}: iconName {data.get('iconName')!r} is not one the website can render — "
            f"pick one from {WEBSITE_ICONS_REL}, or add an SVG for it to quipsapp.com's "
            f"js/icons.js and refresh the mirror"
        )

    if vocab is not None and "tags" in data:
        ctags = data.get("tags")
        if not isinstance(ctags, list):
            rep.error(f"{cid}: collection 'tags' is not a list")
        else:
            unknown = sorted(t for t in ctags if t not in vocab[0])
            if unknown:
                rep.error(f"{cid}: unknown collection tags {unknown}")

    quotes = data.get("quotes")
    if not isinstance(quotes, list):
        rep.error(f"{cid}: 'quotes' is missing or not a list")
        return None

    if not all(isinstance(q, dict) for q in quotes):
        rep.error(f"{cid}: 'quotes' holds a value that is not an object")
        return None

    # An id that is not a string is reported with its quote below; here it
    # counts as missing, so the pattern checks are handed strings.
    ids = [q.get("id") if isinstance(q.get("id"), str) else "" for q in quotes]

    if entry is not None:
        if entry.get("quoteCount") != len(quotes):
            rep.error(f"{cid}: index quoteCount {entry.get('quoteCount')} != {len(quotes)} quotes")
        for field in MIRRORED_FIELDS:
            if entry.get(field) != data.get(field):
                rep.error(f"{cid}: index {field} {entry.get(field)!r} != file {data.get(field)!r}")
        if entry.get("description") != data.get("description"):
            rep.warn(f"{cid}: description differs between index and file")
        if not TS_RE.match(str(entry.get("lastUpdated", ""))):
            rep.warn(f"{cid}: index lastUpdated not YYYY-MM-DDTHH:MM:SSZ")
        if not TS_RE.match(str(entry.get("addedAt", ""))):
            rep.warn(f"{cid}: index addedAt missing or not YYYY-MM-DDTHH:MM:SSZ")
        elif entry.get("addedAt") != data.get("addedAt"):
            rep.warn(f"{cid}: index addedAt {entry.get('addedAt')!r} != file {data.get('addedAt')!r}")
        pq = entry.get("previewQuotes")
        if not (isinstance(pq, list) and len(pq) == 2 and all(isinstance(p, str) and p.strip() for p in pq)):
            rep.warn(f"{cid}: previewQuotes should be 2 non-empty strings")

    if not TS_RE.match(str(data.get("lastUpdated", ""))):
        rep.warn(f"{cid}: file lastUpdated not YYYY-MM-DDTHH:MM:SSZ")
    if not TS_RE.match(str(data.get("addedAt", ""))):
        rep.warn(f"{cid}: file addedAt missing or not YYYY-MM-DDTHH:MM:SSZ")

    dup_ids = sorted(i for i, n in Counter(ids).items() if n > 1)
    if dup_ids:
        rep.error(f"{cid}: duplicate quote ids {dup_ids}")

    bad_ids = sorted(i for i in ids if not ID_RE.match(i))
    if bad_ids:
        rep.error(f"{cid}: malformed quote ids {bad_ids}")

    prefixes = {prefix_of(i) for i in ids if ID_RE.match(i)}
    if len(prefixes) > 1:
        rep.error(f"{cid}: mixed id prefixes {sorted(prefixes)}")

    for q in quotes:
        qid = q.get("id", "?")
        missing = REQUIRED_QUOTE_FIELDS - q.keys()
        if missing:
            rep.error(f"{cid}/{qid}: missing fields {sorted(missing)}")
        for field in sorted(REQUIRED_QUOTE_FIELDS & q.keys()):
            if not isinstance(q[field], str):
                rep.error(f"{cid}/{qid}: {field} is {json_kind(q[field])}, not a string")
        check_app_fields(f"{cid}/{qid}:", q, {}, APP_QUOTE_TYPED, rep)
        status = q.get("verificationStatus")
        if not isinstance(status, str) or status not in VALID_STATUS:
            rep.error(f"{cid}/{qid}: invalid verificationStatus {status!r}")
        if "sourceType" in q:
            source_type = q.get("sourceType")
            if not isinstance(source_type, str) or source_type not in VALID_SOURCE_TYPES:
                rep.error(f"{cid}/{qid}: invalid sourceType {source_type!r}")
        if not str(q.get("content", "")).strip():
            rep.error(f"{cid}/{qid}: empty content")
        qd = q.get("quoteDate")
        if qd is not None and not QUOTE_DATE_RE.match(str(qd)):
            rep.warn(f"{cid}/{qid}: unrecognized quoteDate {qd!r}")
        if not TS_RE.match(str(q.get("addedAt", ""))):
            rep.warn(f"{cid}/{qid}: addedAt missing or not YYYY-MM-DDTHH:MM:SSZ")
        if vocab is not None:
            validate_quote_tags(cid, qid, q.get("tags"), vocab, rep, require_tags)

    texts = [str(q.get("content", "")).strip().lower() for q in quotes]
    dup_text = sorted(t for t, n in Counter(t for t in texts if t).items() if n > 1)
    if dup_text:
        rep.error(f"{cid}: {len(dup_text)} duplicate quote text(s) within collection")

    return next(iter(prefixes)) if len(prefixes) == 1 else None


def normalize_quote_text(text):
    """The key under which the same quote in two collections lands together.

    Case-folded, with every run of punctuation, symbols, spacing and line breaks
    collapsed to a single space. That covers curly versus straight quotes and
    apostrophes, dash and ellipsis spellings, surrounding quote marks, trailing
    punctuation, a semicolon where another copy has a comma, and verse set on
    separate lines versus the same lines run together. Letters, accents and
    digits are left alone, so two quotes collide only when their words are
    identical in order.
    """
    folded = unicodedata.normalize("NFKC", text).casefold()
    kept = "".join(c if unicodedata.category(c)[0] in "LMN" else " " for c in folded)
    return " ".join(kept.split())


def group_quotes_by_text(collections_by_id):
    """{normalized text: [(collection id, quote id, verificationStatus, authorName)]},
    only for texts that more than one quote carries.

    `collections_by_id` maps a collection id to its parsed file. A quote whose
    content or standing is unusable is left out; validate_collection reports it.
    """
    groups = {}
    for cid, data in collections_by_id.items():
        for q in data["quotes"]:
            content, status = q.get("content"), q.get("verificationStatus")
            if not isinstance(content, str) or not isinstance(status, str):
                continue
            key = normalize_quote_text(content)
            if key:
                groups.setdefault(key, []).append((cid, q.get("id", "?"), status, q.get("authorName")))
    return {k: sorted(v) for k, v in groups.items() if len(v) > 1}


def disagreeing_groups(groups):
    """The groups whose members do not all carry the same verificationStatus."""
    return {k: v for k, v in groups.items() if len({status for _, _, status, _ in v}) > 1}


def load_standing_exceptions(root, rep):
    """{normalized text: set of quote ids}, or None if the file is unreadable.

    A missing file is an empty list, so every disagreement is then reported
    rather than none. A file that exists but is malformed is an error and
    switches the check off: the errors it would otherwise produce are noise next
    to that one.
    """
    path = os.path.join(root, STANDING_EXCEPTIONS_REL)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            entries = json.load(f).get("groups")
    except (OSError, json.JSONDecodeError, AttributeError) as e:
        rep.error(f"{STANDING_EXCEPTIONS_REL}: unreadable ({e}) - skipping the standing check")
        return None
    if not isinstance(entries, list):
        rep.error(f"{STANDING_EXCEPTIONS_REL}: no 'groups' list - skipping the standing check")
        return None
    known = {}
    for position, e in enumerate(entries):
        quotes = e.get("quotes") if isinstance(e, dict) else None
        ids = {q.get("id") for q in quotes if isinstance(q, dict)} if isinstance(quotes, list) else set()
        if not isinstance(e, dict) or not isinstance(e.get("text"), str) or not ids or None in ids:
            rep.error(
                f"{STANDING_EXCEPTIONS_REL}: group {position} needs a 'text' string and a "
                f"'quotes' list of objects with an 'id'"
            )
            return None
        if normalize_quote_text(e["text"]) != e["text"]:
            rep.error(f"{STANDING_EXCEPTIONS_REL}: group {position} 'text' is not in normalized form")
            return None
        known[e["text"]] = ids
    return known


def describe_group(members):
    return ", ".join(f"{qid} ({cid}) {status}" for cid, qid, status, _ in members)


def check_standing_agreement(groups, known, rep, only_collection=None):
    """Quotes with the same text must carry the same verificationStatus.

    The app shows verificationStatus as a trust badge, so one line that is
    "verified" in one collection and "attributed" in another tells readers two
    things about the same words. Three outcomes are errors:

      - a group disagrees and is not in `known` (the rule proper);
      - a group in `known` no longer disagrees, or no longer exists, so its
        entry is stale and has to go;
      - a group in `known` has gained a copy, since an allowance covers the
        copies that existed when it was written and no others.

    `known` is {normalized text: ids}. With `only_collection`, only groups that
    include that collection are judged and stale entries are not reported, since
    a single-collection run cannot see whether the rest of the list still holds.
    """
    for key, members in sorted(disagreeing_groups(groups).items()):
        if only_collection and all(cid != only_collection for cid, *_ in members):
            continue
        if key not in known:
            rep.error(
                f"standing: the same quote carries different verificationStatus values - "
                f"{describe_group(members)}: {key[:80]!r}. Give every copy the same status "
                f"(settle it for all copies, not just one). Do not add it to "
                f"{STANDING_EXCEPTIONS_REL}, which only ever shrinks"
            )
            continue
        gained = sorted({qid for _, qid, _, _ in members} - known[key])
        if gained:
            rep.error(
                f"standing: {key[:80]!r} is on the known-disagreement list but has gained "
                f"{gained} - the allowance covers only the copies that were there when it was "
                f"written. Settle the group instead: {describe_group(members)}"
            )

    if only_collection:
        return
    disagreeing = disagreeing_groups(groups)
    for key in sorted(known):
        if key in disagreeing:
            continue
        if key in groups:
            reason = f"all its copies now agree ({describe_group(groups[key])})"
        else:
            reason = "no group of duplicate quotes matches it any more"
        rep.error(
            f"{STANDING_EXCEPTIONS_REL}: the entry for {key[:80]!r} is stale - {reason}. "
            f"Delete the entry"
        )


def main():
    ap = argparse.ArgumentParser(description="Validate Quips collections data.")
    ap.add_argument("--root", default=".", help="repo root containing collections.json")
    ap.add_argument("--collection", help="validate only this collection id")
    ap.add_argument("--strict", action="store_true", help="treat warnings as errors")
    ap.add_argument(
        "--require-tags",
        action="store_true",
        help="error on any quote with no 'tags' key; an empty [] is a decision and passes",
    )
    args = ap.parse_args()

    rep = Report()
    index_path = os.path.join(args.root, "collections.json")
    coll_dir = os.path.join(args.root, "collections")

    index = load_json(index_path, rep)
    if index is None:
        print("[ERROR] cannot read collections.json", file=sys.stderr)
        return 1

    if not isinstance(index, dict):
        print(f"[ERROR] collections.json is {json_kind(index)}, not a JSON object", file=sys.stderr)
        return 1

    check_app_fields("collections.json: top-level", index, APP_INDEX_REQUIRED, {}, rep)
    if not TS_RE.match(str(index.get("lastUpdated", ""))):
        rep.warn("collections.json: top-level lastUpdated not YYYY-MM-DDTHH:MM:SSZ")

    icon_names = load_website_icons(args.root, rep)
    palette = load_palette(args.root, rep)
    vocab = load_tag_vocabulary(args.root, rep)

    listed = index.get("collections")
    entries = {}
    for position, e in enumerate(listed if isinstance(listed, list) else []):
        if not isinstance(e, dict) or not isinstance(e.get("id"), str):
            rep.error(
                f"collections.json: entry {position} is not an object with a string id — "
                f"the app drops the whole index over one"
            )
            continue
        if e["id"] in entries:
            rep.error(f"{e['id']}: listed more than once in collections.json")
        entries[e["id"]] = e

    files = set()
    if os.path.isdir(coll_dir):
        files = {fn[:-5] for fn in os.listdir(coll_dir) if fn.endswith(".json")}

    if args.collection:
        targets = [args.collection]
        if args.collection not in entries:
            rep.error(f"{args.collection}: no entry in collections.json")
        if args.collection not in files:
            rep.error(f"{args.collection}: no file collections/{args.collection}.json")
    else:
        targets = sorted(entries.keys() | files)
        for cid in entries.keys() - files:
            rep.error(f"{cid}: in index but no collections/{cid}.json")
        for cid in files - entries.keys():
            rep.error(f"{cid}: file present but not in collections.json index")

    prefixes = {}
    loaded = {}
    for cid in targets:
        if cid in entries:
            validate_index_entry(cid, entries[cid], rep, palette)
        if cid not in files:
            continue
        data = load_json(os.path.join(coll_dir, f"{cid}.json"), rep)
        prefix = validate_collection(
            cid, data, entries.get(cid), rep, icon_names, vocab, args.require_tags, palette
        )
        if has_quote_objects(data):
            loaded[cid] = data
        if prefix:
            prefixes.setdefault(prefix, []).append(cid)

    if not args.collection:
        for prefix, owners in sorted(prefixes.items()):
            if len(owners) > 1:
                rep.error(f"prefix {prefix!r} used by multiple collections: {sorted(owners)}")

    # The standing rule compares quotes across collections, so a run scoped to
    # one collection still reads the others, quietly: their own problems are
    # not this run's to report.
    if args.collection:
        for cid in sorted(files - {args.collection}):
            try:
                with open(os.path.join(coll_dir, f"{cid}.json"), encoding="utf-8") as f:
                    data = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if has_quote_objects(data):
                loaded[cid] = data
    known = load_standing_exceptions(args.root, rep)
    if known is not None:
        groups = group_quotes_by_text(loaded)
        check_standing_agreement(groups, known, rep, args.collection)
        if not args.collection:
            print(
                f"standing: {len(groups)} duplicate-text group(s) across collections, "
                f"{len(disagreeing_groups(groups))} disagreeing, {len(known)} on the known list"
            )

    for msg in rep.errors:
        print(f"[ERROR] {msg}")
    for msg in rep.warnings:
        print(f"[WARN]  {msg}")

    n_coll = len([c for c in targets if c in files])
    print(f"\n{len(rep.errors)} error(s), {len(rep.warnings)} warning(s) across {n_coll} collection(s)")

    failed = bool(rep.errors) or (args.strict and bool(rep.warnings))
    if not failed:
        print("ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())