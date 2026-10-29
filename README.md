# Quips Collections

The public quote collections that power [Quips](https://quipsapp.com) — the
website and the iOS/macOS app.

Each collection is a curated, source-cited set of quotes. This repo is the
single source of truth for that data; the app and website consume it from
versioned releases.

## Layout

```
collections.json          Index of all collections (metadata + preview quotes)
collections/<id>.json     One file per collection, containing its quotes
schema/                   JSON Schema for the index and collection files
scripts/                  Validation + release tooling (stdlib Python only)
changelogs/               One file per released version, plus unreleased/ fragments
```

## Consuming the data

Releases are published to a CDN-backed custom domain, **`data.quipsapp.com`**.

- **Latest pointer** (short cache, names the current version):
  `https://data.quipsapp.com/latest/manifest.json`
- **Pinned, immutable assets** for a version `X.Y.Z`:
  - Index: `https://data.quipsapp.com/vX.Y.Z/collections.json`
  - Collection: `https://data.quipsapp.com/vX.Y.Z/collections/<id>.json`
  - Offline bundle: `https://data.quipsapp.com/vX.Y.Z/quips-collections-vX.Y.Z.zip`

The same assets are attached to each [GitHub Release](../../releases).

Recommended pattern: read `latest/manifest.json`, then pin and fetch the
`vX.Y.Z` assets it names. Pinned assets never change, so they cache forever.

## Releasing

A release is cut by pushing a semver tag:

```sh
git tag v1.2.0
git push origin v1.2.0
```

`.github/workflows/release.yml` then validates the data, builds the bundle and
`manifest.json`, creates the GitHub Release with `changelogs/<version>.md` as its
notes, and uploads everything to R2 behind `data.quipsapp.com`. A tag with no notes
file is refused before anything is published. The versioning scheme is in
[`changelogs/README.md`](changelogs/README.md).

## License

Quote text is the work of its respective authors and rights holders; inclusion
here is not a claim of ownership over the underlying quotations. The
**compilation, curation, metadata, and source notes** in this repository are
licensed under [CC BY 4.0](LICENSE). Attribution: "Quips Collections —
quipsapp.com".

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the data format and validation rules.
