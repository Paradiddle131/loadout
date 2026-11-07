---
name: image-cache
description: Shares Docker build layers and heavy images between cloud sessions through the owner's ghcr.io. Use when a repo's image build is slow on cloud, when a session pulls or pushes ghcr.io images, or when a heavy tool image should be prebuilt once.
---

# Image cache on ghcr.io

A cloud session starts with an empty Docker cache, so every image builds from scratch.
The owner's ghcr.io namespace is the shared cache: one session writes it, the next reads it.
`<owner>` and `<repo>` below are the GitHub owner and name of the repo being built, lower-cased (`git remote get-url origin`).

## Access

The egress proxy logs every ghcr.io request in as the owner (a token with `read:packages` and `write:packages`, injected as `Authorization: Bearer <base64 token>`).
Pull and push with plain `docker`; `GITHUB_TOKEN` and `GH_TOKEN` hold placeholders, so a `docker login` would only send the wrong credential.
Check it first: `curl -s -o /dev/null -w '%{http_code}' https://ghcr.io/v2/` answers `200`.
A `403` with `invalid token` means the environment's ghcr.io secret is wrong (a raw token instead of its base64): a `You:` item for the owner, not something to work around.

## Which shape

- **Layer cache** (the default, for an image the repo builds): BuildKit reads and writes the cache beside the build, so nobody pushes by hand and a changed input simply misses.
  Add to the repo's single build entry point, per image:
  `--cache-from type=registry,ref=ghcr.io/<owner>/<repo>/<image>:buildcache --cache-to type=registry,ref=ghcr.io/<owner>/<repo>/<image>:buildcache,mode=max,ignore-error=true`.
  `mode=max` keeps the builder stages of a multi-stage build; `ignore-error=true` keeps a failed cache write from failing the build.
  Turn it on by default where the proxy is (cloud) and leave it opt-in on a machine without it, which needs a `docker login ghcr.io` first.
  Give each image its own cache name: two images on one name overwrite each other's cache.
- **Prebuilt image** (a heavy tool or base the session runs but does not build): build it once, push an immutable version tag, and have consumers name the tag and its digest.
  A Dockerfile change means a new version tag, pushed from the session that made the change; an existing tag is never pushed over.

Cache what takes minutes: a build over a minute, or a pull every session repeats.
A cache write uploads every new layer, so a build that takes seconds gains nothing; a warm cache typically cuts a multi-image rebuild to a fraction of its cold time.

## Reference

- ghcr.io's billing terms for container storage and bandwidth are on [GitHub Packages billing](https://docs.github.com/en/billing/concepts/product-billing/github-packages); read them before caching tens of GB.
- New packages are private and belong to the owner's account; a repo-scoped name (`<repo>/<image>`) keeps them grouped.
- Builds that reach PyPI or npm also need the proxy's CA inside the build (cloud `CLAUDE.md`, Containers); the cache does not replace it.
