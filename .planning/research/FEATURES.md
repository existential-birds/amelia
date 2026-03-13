# Feature Landscape

**Domain:** PR Auto-Fix / Automated Review Comment Resolution
**Researched:** 2026-03-13

## Table Stakes

Features users expect from any PR auto-fix tool. Missing any of these and the product feels broken or unusable.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Fetch and parse PR review comments | Cannot fix what you cannot read; every tool in this space starts here | Low | Amelia already has `gh` CLI patterns via `GithubTracker`. Use `gh api` for REST, `gh api graphql` for thread resolution |
| Classify comments as actionable vs non-actionable | Human review comments mix requests, questions, praise, and discussion. Fixing a "nice work!" comment is nonsensical | Medium | CodeRabbit, Qodo, and agent-reviews all filter comments. LLM classification is the standard approach (keyword matching is too brittle) |
| Apply code fixes from review feedback | The core value proposition. Every competitor does this | High | Amelia's Developer agent already handles agentic code changes -- the plumbing exists |
| Commit and push fixes to PR branch | Fixes are useless if they stay local | Low | Standard git operations. Must push to the PR's head branch, not main |
| Reply to review comments explaining what was fixed | Reviewers need to know what happened. CodeRabbit, Qodo, Gitar, and agent-reviews all post explanatory replies | Low | Each reply should reference the specific change made. Brief, not verbose |
| Resolve review threads after fixing | The completion signal. Without this, reviewers must manually check and resolve threads even after a fix lands | Medium | Requires GitHub GraphQL API (`resolveReviewThread` mutation). REST API cannot do this. agent-reviews and Qodo both handle this |
| Skip bot/self comments | Prevent infinite loops where the tool responds to its own comments or other bots | Low | Filter by author. agent-reviews explicitly distinguishes bot vs human comments |
| Deduplication / processed comment tracking | Prevent re-fixing already-handled comments on subsequent polls | Low | Track processed comment IDs persistently. Every polling-based tool needs this |
| Max iteration limits | Prevent infinite fix loops when reviewer and agent disagree | Low | Essential safety valve. If a thread gets N fix attempts without resolution, stop and flag for human |
| Manual trigger (CLI or API) | Users want to kick off a fix on-demand, not only wait for a poll cycle | Low | `fix-pr` one-shot command. Both CodeRabbit and Qodo support manual trigger via chat commands |

## Differentiators

