## What does this PR do?

<!-- One or two sentences. Link the issue it fixes: "Fixes #123" -->

## Checklist

- [ ] Tests pass locally (`pytest --no-cov`, with `QT_QPA_PLATFORM=offscreen` on macOS/Linux) — no new failures vs the baseline in CONTRIBUTING.md
- [ ] New/changed behavior is covered by a test
- [ ] `docs/FEATURE_REALITY.md` updated if user-visible behavior changed
- [ ] `CHANGELOG.md` updated under `[Unreleased]`
- [ ] Changed lines are clean under `black` + `ruff` (no mass reformatting of untouched files)
- [ ] Commits use Conventional Commits and are signed off (`git commit -s`, DCO)
- [ ] No new runtime dependencies, or the dependency was agreed in an issue first (no GPL deps — see docs/THIRD_PARTY.md)
