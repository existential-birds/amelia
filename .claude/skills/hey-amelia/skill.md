---
name: hey-amelia
description: GitHub App bot for responding to code review comments. Use when posting comments as the hey-amelia bot, responding to code review bots (coderabbit, gemini-code-assist, greptile), or authenticating as the GitHub App. Triggers on hey-amelia, bot respond, code review response, GitHub App comment.
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
| Contents | Read | Read repository files |
| Issues | Read & Write | Post issue comments |
| Pull requests | Read & Write | Post PR comments, reply to reviews |
| Metadata | Read | Basic repository access |

## Commands

| Command | Description |
|---------|-------------|
| `/amelia:bot-respond` | Respond to all code review bot comments on current PR |
| `/amelia:bot-comment-pr` | Post a comment to the current PR |
| `/amelia:bot-comment-issue` | Post a comment to a GitHub issue |

## Skills

| Skill | Description |
|-------|-------------|
| [bot-comment-pr](bot-comment-pr.md) | Post general comments to pull requests |
| [bot-comment-issue](bot-comment-issue.md) | Post comments to GitHub issues |

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

**Environment override:**

```bash
# Override config file location
HEY_AMELIA_CONFIG="path/to/config.yaml" uv run python ...
```
