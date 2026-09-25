#!/usr/bin/env python3
"""Generate search-index.json — every quote in the dataset, flattened into one
searchable document, plus the author roster derived from it.

The index exists because `collections.json` carries only two `previewQuotes` per
collection — 166 of 2,711 quotes, about 6%. A client searching what it already
has would miss the rest, and would return different results depending on which
collection files happened to be cached. One flat file makes quote- and
author-level search answerable offline, from a single fetch, with the same
results for everyone.

Each entry carries the field names the collection files use, so a consumer that
already decodes a collection quote can decode these with the same type. The
`sourceCollection` back-reference joins to `collections.json` for presentation
(name, colour, icon) — deliberately *not* duplicated here, so a palette or rename
change ships in the index alone and can't disagree with this file.

Standalone like the other generated feeds: NOT registered in collections.json and
outside collections/, because it reuses other collections' quote ids and text.
Deterministic output — re-running with unchanged data produces no diff. Stdlib only.

Usage: build_search_index.py [--root ROOT] [--out PATH]
"""

import argparse
import json
import math
import os
import re
import sys
import unicodedata

META = {
    "id": "search-index",
    "name": "Search Index",
    "author": "Quips Editorial",
    "generated": True,
}

# Quote fields copied into the index, in the order they appear in an entry.
# `content` and `authorName` are what searching actually matches; `source` is
# included because "Meditations" and "Star Wars" are things people type into a
# quote app's search field. `quoteDate` and `verificationStatus` let a result row
# render its date and its Verified marker without fetching the collection.
# `tags` lets a search for "eulogy" or "grief" find quotes whose text never says
# the word — the slugs, not display names; the app resolves those through
# tags.json like every other surface that shows a tag.
FIELDS = ("id", "content", "authorName", "source", "quoteDate", "verificationStatus", "tags")


# Collection tags: derived from the quotes' tags, never curated. A collection is
# what its quotes are about, so a hand-kept list could only drift from them.
#
# Only `theme` and `occasion` qualify. `tone` describes a quote's form (aphorism,
# one-liner, wit), and it runs through collections of every subject — as a
# collection tag, "aphorism" would match half the catalogue and say nothing.
COLLECTION_TAG_FACETS = {"theme", "occasion"}
# A tag must be on at least this share of the collection's tagged quotes, and on
# at least this many of them, before it can describe the whole collection.
COLLECTION_TAG_MIN_SHARE = 0.10
COLLECTION_TAG_MIN_QUOTES = 2
COLLECTION_TAG_LIMIT = 6


def collection_tags(quotes, facet_of, corpus_counts, corpus_tagged):
    """A collection's most characteristic tags, most characteristic first.

    Ranked by share × log(1 + lift): how much of the collection carries the tag,
    weighted by how much more often it appears here than across the corpus. Share
    alone ranks `courage` high everywhere; lift alone ranks a tag two quotes happen
    to carry. Ties break on slug, so regeneration is stable.
    """
    tagged = [q for q in quotes if q.get("tags")]
    if not tagged or not corpus_tagged:
        return []
    counts = {}
    for q in tagged:
        for slug in q["tags"]:
            counts[slug] = counts.get(slug, 0) + 1
    scored = []
    for slug, count in counts.items():
        share = count / len(tagged)
        if (facet_of.get(slug) not in COLLECTION_TAG_FACETS
                or count < COLLECTION_TAG_MIN_QUOTES
                or share < COLLECTION_TAG_MIN_SHARE):
            continue
        lift = share / (corpus_counts[slug] / corpus_tagged)
        scored.append((-share * math.log1p(lift), slug))
    scored.sort()
    return [slug for _, slug in scored[:COLLECTION_TAG_LIMIT]]


