# Release checklist

Steps for cutting a bg3forge release. Written for `0.1.0`; reuse for
every release.

## 1. Freshness

- [ ] `pytest` — all green
- [ ] Latest `main` GitHub Actions CI is green across the full OS/Python
      matrix and the zero-dependency job
- [ ] **Read the entire README top to bottom** against the current
      code. Examples and roadmaps update themselves during development;
      inventory sections (feature lists, project layout tree, extras
      table) drift silently. This step exists because they have before.
- [ ] `CHANGELOG.md`: move the version from "unreleased" to dated,
      confirm it covers everything `git log` since the last tag says
- [ ] Version in `pyproject.toml` and `src/bg3forge/__init__.py` agree

## 2. Retail validation (needs a machine with the game)

- [ ] `bg3forge doctor` — all ✓
- [ ] `bg3forge validate --max-issues 999` — exit 0
- [ ] `bg3forge benchmark` — no unexplained regression vs
      `docs/baseline.md`; update the baseline if the numbers moved for
      a known reason (new stages, new datasets)

## 3. Package

- [ ] `python -m build`
- [ ] `python -m twine check dist/*`
- [ ] Wheel contains only `bg3forge/**` (no tests, no docs):
      `python -m zipfile -l dist/bg3forge-<ver>-py3-none-any.whl`
- [ ] Fresh-venv smoke test:

      python -m venv /tmp/relcheck && /tmp/relcheck/bin/pip install dist/*.whl
      /tmp/relcheck/bin/bg3forge --version
      /tmp/relcheck/bin/python -c "from bg3forge import Game"

- [ ] The core install pulls **zero dependencies** (watch the pip output)

## 4. Publish

- [ ] Tag: `git tag v<ver> && git push origin v<ver>`
- [ ] Upload: `python -m twine upload dist/*` (or a GitHub Actions
      trusted-publisher workflow, preferred once configured)
- [ ] Verify: `pip install bg3forge==<ver>` from a clean venv
- [ ] GitHub release with the changelog section as the body

## 5. After

- [ ] Bump the version to the next `.dev0` in both places
- [ ] Start the next "unreleased" section in `CHANGELOG.md`
