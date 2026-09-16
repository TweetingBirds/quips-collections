#!/usr/bin/env python3
"""Report on per-quote tag usage across the collections. Stdlib only.

validate_collections.py answers "is every tag legal?". This answers the
question that actually decides whether the tagging is any good: "is the
vocabulary earning its keep?"

Three failure modes it is built to catch, none of which are schema errors:

  dead tags      Slugs nothing ever uses. Vocabulary that exists only to be
                 scrolled past when choosing a tag.
  over-broad     A slug on so many quotes it no longer narrows anything. If
                 "inspiration" is on a third of the corpus, it is a synonym for
                 "quote" and the quotes carrying it are not findable by it.
                 Judged per facet: 'tone' tags are *expected* to be broad --
                 a quarter of everything ever said is a one-liner -- and they
                 never lead, so they never drive an import. A 'theme' tag at
                 the same share is a real problem.
  drift          The same idea tagged one way early and another way late, which
                 shows up as two neighbouring slugs both in heavy use. Read the
                 histogram next to schema/tags.json's `useWhen` lines.
  disagreement   The *same quote*, present in two collections and tagged
                 differently in each. Unlike the others this is not a judgement
                 call: the batches were months apart, the text is identical, so
                 the tags should be too. It is the sharpest drift signal the
                 data can give, and it only appears once both copies are
                 tagged -- expect none early in a rollout.

Usage:
    tag_report.py [--root ROOT] [--collection ID] [--check]
                  [--max-share FRACTION] [--min-uses N] [--json]
                  [--next N]

    --next N      print the next N collections still needing tags, in
                  alphabetical order, and exit. This is how a batch picks its
                  work: what is left is *derived from the data* rather than
                  read from a stored cursor, so it cannot go stale the way a
                  hand-maintained pointer does (the same failure this repo
                  already guards against for collections.json hashes). A
                  partially tagged collection is listed first -- finishing one
                  beats starting another.

    --check       exit 1 if any threshold is breached (for a batch's own gate)
    --max-share   flag a theme/occasion tag used on more than this share of
                  tagged quotes (default 0.25)
    --max-tone-share
                  the same threshold for 'tone' tags, which are legitimately
                  broader (default 0.50)
    --min-uses    flag a tag used fewer than this many times (default 5), once
                  the sample is big enough for a low count to mean anything
    --json        machine-readable output instead of the text report

Exit 0 unless --check and a threshold was breached.
"""

import argparse
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict

TAGS_REL = os.path.join("schema", "tags.json")
# A low use count only means something once enough quotes have been tagged to
# give every slug a fair chance at appearing. Both gates have to pass: coverage
# catches "the rollout has not reached these collections yet", and the absolute
# floor catches a small scoped run -- in a 115-quote pilot at 97% coverage, 75
# of 153 slugs came in under 5 uses purely because the sample was tiny.
MIN_USES_AFTER_COVERAGE = 0.80
MIN_USES_AFTER_SAMPLE = 1000


def load_vocabulary(root):
    with open(os.path.join(root, TAGS_REL), encoding="utf-8") as f:
        entries = json.load(f)["tags"]
    return {e["slug"]: e for e in entries}


def text_key(content):
    """Fold quote text for cross-collection matching: case and punctuation.

    Deliberately exact on wording. Two collections often carry *different
    lengths* of the same passage -- one stops at "plowing up the ground", the
    other runs on to "rain without thunder and lightning" -- and those are
    different quotes a reader could reasonably tag differently. Only identical
    wording is held to identical tags.
    """
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", content.lower()).split())


def collect(root, only=None):
    """Walk the collection files, returning per-quote tag rows."""
    rows = []
    pattern = os.path.join(root, "collections", f"{only}.json" if only else "*.json")
    for path in sorted(glob.glob(pattern)):
        cid = os.path.basename(path)[:-5]
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        for q in data.get("quotes", []):
            # None and [] mean different things and must stay distinct:
            #   absent  -> the tagging pass has not reached this quote
            #   []      -> it was read and deliberately left untagged
            # Collapsing them would make a finished collection look unfinished
            # forever, and --next would keep handing it back.
            #
            # Anything else is malformed, which is validate_collections.py's
            # call to make; reporting it would be worse than ignoring it, since
            # a bare string iterates as characters and "humor" would enter the
            # histogram as five one-letter tags.
            tags = q.get("tags")
            rows.append((cid, q.get("id", "?"),
                         tags if isinstance(tags, list) else None,
                         q.get("content", "")))
    return rows


