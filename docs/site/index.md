---
layout: home
title: Open-Source Agent Orchestration Framework
description: Amelia is an open-source agent orchestration framework that coordinates AI agents to plan, build, review, and ship code using multi-agent workflows.

hero:
  name: "Amelia"
  text: "Open-Source Agent Orchestration"
  tagline: Coordinate AI agents to plan, build, review, and ship code.
  actions:
    - theme: brand
      text: Get Started
      link: /guide/usage
---

<TerminalHero />

<CapabilitiesAndResearch />

## Quick Start

```bash
# Install amelia
uv tool install git+https://github.com/existential-birds/amelia.git

# Create a profile (interactive prompts for driver, model, tracker)
amelia config profile create dev --activate

# Start the API server and dashboard
amelia dev

# Run a workflow on an issue
amelia start 123
```

<CtaSection />
