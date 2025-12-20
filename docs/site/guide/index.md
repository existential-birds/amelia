# User Guide

This guide gets you from zero to orchestrating AI agents in about three minutes. Possibly four if you read slowly.

## Quick Links

- [Usage](/guide/usage) — CLI commands, API reference, example workflows
- [Configuration](/guide/configuration) — Profile setup, driver options, retry settings
- [Troubleshooting](/guide/troubleshooting) — Common issues and solutions

## Getting Started

1. **Install Amelia** (the easy part)
   ```bash
   uv tool install git+https://github.com/anderskev/amelia.git
   ```

2. **Create configuration** in your project root:
   ```yaml
   # settings.amelia.yaml
   active_profile: dev
   profiles:
     dev:
       driver: api:openai
       tracker: github
   ```

3. **Run your first workflow**:
   ```bash
   amelia plan-only 123  # Generate plan for issue #123
   ```
   If this works, you now have AI agents arguing about your codebase. Congratulations.

## What's Next

- [Usage Guide](/guide/usage) — all the CLI commands you'll actually use
- [Configuration](/guide/configuration) — drivers and trackers for your environment
- [Architecture](/architecture/concepts) — how the agents work
