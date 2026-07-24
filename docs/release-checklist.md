# Release checklist

Use this checklist for every BG3 Forge release. Prepare a release-candidate
pull request first; do not create the tag or GitHub release until the
automated and retail-install gates below pass.

## 1. Release candidate

- [ ] The release-candidate pull request is green across the full
      OS/Python matrix, the zero-dependency job, and the built-package job.
- [ ] **Read the entire README top to bottom** against the current code.
      Examples and roadmaps update during development; inventory sections
      such as feature lists, the project tree, and extras table can drift
      silently.
- [ ] Date the release section in `CHANGELOG.md` and reconcile it with
      every commit since the previous tag.
- [ ] Set the same final version in `pyproject.toml` and
      `src/bg3forge/__init__.py`.
- [ ] Review `docs/releases/<version>.md` as the user-facing GitHub,
      PyPI, and Nexus announcement.
- [ ] Confirm the release tag will be `v<version>`.

## 2. Retail validation

These checks require a machine with Baldur's Gate 3 installed:

```console
bg3forge doctor
bg3forge validate --max-issues 999
bg3forge benchmark
python scripts/build_data_release.py
```

- [ ] `doctor` reports all checks healthy.
- [ ] `validate` exits 0 with no unexplained issues.
- [ ] `benchmark` has no unexplained regression against
      `docs/baseline.md`; update the baseline for intentional changes.
- [ ] The data-release script produces
      `dist/bg3forge-data-<game-version>.zip`.
- [ ] The bundle's `MANIFEST.json` records the expected BG3 Forge
      version, retail game version, dataset counts, and successful coverage.

## 3. Package

CI's **Build and smoke-test distributions** job is the authoritative
package gate. It automatically:

- builds the sdist and wheel;
- runs `twine check`;
- confirms both source version declarations match the wheel metadata;
- rejects tests, docs, or other stray wheel contents;
- confirms the core package has zero required dependencies; and
- installs the wheel into a fresh virtual environment, then exercises the
  CLI and public Python API.

To reproduce the build locally:

```console
python -m pip install --upgrade build twine
python -m build
python -m twine check dist/*
python scripts/check_release_artifact.py dist/bg3forge-<version>-py3-none-any.whl
```

## 4. Publish

The repository publishes through `.github/workflows/publish.yml`. Its
build job has read-only repository access; only the separate publish job
can request an OIDC token, and no long-lived PyPI token is stored.

One-time setup, if it is not already configured:

- [ ] Create a protected GitHub environment named `pypi`.
- [ ] Register a PyPI trusted publisher with project `bg3forge`, owner
      `crazyace`, repository `bg3-forge`, workflow `publish.yml`, and
      environment `pypi`.

For every release:

- [ ] Merge the release-candidate pull request.
- [ ] Tag the exact merge commit:
      `git tag v<version> && git push origin v<version>`.
- [ ] Publish a GitHub release for that tag using
      `docs/releases/<version>.md` as its body. Publishing the release
      triggers the trusted-publisher workflow.
- [ ] Confirm the **Publish to PyPI** workflow built, checked, and uploaded
      both the sdist and wheel.
- [ ] Attach the retail data bundle:
      `gh release upload v<version> dist/bg3forge-data-<game-version>.zip`.
- [ ] Verify `pip install bg3forge==<version>` in a clean environment.
- [ ] Verify the GitHub release displays the Python distributions, data
      bundle, and final release notes.

## 5. Community announcement

- [ ] Reuse the user-focused release notes for Nexus and community posts.
- [ ] State clearly that BG3 Forge is a toolkit, not an in-game mod and not
      something to install through BG3 Mod Manager.
- [ ] Link the GitHub release, PyPI package, documentation, and patch-labeled
      data bundle.

## 6. After

- [ ] Bump both version declarations to the next `.dev0`.
- [ ] Start the next `unreleased` section in `CHANGELOG.md`.
