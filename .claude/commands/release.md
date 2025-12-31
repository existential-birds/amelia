---
description: create a release from the previous tag through PR creation
---

# Release Automation

Automate the full release process: generate notes, update files, create branch, and open PR.

**Input**: Previous tag (e.g., `v0.1.0`)

```text
$ARGUMENTS
```

---

## Prerequisites

Verify we're on main and it's clean:

```bash
git checkout main
git pull
git status --short
```

If there are uncommitted changes, abort and ask the user to resolve them first.

## Step 1: Generate Release Notes

Run `/gen-release-notes $ARGUMENTS` to:
1. Analyze commits since the previous tag
2. Categorize changes (Added, Changed, Fixed, Security, etc.)
3. Determine the next version number
4. Update `CHANGELOG.md` with the new version section
5. Update `pyproject.toml` with the new version

**Do not proceed** until CHANGELOG.md and pyproject.toml are updated.

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

Commit the updated files:

```bash
git add CHANGELOG.md pyproject.toml
git commit -m "chore(release): bump version to ${VERSION}"
```

## Step 4: Push and Create PR

Push the branch and create a pull request:

```bash
git push -u origin "chore/release-${VERSION}"
```

Create the PR with this structure (adapt summary based on actual changes):

```bash
gh pr create --title "chore(release): ${VERSION}" --body "$(cat <<'EOF'
## Summary

- Bump version to X.Y.Z
- Update CHANGELOG.md with changes since vPREV

## Post-merge steps

After merging:
```bash
git checkout main && git pull
git tag -a vX.Y.Z -m "Release vX.Y.Z - Brief summary"
git push origin vX.Y.Z
```

GitHub Action creates the release automatically from the tag.

---

Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

Add the `docs` label:

```bash
gh pr edit --add-label "docs"
```

## Step 5: Output Summary

After creating the PR, provide:

1. The PR URL
2. The version number
3. Post-merge instructions:

```text
Release PR created: <URL>

After the PR is merged, run:
  git checkout main && git pull
  git tag -a vX.Y.Z -m "Release vX.Y.Z - <summary>"
  git push origin vX.Y.Z

GitHub Action will create the release automatically.
```

## Error Handling

- If main has uncommitted changes: abort and notify user
- If tag doesn't exist: abort and list available tags
- If no changes since tag: abort and notify user
- If PR creation fails: provide manual steps
