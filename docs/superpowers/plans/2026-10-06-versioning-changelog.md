# Versioning and Changelog Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Adopt commitizen so every `generic-grader` release bumps the version and updates a generated `CHANGELOG.md` in one command, with conventional-commit enforcement.

**Architecture:** commitizen (`cz`) becomes the release tool. `[tool.commitizen]` in `pyproject.toml` configures the `uv` version provider (updates `pyproject.toml` + `uv.lock`), `v$version` tags, annotated tags, and `major_version_zero`. `make bump` wraps `cz bump --changelog`. A hand-curated `0.2.10` section seeds `CHANGELOG.md`; cz auto-generates from `0.2.11` onward. Enforcement is a CI job checking the PR title plus a local `commit-msg` pre-commit hook.

**Tech Stack:** Python 3.11+, uv, commitizen 4.19.1, pre-commit, GitHub Actions.

## Global Constraints

- commitizen version: **4.19.1** (dev dependency and pre-commit hook `rev: v4.19.1` must match).
- `version_provider = "uv"` — must update both `pyproject.toml` and `uv.lock`.
- `tag_format = "v$version"` and `annotated_tag = true` — must match existing `v0.2.9` tags.
- `major_version_zero = true` — at `0.x`, breaking changes bump MINOR, not MAJOR.
- `changelog_start_rev = "v0.2.10"` — cz generates from `0.2.11` onward.
- Do **not** set `update_changelog_on_bump = true`; the Makefile passes `--changelog` instead (see Task 3).
- Run all commands from the repo root `/home/john/Work/EBEC/generic-grader`.
- Use `uv`, never `pip`, for local installs.
- Pre-commit uses ruff 0.16.10; run `uv run ruff check --fix && uv run ruff format` before committing Python changes.

---

### Task 1: Add commitizen dependency and configuration

**Files:**
- Modify: `pyproject.toml` (dev extra, new `[tool.commitizen]` table)

**Interfaces:**
- Consumes: nothing.
- Produces: a working `uv run cz` command and the `[tool.commitizen]` config that Tasks 3, 4, 5, and 7 rely on.

- [ ] **Step 1: Add commitizen to the dev extra**

In `pyproject.toml`, find:

```toml
[project.optional-dependencies]
dev = ["build", "coverage", "pytest", "pytest-cov", "pre-commit>=3,<5", "twine"]
```

Replace with:

```toml
[project.optional-dependencies]
dev = ["build", "commitizen==4.19.1", "coverage", "pytest", "pytest-cov", "pre-commit>=3,<5", "twine"]
```

- [ ] **Step 2: Add the `[tool.commitizen]` table**

Append to the end of `pyproject.toml`:

```toml
[tool.commitizen]
version_provider = "uv"
tag_format = "v$version"
annotated_tag = true
major_version_zero = true
changelog_incremental = true
changelog_start_rev = "v0.2.10"
bump_message = "Bump version to $new_version"
```

Do **not** add a `name` key. It is only used by the `commitizen` version
provider; with `version_provider = "uv"` it makes cz look for an installed
package and fail with "The committer has not been found in the system."

- [ ] **Step 3: Sync the environment**

Run: `uv sync --extra dev`
Expected: commitizen installs; `uv.lock` updates to include it.

- [ ] **Step 4: Verify cz reads the config**

Run: `uv run cz version --project`
Expected: prints `0.2.9` (the current `project.version`).

- [ ] **Step 5: Verify the version provider is wired up**

Run: `uv run cz info`
Expected: output includes `version_provider: uv` and `tag_format: v$version`.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "build: add commitizen for versioning and changelog"
```

---

### Task 2: Seed CHANGELOG.md with the curated 0.2.10 section

**Files:**
- Create: `CHANGELOG.md`

**Interfaces:**
- Consumes: nothing.
- Produces: a `CHANGELOG.md` whose top section is `## 0.2.10`; Task 7's bump must not duplicate it.

- [ ] **Step 1: Create the changelog**

Create `CHANGELOG.md` with exactly:

```markdown
# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 0.2.10 (2026-10-06)

### Added

- Thread `rtol`/`atol` through `array_diff_details` for tolerance-aware array
  comparisons (#207).
- Support Python 3.14 in CI.

### Changed

- Allow trusted library operations during student imports (#200).
- Attribute library-origin security errors to the grader rather than the
  student.

### Fixed

- Select a non-interactive matplotlib backend at runtime to avoid cold-start
  timeouts (#205).
- Give `Options.expected_distribution` a per-instance default.
- Make the unclosed-file message deterministic.
- Fix test message checks that iterated over characters.
```

- [ ] **Step 2: Verify the file is well-formed Markdown**

