---
layout: home

hero:
  name: "Amelia"
  text: "Agentic Coding Orchestrator"
  tagline: A local AI orchestrator that coordinates specialized agents through a LangGraph state machine. Built for developers who want AI assistance with full control.
  actions:
    - theme: brand
      text: Get Started
      link: /guide/usage
---

<TerminalHero />

## Quick Start

```bash
# Install amelia globally
uv tool install git+https://github.com/anderskev/amelia.git

# Configure in your project
cat > settings.amelia.yaml << 'EOF'
active_profile: dev
profiles:
  dev:
    driver: api:openai
    tracker: github
EOF

# Generate a plan for an issue
amelia plan-only 123

# Or run the full workflow
amelia start 123
```