def author_key(name):
    """Fold an author name to a comparison key: case, accents, and punctuation.

    "C. S. Lewis" and "C.S. Lewis" are one person written two ways, and a roster
    that lists both — 36 quotes and 2 — reads as a bug in whatever renders it.
    Folding here groups them; the quote entries keep whatever spelling the
    collection file uses, because this file reports the data rather than editing it.
    """
    folded = unicodedata.normalize("NFKD", name).lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", folded).split())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=None, help="output path (default: <root>/search-index.json)")
    args = ap.parse_args()

    coll_dir = os.path.join(args.root, "collections")
    files = sorted(fn for fn in os.listdir(coll_dir) if fn.endswith(".json"))

    with open(os.path.join(args.root, "schema", "tags.json"), encoding="utf-8") as f:
        facet_of = {t["slug"]: t.get("facet") for t in json.load(f)["tags"]}

    entries = []
    newest = ""
    quotes_by_collection = {}
    for fn in files:
        data = json.load(open(os.path.join(coll_dir, fn), encoding="utf-8"))
        cid = data["id"]
        quotes_by_collection[cid] = data.get("quotes", [])
        for q in data.get("quotes", []):
            # Presence, not truthiness: `if q.get(f)` would also drop a field that
            # is present but empty, silently turning a data problem into a missing
            # key that no consumer can distinguish from "never published".
            entry = {f: q[f] for f in FIELDS if f in q}
            entry["sourceCollection"] = cid
            entries.append(entry)
            newest = max(newest, q.get("addedAt", ""))

    # Deterministic: by collection, then by quote id within it. Matches the order
    # a reader would find them in, and is stable across regenerations.
    entries.sort(key=lambda e: (e["sourceCollection"], e["id"]))

    # The author roster, derived rather than curated: an author is however the
    # quotes spell their `authorName`, grouped by ``author_key``. Counts are what a
    # search result needs to say "10 quotes across 9 collections" without scanning
    # the entries again.
    roster = {}
    for e in entries:
        name = e.get("authorName", "")
        if not name:
            continue
        rec = roster.setdefault(author_key(name), {"spellings": {}, "collections": set()})
        rec["spellings"][name] = rec["spellings"].get(name, 0) + 1
        rec["collections"].add(e["sourceCollection"])

    authors, collisions = [], []
    for rec in sorted(roster.values(), key=lambda r: min(r["spellings"])):
        # The dominant spelling wins the display name; ties break alphabetically so
        # the choice is stable across regenerations.
        ranked = sorted(rec["spellings"].items(), key=lambda kv: (-kv[1], kv[0]))
        name = ranked[0][0]
        entry = {
            "name": name,
            "quoteCount": sum(rec["spellings"].values()),
            "collectionCount": len(rec["collections"]),
        }
        if len(ranked) > 1:
            # Listed so a client can map a quote's raw `authorName` onto this entry
            # without reimplementing the folding above.
            entry["variants"] = sorted(n for n, _ in ranked[1:])
            collisions.append((name, entry["variants"]))
        authors.append(entry)
    authors.sort(key=lambda a: a["name"])

    corpus_counts, corpus_tagged = {}, 0
    for quotes in quotes_by_collection.values():
        for q in quotes:
            if q.get("tags"):
                corpus_tagged += 1
                for slug in q["tags"]:
                    corpus_counts[slug] = corpus_counts.get(slug, 0) + 1
    collections = []
    for cid in sorted(quotes_by_collection):
        tags = collection_tags(quotes_by_collection[cid], facet_of, corpus_counts, corpus_tagged)
        if tags:
            collections.append({"id": cid, "tags": tags})

    index = {
        **META,
        "description": (
            f"Every quote across the Quips collections ({len(entries)}), flattened for "
            "search, with the author roster and each collection's characteristic tags "
            "derived from them. Join back to "
            "collections.json on sourceCollection for presentation."
        ),
        "lastUpdated": newest,
        "quoteCount": len(entries),
        "authorCount": len(authors),
        "quotes": entries,
        "authors": authors,
        # Derived per-collection tags (see ``collection_tags``), so a search for
        # "grief" can find a collection whose name and description never say it.
        "collections": collections,
    }

    out = args.out or os.path.join(args.root, "search-index.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.write("\n")

    size = os.path.getsize(out)
    print(f"wrote {len(entries)} quote(s) and {len(authors)} author(s) to {out} "
          f"({size // 1024} KB)")
    # Reported rather than silently merged: a spelling collision is a fixable
    # inconsistency in the collection files, and the roster folding is a safety net
    # for consumers, not a reason to leave the data disagreeing with itself.
    for name, variants in collisions:
        print(f"  note: '{name}' also spelled {', '.join(repr(v) for v in variants)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
