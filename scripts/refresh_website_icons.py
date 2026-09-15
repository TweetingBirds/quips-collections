#!/usr/bin/env python3
"""Refresh (or verify) schema/website-icons.json from quipsapp.com.

An `iconName` is only useful if the website can draw it. The drawings live in
quipsapp.com's js/icons.js, which this repo cannot see, so a collection shipping
an unknown name used to clear every gate here and fail over there at deploy —
after the release, on their main, with the site left serving the previous build.

The website publishes the names it supports at /icons.json. This script mirrors
that list into schema/website-icons.json, where validate_collections.py checks
every collection's iconName against it. Mirrored rather than fetched at
validation time so validation stays offline, hermetic and stdlib-only: CI should
not go red because a website is briefly unreachable.

The mirror is therefore a cache, and a cache can go stale. --check reports that
without writing, so a scheduled job or a human can notice the website has added
icons this repo cannot yet use.

Ordering: a brand-new icon must land on the website first. Add the SVG there,
let it deploy, then refresh here — the name is not usable until it is drawable.

Usage:
    refresh_website_icons.py [--root ROOT] [--url URL] [--check]

    --root   repo root containing schema/ (default: .)
    --url    where to fetch the published names (default: the live site)
    --check  compare only; exit 1 if the mirror is stale. No writes.

Exit code 0 on success, 1 if --check finds drift or the fetch fails.
"""

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

DEFAULT_URL = "https://quipsapp.com/icons.json"
MIRROR_REL = os.path.join("schema", "website-icons.json")
TIMEOUT = 30
USER_AGENT = "quips-collections refresh_website_icons.py (+https://github.com/TweetingBirds/quips-collections)"

NOTE = (
    "Mirror of the iconName values quipsapp.com can render, from "
    "{url} (generated there from js/icons.js). "
    "Refresh with scripts/refresh_website_icons.py — do not hand-edit."
)


def fetch_names(url):
    """The names the website publishes, sorted and deduped."""
    # Identify ourselves. urllib's default "Python-urllib/x.y" is 403'd by the
    # edge in front of quipsapp.com, so the stock request never reaches the file.
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        payload = json.load(resp)
    names = payload.get("names")
    if not isinstance(names, list) or not names:
        raise ValueError(f"{url}: no non-empty 'names' list")
    if not all(isinstance(n, str) and n for n in names):
        raise ValueError(f"{url}: 'names' must be non-empty strings")
    return sorted(set(names))


def read_mirror(path):
    """The names currently mirrored, or None if there is no readable mirror."""
    try:
        with open(path, encoding="utf-8") as f:
            names = json.load(f).get("names")
    except (OSError, json.JSONDecodeError):
        return None
    return sorted(set(names)) if isinstance(names, list) else None


def write_mirror(path, names, url):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            {"note": NOTE.format(url=url), "source": url, "names": names},
            f,
            indent=2,
            ensure_ascii=False,
        )
        f.write("\n")


def main():
    ap = argparse.ArgumentParser(description="Refresh the website icon-name mirror.")
    ap.add_argument("--root", default=".", help="repo root containing schema/")
    ap.add_argument("--url", default=DEFAULT_URL, help="published icon names")
    ap.add_argument("--check", action="store_true", help="report drift; do not write")
    args = ap.parse_args()

    path = os.path.join(args.root, MIRROR_REL)

    try:
        published = fetch_names(args.url)
    except (urllib.error.URLError, ValueError, json.JSONDecodeError, TimeoutError) as e:
        print(f"[ERROR] could not fetch {args.url}: {e}", file=sys.stderr)
        return 1

    current = read_mirror(path)
    if current == published:
        print(f"ok — {MIRROR_REL} is current ({len(published)} names)")
        return 0

    added = sorted(set(published) - set(current or []))
    removed = sorted(set(current or []) - set(published))
    # Removals matter more than additions: an unused new icon is harmless, but a
    # name that disappeared from the website may still be in use here, which
    # validate_collections.py will now fail on.
    for n in added:
        print(f"  + {n}")
    for n in removed:
        print(f"  - {n}")

    if args.check:
        print(f"\n[ERROR] {MIRROR_REL} is stale: {len(added)} added, {len(removed)} removed")
        return 1

    write_mirror(path, published, args.url)
    print(f"\nwrote {MIRROR_REL} — {len(published)} names ({len(added)} added, {len(removed)} removed)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
