---
description: generate release notes for changes since a given tag
---

# Release Notes Generator

Generate professional release notes following the Keep a Changelog standard.

**Input**: Previous tag (e.g., `v0.0.1`)

```text
$ARGUMENTS
```

---

Use extended thinking to analyze the changes thoroughly before generating release notes.

## Step 1: Gather Changes

Run these commands to collect information about changes since the provided tag:

```bash
# Store the previous tag
PREV_TAG="$ARGUMENTS"

# Verify the tag exists
git tag -l "$PREV_TAG"

# Get the repo URL for PR links
git remote get-url origin

# List commits since last tag
git log ${PREV_TAG}..HEAD --pretty=format:"%h %s" --no-merges

# Get detailed diff stats
git diff ${PREV_TAG}..HEAD --stat

# List changed files by directory
git diff ${PREV_TAG}..HEAD --name-only | sort | uniq
```

Also gather PR information:

```bash
# Get merged PRs since the tag (requires gh CLI)
gh pr list --state merged --search "merged:>=$(git log -1 --format=%ci $PREV_TAG | cut -d' ' -f1)" --json number,title,author,labels
```

## Step 2: Analyze and Categorize

Categorize each change into exactly one of these groups (in this order):

| Category | Include | Exclude |
|----------|---------|---------|
| **Added** | New features, new public APIs, new CLI commands | Internal utilities not exposed to users |
| **Changed** | Modified behavior, performance improvements, updated dependencies with user impact | Refactors with no behavior change |
| **Deprecated** | Features marked for future removal | - |
| **Removed** | Deleted features, removed public APIs | Removed internal code |
| **Fixed** | Bug fixes, error handling improvements | Test-only fixes |
| **Security** | Vulnerability patches, security hardening | - |

**Exclude entirely:**
- CI/CD configuration changes (unless they affect users)
- Documentation-only changes (unless they reveal new features)
- Code style/formatting changes
- Test-only changes
- Internal refactors with no user-visible impact
- Merge commits

## Step 3: Determine Version Number

Based on the changes, suggest the next version following Semantic Versioning:
- **MAJOR** (X.0.0): Breaking changes to public API
- **MINOR** (x.Y.0): New features, backward-compatible
- **PATCH** (x.y.Z): Bug fixes only

Detect the tag format from existing tags (with or without `v` prefix).

Also check the current version in `pyproject.toml`:

```bash
grep '^version = ' pyproject.toml
```

## Step 4: Write Release Notes

Generate a `CHANGELOG.md` entry using this exact format:

```markdown
## [VERSION] - YYYY-MM-DD

### Added

- **scope:** Add new feature description ([#54](REPO_URL/pull/54))

### Changed

- **Breaking:** Rename `oldName()` to `newName()` for consistency ([#145](REPO_URL/pull/145))

  **Migration:** Replace all calls to `oldName()` with `newName()`.

### Deprecated

- **scope:** Deprecate `legacy_function()` in favor of `new_function()` ([#143](REPO_URL/pull/143))

### Removed

- **Breaking:** Remove deprecated `old_function()` ([#141](REPO_URL/pull/141))

### Fixed

- **scope:** Fix race condition when multiple workers access shared state ([#139](REPO_URL/pull/139))

### Security

- **deps:** Update vulnerable package to patched version ([#49](REPO_URL/pull/49))
```

### Writing Rules

**Format requirements:**
- Start every entry with an imperative verb: Add, Fix, Remove, Update, Improve, Rename, Deprecate, Patch
- Include scope prefix in bold when present: `**server:**`, `**cli:**`, `**api:**`
- One line per change (except breaking changes which get migration notes)
- Include PR/issue link at end of line
- Sort entries within each category by importance (most impactful first)
- Omit empty categories entirely

**Breaking changes:**
- Prefix with bold `**Breaking:**`
- List first within their category
- Add a `**Migration:**` block on the next line explaining exactly what users must change
- Include before/after code examples for API signature changes

**Tone:**
- Write for library consumers, not maintainers
- Focus on *what changed for users*, not *how it was implemented*
- Be specific—never write "various improvements" or "bug fixes"
- Each entry should be understandable without reading the PR

**Bad examples to avoid:**
```markdown
# BAD - Too vague
- Fixed bugs
- Performance improvements
- Updated dependencies

# BAD - Implementation-focused
- Refactored the internal state machine to use async/await

# BAD - Missing context
- Fixed #234
```

**Good examples to follow:**
```markdown
# GOOD - Specific and user-focused
- **server:** Fix timeout errors when processing files larger than 100MB ([#234](URL))
- **cli:** Add `--dry-run` flag to preview changes before execution ([#235](URL))
- **api:** Improve cold-start latency from 2.3s to 0.8s by lazy-loading plugins ([#236](URL))
```

## Step 5: Update CHANGELOG.md

1. Read the current `CHANGELOG.md`
2. Insert new version after the `## [Unreleased]` section
3. Add version comparison link at the bottom of the file

## Step 6: Update pyproject.toml

Update the version field in `pyproject.toml` to match the new version number.

## Step 7: Output Summary

After updating the files, provide:
1. The suggested version number with rationale
2. Summary of categorized changes
3. Any breaking changes that need special attention
4. Confirmation that CHANGELOG.md and pyproject.toml were updated
5. Next steps for the release:

```text
Next steps:
1. Review the CHANGELOG.md changes
2. Commit: git commit -am "chore(release): bump version to X.Y.Z"
3. Push branch and create PR
4. After PR merge, tag: git tag -a vX.Y.Z -m "Release vX.Y.Z - Summary"
5. Push tag: git push origin vX.Y.Z
6. GitHub Action will create the release automatically
```

## Conventional Commits Mapping

Map commit prefixes to changelog categories:

| Commit Prefix | Changelog Category |
|---------------|-------------------|
| `feat(scope):` | Added |
| `feat!(scope):` | Added (with Breaking prefix) |
| `fix(scope):` | Fixed |
| `perf(scope):` | Changed |
| `security(scope):` | Security |
| `refactor!:` | Changed (with Breaking prefix) |
| `docs:`, `chore:`, `ci:`, `test:`, `style:` | **Exclude** (unless user-facing) |
