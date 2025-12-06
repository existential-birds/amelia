# Testing Documentation

This folder contains manual testing procedures and test plans for features that require human verification beyond automated tests.

## Contents

| Document | Description |
|----------|-------------|
| [WebSocket Manual Testing Plan](websocket-manual-testing-plan.md) | Manual testing procedures for WebSocket real-time functionality |

## Purpose

Manual test plans are used when:
- **Integration testing** - Verifying end-to-end flows across multiple systems
- **UI/UX validation** - Testing user interactions that require human judgment
- **Real-time features** - Testing WebSocket connections and live updates
- **Edge cases** - Scenarios difficult to reproduce in automated tests

## PR Test Plans

For PRs with significant changes, create a test plan at `docs/testing/pr-test-plan.md`. The `amelia-qa` GitHub Action will automatically post it as a PR comment. Delete the file after the PR is merged.

## Related

- [CLAUDE.md](../../CLAUDE.md) - Project testing conventions and commands
