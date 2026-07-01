---
description: create a release PR (auto-detects previous tag)
---

# Release Automation

Automate the full release process: generate notes, update files, create branch, and open PR.

No arguments required - automatically detects the previous tag.

---

## Prerequisites

Verify we're on main and it's clean:

```bash
git checkout main
git pull
git status --short
```

If there are uncommitted changes, abort and ask the user to resolve them first.

Detect the previous tag:

```bash
PREV_TAG=$(git describe --tags --abbrev=0 2>/dev/null)
if [ -z "$PREV_TAG" ]; then
  echo "No previous tags found. This appears to be the first release."
  PREV_TAG="HEAD~100"  # Fallback to analyze recent history
fi
echo "Previous tag: $PREV_TAG"
```

## Step 1: Generate Release Notes

Run `/gen-release-notes ${PREV_TAG}` to:
1. Analyze commits since the previous tag
2. Categorize changes (Added, Changed, Fixed, Security, etc.)
3. Determine the next version number
4. Update `CHANGELOG.md` with the new version section
5. Update `pyproject.toml` with the new version
6. Regenerate `uv.lock` (`uv lock`) so its editable-root `amelia` entry tracks the new version

Bumping `pyproject.toml` invalidates `uv.lock`'s own entry (`name = "amelia"`, `source = { editable = "." }`), whose `version` still points at the previous release. `uv lock --check` runs first in `make check`, the pre-push hook, and CI (before any `uv run`/`uv sync` can silently re-lock), and FAILS on a drifted lock — so a stale lock can never merge.

**Do not proceed** until CHANGELOG.md, pyproject.toml, and uv.lock are updated.

## Step 2: Create Release Branch

After the files are updated, extract the version and create a branch:

```bash
# Extract version from pyproject.toml
VERSION=$(grep '^version = ' pyproject.toml | sed 's/version = "\(.*\)"/\1/')
echo "Creating release branch for version $VERSION"

# Create and checkout release branch
git checkout -b "chore/release-${VERSION}"
```

## Step 3: Commit Changes

Commit all updated version files:

```bash
git add CHANGELOG.md pyproject.toml amelia/__init__.py dashboard/package.json uv.lock
git commit -m "chore(release): bump version to ${VERSION}"
```

## Step 4: Push and Create PR

Push the branch and create a pull request:

```bash
git push -u origin "chore/release-${VERSION}"
```

Create the PR with this structure (adapt summary based on actual changes):

```bash
gh label create "release" --description "Release PR" --color "0E8A16" 2>/dev/null || true
gh pr create --label "release" --title "chore(release): ${VERSION}" --body "$(cat <<EOF
## Summary

- Bump version to ${VERSION}
- Update CHANGELOG.md with changes since ${PREV_TAG}

## Post-merge steps

After merging, run:
\`\`\`
/release-tag ${VERSION}
\`\`\`

---

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

## Step 5: Output Summary

After creating the PR, provide:

1. The PR URL
2. The version number
3. Post-merge instructions:

```text
Release PR created: <URL>

After the PR is merged, run:
  /release-tag ${VERSION}
```

## Error Handling

- If main has uncommitted changes: abort and notify user
- If no tags exist: treat as first release, analyze recent commits
- If no changes since tag: abort and notify user
- If PR creation fails: provide manual steps
