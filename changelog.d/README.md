One file per change, never an edit to `CHANGELOG.md`.

1. Add `changelog.d/<pr-or-branch>.<kind>.md`, for example `231.fixed.md` or `rig-clear-flags.added.md`. Kinds, in the order a release lists them: `added`, `changed`, `fixed`, `removed`, `docs`, `decision`.
2. The file is the entry exactly as it should read in the changelog: one bullet starting with `- `, wrapped as the rest of the changelog is, naming the PR and the decision it rests on.
3. A pull request that changes `src/`, `catalog/` or `docs/guides/` carries one (`tests/test_changelog.py` checks it in CI); `## Unreleased` in `CHANGELOG.md` only ever says "Nothing yet."
4. At release, `python3 scripts/changelog.py assemble --version vX.Y.Z --date YYYY-MM-DD` writes the section and deletes the fragments; `preview` shows what it would write.
5. Why: every pull request used to append to `## Unreleased` while `main` moved, and conflicted on that file alone. Two fragments never touch the same line.
