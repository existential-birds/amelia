---
description: fetch greptile-apps comments from current PR and evaluate with amelia:eval-feedback
---
Fetch all comments from the `greptile-apps[bot]` user on the current PR and evaluate them.

## Steps

1. **Get the current PR context** using:
   ```bash
   gh pr view --json number,headRepository
   ```
   Extract owner, repo, and PR number.

2. **Fetch all greptile comments** - there are two types, and there may be MULTIPLE of each. Use `--paginate` to ensure all comments are fetched (GitHub returns max 100 per page):

   **Issue comments** (general summary/overview):
   ```bash
   gh api --paginate repos/{owner}/{repo}/issues/{number}/comments \
     --jq '.[] | select(.user.login == "greptile-apps[bot]") | .body'
   ```

   **Review comments** (line-specific, separated by `---`):
   ```bash
   gh api --paginate repos/{owner}/{repo}/pulls/{number}/comments \
     --jq '.[] | select(.user.login == "greptile-apps[bot]") | "---\nFile: \(.path):\(.line)\n\(.body)\n"'
   ```

3. **Format the feedback** into a single document. Note: strip out the `<details>` "Prompt To Fix With AI" sections as they are noise:
   ```
   # Greptile Code Review Feedback

   ## Summary/Overview
   [all issue comments here - there may be multiple]

   ## Line-Specific Comments
   [all review comments here, each prefixed with "File: path:line"]
   ```

4. **Run amelia:eval-feedback ultrathink** by invoking `/amelia:eval-feedback ultrathink` with the formatted content as the argument. The superpowers:receiving-code-review skill will guide evaluation of each piece of feedback.
