---
description: fetch coderabbitai comments from current PR and evaluate with ka-eval-feedback
---
Fetch all comments from the `coderabbitai[bot]` user on the current PR and evaluate them.

## Steps

1. **Get the current PR context** using:
   ```bash
   gh pr view --json number,headRepository
   ```
   Extract owner, repo, and PR number.

2. **Fetch all CodeRabbit comments** - there are two types, and there may be MULTIPLE of each. Use `--paginate` to ensure all comments are fetched (GitHub returns max 100 per page):

   **Issue comments** (general summary/overview - CodeRabbit posts detailed summaries here):
   ```bash
   gh api --paginate repos/{owner}/{repo}/issues/{number}/comments \
     --jq '.[] | select(.user.login == "coderabbitai[bot]") | .body'
   ```

   **Review comments** (line-specific, separated by `---`):
   ```bash
   gh api --paginate repos/{owner}/{repo}/pulls/{number}/comments \
     --jq '.[] | select(.user.login == "coderabbitai[bot]") | "---\nFile: \(.path):\(.line)\n\(.body)\n"'
   ```

3. **Format the feedback** into a single document. Note: strip out `<details>` collapsible sections containing "Learnings" or AI command hints as they are noise:
   ```
   # CodeRabbit Review Feedback

   ## Summary/Overview
   [all issue comments here - there may be multiple]

   ## Line-Specific Comments
   [all review comments here, each prefixed with "File: path:line"]
   ```

4. **Run ka-eval-feedback ultrathink** by invoking `/amelia:eval-feedback ultrathink` with the formatted content as the argument. The superpowers:receiving-code-review skill will guide evaluation of each piece of feedback.
