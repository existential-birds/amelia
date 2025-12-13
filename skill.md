---
name: hey-amelia
description: GitHub App bot for GitHub operations. Use when posting comments, creating PRs, creating issues, committing files, or responding to code review bots as the hey-amelia bot. Triggers on hey-amelia, bot respond, code review response, GitHub App comment, create PR, create issue, commit files.
---

# hey-amelia GitHub App

A GitHub App bot for Amelia to post comments and respond to code reviews.

## Status

**Not publicly available.** This app is currently private and installable only by the owner. Future releases may make it available for broader installation.

- **App URL**: https://github.com/apps/hey-amelia
- **App ID**: Configure in environment
- **Installation**: Private (owner-only)

## Configuration

Set these environment variables or create `~/.config/amelia/github-app.yaml`:

```bash
# Environment variables
export HEY_AMELIA_APP_ID="your-app-id"
export HEY_AMELIA_PRIVATE_KEY_PATH="$HOME/.config/amelia/hey-amelia.pem"
export HEY_AMELIA_INSTALLATION_ID="your-installation-id"
```

Or YAML config (`~/.config/amelia/github-app.yaml`):

```yaml
app_id: "123456"
private_key_path: "~/.config/amelia/hey-amelia.pem"
installation_id: "12345678"
```

## Usage

### Post a Comment as hey-amelia

Use the provided script to post comments authenticated as the GitHub App:

```bash
# Post a PR review comment reply
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "owner/repo" \
  --comment-id 123456789 \
  --body "Your response here"

# Post a general PR comment
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "owner/repo" \
  --pr 42 \
  --body "Your comment here"

# Post an issue comment
uv run python .claude/skills/hey-amelia/scripts/post_comment.py \
  --repo "owner/repo" \
  --issue 42 \
  --body "Your comment here"
```

### Supported Code Review Bots

The bot can respond to comments from these code review assistants:

| Bot | Login |
|-----|-------|
| CodeRabbit | `coderabbitai[bot]` |
| Gemini Code Assist | `gemini-code-assist[bot]` |
| Greptile | `greptile-apps[bot]` |
| GitHub Copilot | `copilot[bot]` |

## Authentication Flow

The script handles GitHub App authentication automatically:

1. Loads private key from configured path
2. Generates JWT signed with the private key
3. Exchanges JWT for installation access token
4. Uses installation token for API calls

Tokens are cached for their validity period (1 hour) to avoid unnecessary regeneration.

## Permissions

The hey-amelia app requires these permissions:

| Permission | Access | Purpose |
|------------|--------|---------|
| Contents | Read & Write | Read files, commit changes |
| Issues | Read & Write | Create issues, post comments |
| Pull requests | Read & Write | Create PRs, post comments, reply to reviews |
| Metadata | Read | Basic repository access |

## Commands

| Command | Description |
|---------|-------------|
| `/amelia:bot-respond` | Respond to all code review bot comments on current PR |
| `/amelia:bot-comment-pr` | Post a comment to the current PR |
| `/amelia:bot-comment-issue` | Post a comment to a GitHub issue |
| `/amelia:bot-create-pr` | Create a pull request |
| `/amelia:bot-create-issue` | Create a GitHub issue |
| `/amelia:bot-create-branch` | Create a Git branch |
| `/amelia:bot-commit` | Commit files to a branch |

## Skills

| Skill | Description |
|-------|-------------|
| [bot-comment-pr](bot-comment-pr.md) | Post general comments to pull requests |
| [bot-comment-issue](bot-comment-issue.md) | Post comments to GitHub issues |
| [bot-create-pr](bot-create-pr.md) | Create pull requests |
| [bot-create-issue](bot-create-issue.md) | Create GitHub issues |
| [bot-create-branch](bot-create-branch.md) | Create Git branches |
| [bot-commit](bot-commit.md) | Commit files to a branch |

## Script Reference

### `post_comment.py`

Post comments as the hey-amelia GitHub App.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `--repo` | Yes | Repository in `owner/repo` format |
| `--body` | Yes | Comment body text |
| `--comment-id` | No* | Reply to a specific review comment |
| `--pr` | No* | Post a general PR comment |
| `--issue` | No* | Post an issue comment |

*One of `--comment-id`, `--pr`, or `--issue` is required.

### `create_pr.py`

Create pull requests as the hey-amelia GitHub App.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `--repo` | Yes | Repository in `owner/repo` format |
| `--head` | Yes | Source branch (with changes) |
| `--base` | Yes | Target branch (to merge into) |
| `--title` | Yes | PR title |
| `--body` | Yes | PR description |
| `--draft` | No | Create as draft PR |

### `create_issue.py`

Create GitHub issues as the hey-amelia GitHub App.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `--repo` | Yes | Repository in `owner/repo` format |
| `--title` | Yes | Issue title |
| `--body` | Yes | Issue description |
| `--labels` | No | Comma-separated label names |
| `--assignees` | No | Comma-separated GitHub usernames |
| `--milestone` | No | Milestone number |

### `create_branch.py`

Create Git branches as the hey-amelia GitHub App.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `--repo` | Yes | Repository in `owner/repo` format |
| `--branch` | Yes | New branch name to create |
| `--base` | No | Base branch (default: repo's default branch) |
| `--sha` | No | Specific commit SHA (overrides --base) |

### `commit_files.py`

Commit files to a GitHub repository as the hey-amelia GitHub App.

**Arguments:**

| Argument | Required | Description |
|----------|----------|-------------|
| `--repo` | Yes | Repository in `owner/repo` format |
| `--branch` | Yes | Branch name to commit to |
| `--message` | Yes | Commit message |
| `--files` | Yes | Comma-separated local file paths |
| `--create-branch` | No | Create branch if it doesn't exist |
| `--author-name` | No | Commit author name |
| `--author-email` | No | Commit author email |

**Environment override:**

```bash
# Override config file location
HEY_AMELIA_CONFIG="path/to/config.yaml" uv run python ...
```