Features that set Amelia apart from the competition. Not expected by users, but create real competitive advantage.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Adjustable fix aggressiveness spectrum | No competitor offers a configurable dial from "critical-only" to "exemplary." CodeRabbit and Copilot are binary (fix or don't). This lets teams match their quality bar without forking config | Medium | Four levels: critical-only, standard, thorough, exemplary. LLM classification step determines which comments are actionable at configured level. Per-profile default with per-PR override |
| Background polling with configurable interval | Most tools are webhook-triggered (requiring public endpoints) or manually invoked. Polling works behind firewalls and needs zero infrastructure beyond the running agent | Medium | Follow existing `WorktreeHealthChecker` pattern. Must respect GitHub rate limits with backoff |
| Dashboard with real-time fix visibility | Most PR auto-fix tools are headless (CLI/GitHub comments only). Seeing fix progress live -- which comments triggered a workflow, which are resolved, which failed -- is a genuine UX advantage | High | Amelia already has WebSocket event bus and dashboard. Extend with PR-specific views showing comment-to-fix mapping |
| Comment-to-fix traceability | Show exactly which review comment led to which code change. Most tools just post "I fixed things" without clear tracing | Medium | Map each comment ID to the specific commit/diff that addressed it. Display in dashboard and in GitHub reply |
| Profile-scoped configuration | Different repos/teams can have different aggressiveness settings, polling intervals, and behaviors. Most competitors are one-size-fits-all per org | Low | Amelia already has profile-based config. Extend with PR auto-fix settings |
| Composable pipeline architecture | The PR_AUTO_FIX pipeline can be invoked standalone or composed with the existing review pipeline. Most competitors are monolithic | Medium | LangGraph pipeline registered in registry. Existing review pipeline can optionally invoke it when PR context is available |

## Anti-Features

Features to explicitly NOT build. Either out of scope, dangerous, or better left to other tools.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Auto-merge PRs after fixing | Dangerous. Merging is a human decision that considers business context, release timing, and approval requirements. Even Copilot Autofix does not auto-merge | Fix comments and resolve threads only. Let humans approve and merge |
| Generate new review comments (AI reviewer) | Amelia already has a local review pipeline. Generating GitHub review comments would conflict with human reviewers and create noise. CodeRabbit occupies this niche -- compete on the fix side, not the review side | Consume human review comments, don't generate new ones on GitHub. Keep local review for pre-push quality |
| Cross-repo PR monitoring | Massively increases complexity (auth, rate limits, context switching). Most teams work repo-by-repo | Scope to the profile's configured repository. Users can run multiple profiles for multiple repos |
| Webhook-based triggers | Requires a publicly accessible endpoint, complicates deployment, and adds infrastructure requirements. Polling is simpler and works everywhere | Use polling with configurable intervals. Manual trigger covers the "I want it now" case |
| Full GitHub PR creation from scratch | Sweep AI does this (issue-to-PR). It's a different product category (issue automation, not review response) | Focus on fixing existing PRs that humans or other agents created. Stay in the "review response" lane |
| PyGithub/Octokit integration | Adding a GitHub client library creates a parallel API surface to the existing `gh` CLI pattern. Maintenance burden for marginal benefit | Use `gh` CLI subprocess pattern consistent with `GithubTracker`. `gh api` and `gh api graphql` cover all needed endpoints |
| Non-GitHub forge support (v1) | GitLab, Bitbucket, Azure DevOps each have different review comment APIs. Supporting them triples the integration surface | GitHub only for v1. Abstract the interface so forge-specific backends can be added later without rewriting the core |
| Automatic test generation for fixes | CodeRabbit and Qodo offer test generation. It's a separate concern that inflates scope and fix time | Let the Developer agent decide if tests are needed based on the review comment content. Don't force test generation as a feature |

## Feature Dependencies

```
Fetch PR comments --> Classify comments (needs raw comments to classify)
Classify comments --> Apply fixes (needs actionable comment list)
Apply fixes --> Commit and push (needs code changes to commit)
Commit and push --> Reply to comments (needs commit ref to reference in reply)
Reply to comments --> Resolve threads (resolve after replying)

Background polling --> Fetch PR comments (polling triggers fetch cycle)
Manual trigger --> Fetch PR comments (manual trigger also triggers fetch)

Deduplication --> Fetch PR comments (filter already-processed before classification)
Bot detection --> Fetch PR comments (filter before classification)
Max iterations --> Resolve threads (stop after N failed fix attempts)

Aggressiveness config --> Classify comments (aggressiveness level drives classification)
Profile config --> Aggressiveness config (profile provides defaults)

Dashboard views --> Event bus integration (dashboard needs fix lifecycle events)
Comment-to-fix tracing --> Apply fixes + Reply to comments (needs both sides of the mapping)
```

## MVP Recommendation

Prioritize for first working version:

1. **Fetch and parse PR review comments** -- foundation everything else builds on
2. **Bot/self comment filtering** -- prevent loops from day one
3. **LLM comment classification with aggressiveness** -- the core differentiator, build it early
4. **Apply fixes via Developer agent** -- the core value
5. **Commit, push, reply, and resolve threads** -- complete the loop
6. **Deduplication and max iteration limits** -- safety features for production use
7. **Manual CLI trigger (`fix-pr`)** -- fastest way to test and demo

Defer to post-MVP:
- **Background polling**: Adds operational complexity. Manual trigger is sufficient for v1 validation
- **Dashboard integration**: High complexity, and the feature works without it. Add after the core loop is proven
- **Comment-to-fix traceability**: Nice-to-have visualization. The core loop works without fine-grained tracing
- **Per-PR aggressiveness override**: Profile-level default is enough initially

## Sources

- [CodeRabbit - AI Code Reviews](https://www.coderabbit.ai/)
- [CodeRabbit Documentation](https://docs.coderabbit.ai/)
- [GitHub Copilot Autofix - Responsible Use](https://docs.github.com/en/code-security/responsible-use/responsible-use-autofix-code-scanning)
- [Copilot Autofix - Secure Code Faster](https://github.blog/news-insights/product-news/secure-code-more-than-three-times-faster-with-copilot-autofix/)
- [agent-reviews - npm](https://www.npmjs.com/package/agent-reviews)
- [agent-reviews on GitHub](https://github.com/pbakaus/agent-reviews)
- [gh-pr-review GitHub CLI extension](https://github.com/agynio/gh-pr-review)
- [Qodo PR-Agent Review Docs](https://qodo-merge-docs.qodo.ai/tools/review/)
- [Qodo Agent Skills for Auto-Fix](https://www.qodo.ai/blog/how-i-use-qodos-agent-skills-to-auto-fix-issues-in-pull-requests/)
- [Gitar - AI Code Review and CI Auto-Fix](https://cms.gitar.ai/ai-code-review-ci-fix/)
- [Sweep AI Documentation](https://docs.sweep.dev/)
- [State of AI Code Review Tools 2025](https://www.devtoolsacademy.com/blog/state-of-ai-code-review-tools-2025/)
- [Best AI Code Review Tools 2026 - Qodo](https://www.qodo.ai/blog/best-automated-code-review-tools-2026/)
