# Amelia Commands

This document lists all the available commands for the Amelia project.

| Command | Description |
| --- | --- |
| speckit.analyze | Perform a non-destructive cross-artifact consistency and quality analysis across spec.md, plan.md, and tasks.md after task generation. |
| speckit.checklist | Create a checklist for the following domain... |
| speckit.clarify | Clarify specification requirements |
| speckit.constitution | Create or update the project constitution from interactive or provided principle inputs, ensuring all dependent templates stay in sync. |
| speckit.implement | Execute the implementation planning workflow using the plan template to generate design artifacts. |
| speckit.plan | Execute the implementation planning workflow using the plan template to generate design artifacts. |
| speckit.search-modified-files | Search for files modified in the last N days. |
| speckit.specify | Create or update the feature specification from a natural language feature description. |
| speckit.tasks | Break the plan into tasks |
| speckit.taskstoissues | Convert existing tasks into actionable, dependency-ordered GitHub issues for the feature based on available design artifacts. |

## Amelia: Agentic Orchestrator

Amelia is a local agentic coding system designed to orchestrate software development tasks while adapting to your environment's constraints.

### Work Profile: Enterprise-Ready Development

In the **Work Profile**, Amelia operates strictly within enterprise security constraints, ensuring no code or sensitive data leaves your local environment via direct API calls. Instead, it orchestrates your existing, approved CLI tools to act as a force multiplier.

**What you can achieve:**

*   **Automated Issue Resolution**: Point Amelia at a Jira ticket (e.g., `PROJ-123`). It will fetch the details using `acli`, plan the necessary changes, and implement them by driving the `claude` CLI tool—just like a human developer typing at a terminal.
*   **Compliance by Default**: All AI interactions happen through your authenticated `claude` CLI session, inheriting your existing enterprise SSO and data retention policies.
*   **Local Reviews**: Run `amelia review --local` to get an instant, multi-perspective code review of your uncommitted changes without pushing to a remote server.
*   **Interactive Guidance**: Since Amelia drives the CLI, you can watch the progress in real-time, pause execution, or intervene if the agent starts drifting off-course.