def build(rows, vocab):
    tagged = [r for r in rows if r[2]]
    uses = Counter(t for _, _, tags, _c in rows for t in (tags or []))
    # Leading tag only -- this is what bulk import actually applies, so a slug
    # that never leads is invisible on the path most users take.
    leads = Counter(tags[0] for _, _, tags, _c in rows if tags)
    # quotes, tagged, tag-applications, decided (tagged or deliberately empty)
    per_coll = defaultdict(lambda: [0, 0, 0, 0])
    for cid, _, tags, _c in rows:
        per_coll[cid][0] += 1
        per_coll[cid][1] += 1 if tags else 0
        per_coll[cid][2] += len(tags or [])
        per_coll[cid][3] += 1 if tags is not None else 0
    facet_hits = Counter()
    for _, _, tags, _c in rows:
        if not tags:
            continue
        for facet in {vocab[t]["facet"] for t in tags if t in vocab}:
            facet_hits[facet] += 1
    by_text = defaultdict(list)
    for cid, qid, tags, content in rows:
        if tags:
            by_text[text_key(content)].append((cid, qid, tuple(tags)))
    disagree = sorted(
        (sorted(v) for v in by_text.values()
         if len(v) > 1 and len({t for _, _, t in v}) > 1),
        key=lambda v: v[0],
    )

    return {
        "disagree": disagree,
        "quotes": len(rows),
        "tagged": len(tagged),
        "deliberately_untagged": sum(1 for _, _, t, _c in rows if t == []),
        "coverage": len(tagged) / len(rows) if rows else 0.0,
        "applications": sum(uses.values()),
        "mean_tags": sum(uses.values()) / len(tagged) if tagged else 0.0,
        "uses": uses,
        "leads": leads,
        "per_collection": dict(per_coll),
        "facet_hits": facet_hits,
    }


