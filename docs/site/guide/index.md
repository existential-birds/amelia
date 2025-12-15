# User Guide

Welcome to the Amelia user guide. This section covers everything you need to use Amelia in your projects.

## Quick Links

- [Usage](/guide/usage) - CLI commands, API reference, example workflows
- [Configuration](/guide/configuration) - Profile setup, driver options, retry settings
- [Troubleshooting](/guide/troubleshooting) - Common issues and solutions

## Getting Started

1. **Install Amelia**
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

## Next Steps

- Read the full [Usage Guide](/guide/usage) for all CLI commands
- Configure [drivers and trackers](/guide/configuration) for your environment
- Understand [how agents work](/architecture/concepts)
