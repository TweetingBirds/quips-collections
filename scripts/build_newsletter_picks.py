#!/usr/bin/env python3
"""Generate newsletter-picks.json — collection quotes that have been featured in
the Quote Unquote newsletter ("As seen in Quote Unquote").

Cross-references newsletter-issues.json against the collections: an issue's
quote is the collection quote its `quoteId` names, or, for an entry with no
`quoteId`, the one whose normalized text (lowercased, alphanumerics only)
contains the issue's or is contained by it. The id wins because it is the only
link for an issue that debunks a paraphrase (`paraphrasesQuoteId: true`): its
quote is the popular wording, and `quoteId` names the authentic line, which no
text match would find. quote-unquote's check_newsletter_sync.py verifies that
every other id's text matches. Matched collection quotes are emitted
with a `newsletterIssue` number and a `sourceCollection` back-reference. Not
every newsletter quote maps to a collection quote — many issues are about
misattributions/paraphrases with no verified entry in the dataset; those are
reported and skipped.

**Only issues with `status: "sent"` are eligible.** The log also carries the
backlog and the scheduled-but-unsent, and a quote badged "Quote Unquote #7" for
an issue no subscriber has received — and no reader can open — is a claim the
newsletter has not earned yet. Quote Unquote has not launched, so today this
feed is empty by construction.

When nothing qualifies the feed is **not written**, and any existing copy is
removed. An empty feed file is worse than an absent one: build_manifest.py lists
each feed only when its file exists, so absence propagates cleanly (the website
drops the shelf, the app drops the tile), whereas a file with `quotes: []` still
draws an empty "From Quote Unquote" tile in the app, which gates on the feed
being present rather than on it having contents.

Standalone like the other generated feeds: NOT registered in collections.json
and outside collections/. Deterministic output. Stdlib only.

Usage: build_newsletter_picks.py [--root ROOT] [--out PATH]
"""

import argparse
import json
import os
import re
import sys
import unicodedata

META = {
    "id": "newsletter-picks",
    "name": "Newsletter Picks",
    "author": "Quips Editorial",
    "colorName": "violet",
    "colorLightHex": "#8839E9",
    "colorDarkHex": "#A174F0",
    "iconName": "envelope.fill",
    "category": "Featured",
    "generated": True,
}


def normalize(text):
    text = unicodedata.normalize("NFKD", text).lower()
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text).split())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=".")
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    coll_dir = os.path.join(args.root, "collections")
    files = sorted(fn for fn in os.listdir(coll_dir) if fn.endswith(".json"))

    # (collection_id, quote, normalized_content) for every quote, and by id.
    quotes = []
    for fn in files:
        data = json.load(open(os.path.join(coll_dir, fn), encoding="utf-8"))
        for q in data.get("quotes", []):
            quotes.append((data["id"], q, normalize(q.get("content", ""))))
    by_id = {q.get("id"): (cid, q) for cid, q, _ in quotes if q.get("id")}

    with open(os.path.join(args.root, "newsletter-issues.json"), encoding="utf-8") as f:
        issues = json.load(f)

    out = args.out or os.path.join(args.root, "newsletter-picks.json")

    sent = [i for i in issues if i.get("status") == "sent"]
    if not sent:
        # Absent, not empty — see the module docstring.
        if os.path.exists(out):
            os.remove(out)
            print(f"no sent issues; removed {out}")
        else:
            print(f"no sent issues; wrote nothing (by design — {len(issues)} "
                  f"issue(s) still backlog/scheduled)")
        return 0

    picked, unmatched = [], []
    for p in sent:
        pn = normalize(p.get("quote", ""))
        match = by_id.get(p.get("quoteId")) or next((
            (cid, q) for cid, q, qn in quotes if pn and (pn in qn or qn in pn)
        ), None)
        if match:
            cid, q = match
            picked.append({**q, "sourceCollection": cid, "newsletterIssue": p.get("issueNumber")})
        else:
            unmatched.append(p.get("issueNumber"))

    # Deterministic: by issue number.
    picked.sort(key=lambda q: (q.get("newsletterIssue") or 0, q.get("id", "")))
    newest = max((q.get("addedAt", "") for q in picked), default="")

    collection = {
        **META,
        "description": (
            "Quotes from the collections that have been featured in the Quote "
            "Unquote newsletter, tagged with their issue number."
        ),
        "lastUpdated": newest,
        "quotes": picked,
    }

    with open(out, "w", encoding="utf-8") as f:
        json.dump(collection, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"wrote {len(picked)} matched quote(s) to {out}; "
          f"{len(unmatched)} issue(s) with no collection quote: {sorted(filter(None, unmatched))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
