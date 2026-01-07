# User Guide

Install, configure, and run your first multi-agent workflow in under five minutes.

## Quick Links

- [Usage](/guide/usage) — CLI commands, API reference, example workflows
- [Configuration](/guide/configuration) — Profile setup, driver options, retry settings
- [Troubleshooting](/guide/troubleshooting) — Common issues and solutions

## Getting Started

1. **Install Amelia** (the easy part)
   ```bash
   uv tool install git+https://github.com/existential-birds/amelia.git
   ```

2. **Create configuration** in your project root:
   ```yaml
   # settings.amelia.yaml
   active_profile: dev
   profiles:
     dev:
       driver: api:openrouter
       tracker: github
   ```

3. **Run your first workflow**:
   ```bash
   amelia plan 123  # Generate plan for issue #123
   ```
   You should see the Architect agent generate an implementation plan for review.

## What's Next

- [Usage Guide](/guide/usage) — all the CLI commands you'll actually use
- [Configuration](/guide/configuration) — drivers and trackers for your environment
- [Architecture](/architecture/concepts) — how the agents work
