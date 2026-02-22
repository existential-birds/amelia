---
layout: home

hero:
  name: "Amelia"
  text: "Multi-Agent Research Platform"
  tagline: An open-source laboratory for experimenting with agentic workflows.
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
