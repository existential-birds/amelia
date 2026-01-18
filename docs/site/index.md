---
layout: home

hero:
  name: "Amelia"
  text: "Agentic Coding Orchestrator"
  tagline: Multi-agent orchestration for software development with human-in-the-loop approval gates, defense-in-depth security, and end-to-end observability. Local-first.
  actions:
    - theme: brand
      text: Get Started
      link: /guide/usage
---

<TerminalHero />

## Quick Start

```bash
# Install amelia globally
uv tool install git+https://github.com/existential-birds/amelia.git

# Configure in your project
cat > settings.amelia.yaml << 'EOF'
active_profile: dev
profiles:
  dev:
    driver: api:openrouter
    tracker: github
EOF

# Generate a plan for an issue
amelia plan 123

# Or run the full workflow
amelia start 123
```