Run: `uv run cz changelog --dry-run 2>&1 | head -5`
Expected: cz parses the existing changelog without error (it may print an
"Unreleased" or empty section; that is fine — the point is no parse error).

- [ ] **Step 3: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs: add changelog with curated 0.2.10 entry"
```

---

### Task 3: Point `make bump` at commitizen

**Files:**
- Modify: `Makefile:1-18`

**Interfaces:**
- Consumes: the `[tool.commitizen]` config from Task 1.
- Produces: a `bump` target that runs `cz bump --changelog`; `build` and `publish` unchanged.

- [ ] **Step 1: Replace the version variables and bump target**

The current `Makefile` starts with version-extraction variables used only by
`bump`. Replace the entire file's first 18 lines (everything from
`# Extract current version...` through the `bump` target's final `@echo`) with:

```makefile
bump:
	uv run cz bump --changelog
	@echo "Version bumped, changelog updated, committed, and tagged."
	@echo "Review with 'git log -1' then run 'make publish'."
```

Leave the `build` and `publish` targets exactly as they are:

```makefile
build:
	rm -rf dist/
	uv build

publish: build
	uv publish
	git push --follow-tags
```

- [ ] **Step 2: Verify the Makefile parses**

Run: `make -n bump`
Expected: prints `uv run cz bump --changelog` (dry-run of the recipe, no execution).

- [ ] **Step 3: Verify no stale version variables remain**

Run: `grep -nE 'VERSION|NEXT_PATCH' Makefile`
Expected: no output (all version-extraction variables removed).

- [ ] **Step 4: Commit**

```bash
git add Makefile
git commit -m "build: make bump run cz bump --changelog"
```

---

### Task 4: Add the local commit-msg pre-commit hook

**Files:**
- Modify: `.pre-commit-config.yaml`

**Interfaces:**
- Consumes: nothing.
- Produces: a `commitizen` commit-msg hook that validates local commit messages.

- [ ] **Step 1: Append the commitizen hook**

Append to `.pre-commit-config.yaml`:

```yaml
  - repo: https://github.com/commitizen-tools/commitizen
    rev: v4.19.1
    hooks:
      - id: commitizen
```

- [ ] **Step 2: Install the hook**

Run: `pre-commit install --hook-type commit-msg`
Expected: `pre-commit installed at .git/hooks/commit-msg`.

- [ ] **Step 3: Verify a conventional message passes**

Run: `uv run cz check --message "feat: add a thing"`
Expected: exit code 0, no error.

- [ ] **Step 4: Verify a non-conventional message fails**

Run: `uv run cz check --message "added a thing"`
Expected: non-zero exit code with a message that the commit does not match the
conventional-commit pattern.

- [ ] **Step 5: Commit**

```bash
git add .pre-commit-config.yaml
git commit -m "build: enforce conventional commits with commitizen hook"
```

---

### Task 5: Add the PR-title CI check

**Files:**
- Create: `.github/workflows/commitizen.yml`

**Interfaces:**
- Consumes: nothing.
- Produces: a `pr-title` CI job that fails when a PR title is not a valid conventional commit.

- [ ] **Step 1: Create the workflow**

Create `.github/workflows/commitizen.yml` with exactly:

```yaml
name: Check Commit Convention

on:
  pull_request:
    branches: ["main"]
    types: [opened, edited, synchronize, reopened]
  workflow_dispatch:

jobs:
  pr-title:
    runs-on: ubuntu-22.04
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.12.8"
      - name: Install commitizen
        run: pip install commitizen==4.19.1
      - name: Check PR title
        env:
          PR_TITLE: ${{ github.event.pull_request.title }}
        run: cz check --message "$PR_TITLE"
```

- [ ] **Step 2: Validate the YAML**

Run: `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/commitizen.yml').read_text()); print('ok')"`
Expected: prints `ok`.

- [ ] **Step 3: Verify the check command locally**

Run: `uv run cz check --message "fix: correct the thing"`
Expected: exit code 0.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/commitizen.yml
git commit -m "ci: check PR titles against conventional commits"
```

---

### Task 6: Document the release workflow in the README

**Files:**
- Modify: `README.md` (append a "Releasing" section after "Contributing")

**Interfaces:**
- Consumes: the workflow defined in Tasks 1-5.
- Produces: contributor-facing documentation.

- [ ] **Step 1: Append the Releasing section**

Append to the end of `README.md`:

```markdown
## Releasing

