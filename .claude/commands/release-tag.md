---
description: tag and push a release after the release PR is merged
---

# Release Tag

Create and push a version tag after a release PR has been merged.

**Input**: Version number (e.g., `0.2.1`) - the `v` prefix is optional

```text
$ARGUMENTS
```

---

## Prerequisites

Verify the release PR is merged and we're ready to tag:

```bash
# Ensure we're on main with latest changes
git checkout main
git pull

# Extract version from input (strip 'v' prefix if present)
VERSION="${ARGUMENTS#v}"

# Verify all version files match (exit on first mismatch)
echo "Checking version consistency..."
grep -q "^version = \"${VERSION}\"" pyproject.toml || { echo "ERROR: pyproject.toml version mismatch"; exit 1; }
grep -q "__version__ = \"${VERSION}\"" amelia/__init__.py || { echo "ERROR: amelia/__init__.py version mismatch"; exit 1; }
grep -q "\"version\": \"${VERSION}\"" dashboard/package.json || { echo "ERROR: dashboard/package.json version mismatch"; exit 1; }
grep -q "\"version\": \"${VERSION}\"" docs/site/package.json || { echo "ERROR: docs/site/package.json version mismatch"; exit 1; }
echo "All versions match: ${VERSION}"
```

If any version doesn't match, the script aborts with an error. All version files must be in sync before tagging.

## Step 1: Verify CHANGELOG Entry

Confirm the version has a changelog entry:

```bash
grep "## \[${VERSION}\]" CHANGELOG.md
```

If no entry exists, abort - the release PR may not have been merged.

## Step 2: Check Tag Doesn't Exist

```bash
git tag -l "v${VERSION}"
```

If the tag already exists, inform the user and ask if they want to view the release instead.

## Step 3: Create Annotated Tag

Generate a brief summary from the CHANGELOG for the tag message:

```bash
# Extract the first category and its first item from this version's section
SUMMARY=$(sed -n "/## \[${VERSION}\]/,/## \[/p" CHANGELOG.md | grep "^- " | head -1 | sed 's/^- //')
```

Create the tag:

```bash
git tag -a "v${VERSION}" -m "Release v${VERSION} - ${SUMMARY}"
```

## Step 4: Push Tag

```bash
git push origin "v${VERSION}"
```

## Step 5: Confirm Release

After pushing, the GitHub Action will create the release. Provide the release URL:

```bash
# Get repo URL
REPO_URL=$(gh repo view --json url --jq '.url')
echo "Release will be available at: ${REPO_URL}/releases/tag/v${VERSION}"
```

Output:

```text
Tagged and pushed v${VERSION}

GitHub Action is creating the release at:
  ${REPO_URL}/releases/tag/v${VERSION}

To view the release once ready:
  gh release view v${VERSION}
```

## Error Handling

- If not on main: checkout main first
- If version not in pyproject.toml: abort, suggest running /release first
- If tag exists: show existing tag info, don't recreate
- If push fails: provide manual push command