def main():
    ap = argparse.ArgumentParser(description="Report on Quips tag usage.")
    ap.add_argument("--root", default=".", help="repo root containing collections.json")
    ap.add_argument("--collection", help="report on this collection only")
    ap.add_argument("--check", action="store_true", help="exit 1 on a threshold breach")
    ap.add_argument("--max-share", type=float, default=0.25,
                    help="flag a theme/occasion tag on more than this share of tagged quotes")
    ap.add_argument("--max-tone-share", type=float, default=0.50,
                    help="the same threshold for 'tone' tags, which run broader (default 0.50)")
    ap.add_argument("--min-uses", type=int, default=5,
                    help="flag a tag used fewer than this many times (default 5)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--next", type=int, metavar="N",
                    help="print the next N collections needing tags, then exit")
    args = ap.parse_args()

    try:
        vocab = load_vocabulary(args.root)
    except (OSError, json.JSONDecodeError, KeyError) as e:
        print(f"[ERROR] cannot read {TAGS_REL}: {e}", file=sys.stderr)
        return 1

    rows = collect(args.root, args.collection)
    if not rows:
        print("[ERROR] no quotes found", file=sys.stderr)
        return 1
    st = build(rows, vocab)

    if args.next:
        pending = [
            (cid, n, dec) for cid, (n, _, _, dec) in sorted(st["per_collection"].items())
            if dec < n
        ]
        # Partially decided first: an interrupted collection is a loose end, and
        # leaving it half-done is how a quote gets missed for good.
        pending.sort(key=lambda r: (r[2] == 0, r[0]))
        for cid, n, dec in pending[: args.next]:
            print(f"{cid}\t{n - dec} undecided of {n}" + ("  (partial)" if dec else ""))
        if not pending:
            print("nothing pending — every collection is fully tagged")
        return 0

    unused = sorted(s for s in vocab if not st["uses"][s])

    def ceiling(slug):
        facet = vocab[slug]["facet"] if slug in vocab else "theme"
        return args.max_tone_share if facet == "tone" else args.max_share

    over = sorted(
        ((s, n) for s, n in st["uses"].items()
         if st["tagged"] and n / st["tagged"] > ceiling(s)),
        key=lambda kv: -kv[1],
    )
    ripe = st["coverage"] >= MIN_USES_AFTER_COVERAGE and st["tagged"] >= MIN_USES_AFTER_SAMPLE
    thin = sorted((s, n) for s, n in st["uses"].items() if 0 < n < args.min_uses) if ripe else []

    if args.json:
        json.dump({
            "quotes": st["quotes"], "tagged": st["tagged"], "coverage": round(st["coverage"], 4),
            "applications": st["applications"], "meanTags": round(st["mean_tags"], 2),
            "vocabulary": len(vocab), "vocabularyUsed": len(vocab) - len(unused),
            "unused": unused, "overBroad": [{"slug": s, "uses": n} for s, n in over],
            "thin": [{"slug": s, "uses": n} for s, n in thin],
            "disagree": [[{"collection": c, "id": q, "tags": list(t)} for c, q, t in g]
                         for g in st["disagree"]],
            "uses": dict(st["uses"].most_common()),
        }, sys.stdout, indent=2)
        sys.stdout.write("\n")
    else:
        pct = 100 * st["coverage"]
        print(f"{st['tagged']}/{st['quotes']} quotes tagged ({pct:.1f}%), "
              f"{st['applications']} tag applications, {st['mean_tags']:.2f} per tagged quote")
        used = len(vocab) - len(unused)
        print(f"vocabulary: {used}/{len(vocab)} slugs used ({100 * used / len(vocab):.0f}%)")
        if st["tagged"]:
            bits = ", ".join(
                f"{f} {100 * st['facet_hits'][f] / st['tagged']:.0f}%"
                for f in ("theme", "occasion", "tone")
            )
            print(f"tagged quotes carrying each facet: {bits}")

        if st["uses"]:
            print("\ntop 25 tags (uses / as leading tag):")
            for s, n in st["uses"].most_common(25):
                share = 100 * n / st["tagged"] if st["tagged"] else 0
                print(f"  {n:5d} {share:5.1f}%  lead {st['leads'][s]:4d}  {s}")

        if st["disagree"]:
            print(f"\n[FLAG] same quote, different tags in different collections "
                  f"({len(st['disagree'])}):")
            for group in st["disagree"]:
                for cid, qid, tags in group:
                    print(f"  {cid}/{qid}: {list(tags)}")
                print()

        if over:
            print(f"\n[FLAG] over-broad (>{100 * args.max_share:.0f}% of tagged quotes, "
                  f"or >{100 * args.max_tone_share:.0f}% for a tone tag):")
            for s, n in over:
                facet = vocab[s]["facet"] if s in vocab else "?"
                print(f"  {s} ({facet}): {n} ({100 * n / st['tagged']:.1f}%)")
        if unused:
            print(f"\n[FLAG] unused slugs ({len(unused)}):")
            print("  " + ", ".join(unused))
        if thin:
            print(f"\n[FLAG] used fewer than {args.min_uses} times:")
            print("  " + ", ".join(f"{s}({n})" for s, n in thin))
        elif not ripe:
            print(f"\n(thin-tag check held back until coverage reaches "
                  f"{100 * MIN_USES_AFTER_COVERAGE:.0f}% and {MIN_USES_AFTER_SAMPLE} "
                  f"quotes are tagged; now {100 * st['coverage']:.0f}%, {st['tagged']})")

        incomplete = sorted(
            (cid, v) for cid, v in st["per_collection"].items() if v[3] and v[3] < v[0]
        )
        if incomplete:
            print(f"\n[FLAG] partially tagged collections ({len(incomplete)}):")
            for cid, (n, _, _, dec) in incomplete:
                print(f"  {cid}: {dec}/{n} decided")

    # A disagreement always breaches: unlike a share threshold it is not a
    # judgement call, it is the same words tagged two ways.
    breached = bool(over or thin or st["disagree"])
    if args.check and breached:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