Releases are versioned and documented with
[commitizen](https://commitizen-tools.github.io/commitizen/). Commit messages
and pull request titles must follow the
[Conventional Commits](https://www.conventionalcommits.org/) format
(`feat:`, `fix:`, `docs:`, `build:`, `ci:`, `chore:`, ...). Because pull
requests are squash-merged, the **PR title** is what appears in the changelog;
a CI job checks it.

To cut a release:

1. Make sure `main` is up to date and the working tree is clean.
2. Run `make bump`. This bumps the version in `pyproject.toml` and `uv.lock`,
   prepends a new section to `CHANGELOG.md`, commits, and creates an annotated
   `vX.Y.Z` tag.
3. Review the commit and changelog with `git log -1` and `git show`.
4. Run `make publish` to build, upload to PyPI, and push the tag.

While the project is at `0.x`, breaking changes bump the minor version (for
example `0.2.10` to `0.3.0`) rather than the major version.
```

- [ ] **Step 2: Verify the section renders**

Run: `grep -n "## Releasing" README.md`
Expected: one match.

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "docs: document the commitizen release workflow"
```

---

### Task 7: Cut the 0.2.10 release

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (version), `CHANGELOG.md` (already has the section)

**Interfaces:**
- Consumes: all prior tasks.
- Produces: version `0.2.10`, an annotated tag `v0.2.10`, and a clean tree.

- [ ] **Step 1: Confirm the working tree is clean**

Run: `git status --porcelain`
Expected: no output.

- [ ] **Step 2: Dry-run the bump to confirm the target version**

Run: `uv run cz bump 0.2.10 --allow-no-commit --dry-run`
Expected: output shows `bump: version 0.2.9 → 0.2.10` and `tag to create: v0.2.10`.

- [ ] **Step 3: Perform the bump (no changelog generation)**

Run: `uv run cz bump 0.2.10 --allow-no-commit --yes`
Expected: version files updated, commit `Bump version to 0.2.10` created, tag
`v0.2.10` created. No new changelog section is generated (the curated one stays).

- [ ] **Step 4: Verify all three files changed and the tag exists**

Run: `git show --stat HEAD && git tag -l v0.2.10`
Expected: `pyproject.toml` and `uv.lock` in the stat; `v0.2.10` printed by the
tag command.

- [ ] **Step 5: Verify the changelog was not duplicated**

Run: `grep -c "^## 0.2.10" CHANGELOG.md`
Expected: `1`.

- [ ] **Step 6: Verify the tag is annotated**

Run: `git cat-file -t v0.2.10`
Expected: `tag` (not `commit`).

- [ ] **Step 7: Verify the version is consistent across files**

Run: `uv run cz bump --check-consistency --dry-run 2>&1 | head -3`
Expected: no consistency error (both `pyproject.toml` and `uv.lock` report
`0.2.10`).

- [ ] **Step 8: Run the test suite**

Run: `uv run pytest -q`
Expected: all tests pass (no runtime code changed).

- [ ] **Step 9: Push the release commit and tag**

Run: `git push --follow-tags`
Expected: `main` and `v0.2.10` pushed.

- [ ] **Step 10: Publish to PyPI**

Run: `make publish`
Expected: `dist/` built, package uploaded, tags pushed.

---

## Self-Review

**Spec coverage:**

- `[tool.commitizen]` config → Task 1. ✓
- `CHANGELOG.md` with curated 0.2.10 → Task 2. ✓
- `Makefile` bump wrapper → Task 3. ✓
- Local `commit-msg` hook → Task 4. ✓
- PR-title CI check → Task 5. ✓
- README "Releasing" section → Task 6. ✓
- 0.2.10 release → Task 7. ✓
- Error handling (no eligible commits, pre-commit retry, consistency) → Task 7
  uses `--allow-no-commit`; `--check-consistency` verified in Step 7. ✓

**Placeholder scan:** No TBD/TODO; every step has exact commands or file
content. ✓

**Type consistency:** `version_provider = "uv"`, `tag_format = "v$version"`,
`changelog_start_rev = "v0.2.10"`, and commitizen `4.19.1` are used identically
across Tasks 1, 4, 5, and 7. ✓

**Verified during planning:** the `[tool.commitizen]` config (without `name`)
was tested against the real repo with commitizen 4.19.1: `cz version --project`
returns `0.2.9`, and `cz bump --dry-run` reports `NO_COMMITS_TO_BUMP` (expected,
since the commits since `v0.2.9` are non-conventional). A manual `cz bump 0.2.10
--allow-no-commit` dry-run succeeds despite `major_version_zero = true`.

**Deviation from spec (intentional):** the spec's config block listed
`update_changelog_on_bump = true`; this plan omits it and passes `--changelog`
in the Makefile instead, so the one-time 0.2.10 bump does not emit an empty
auto-generated section. The spec was updated to match.
