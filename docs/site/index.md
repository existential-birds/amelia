---
layout: home

hero:
  name: "Amelia"
  text: "Multi-Agent Research Platform"
  tagline: An open-source laboratory for experimenting with agentic workflows and AI-native software development patterns.
  actions:
    - theme: brand
      text: Get Started
      link: /guide/usage
---

<TerminalHero />

## Quick Start

```bash
# Install amelia
uv tool install git+https://github.com/existential-birds/amelia.git

# Create a profile
amelia config profile create dev --driver api:openrouter --tracker github

# Start the dashboard
amelia dev

# Run a workflow on an issue
amelia start 123
```

<div class="research-link">

Curious about the ideas and research that influenced Amelia? [Explore our research notes →](/ideas/)

</div>

<style>
.research-link {
  max-width: 688px;
  margin: 2rem auto 0;
  padding: 1.25rem 1.5rem;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  border-radius: 8px;
  text-align: center;
  font-size: 0.95rem;
  color: var(--vp-c-text-2);
}

.research-link a {
  color: var(--vp-c-brand-1);
  font-weight: 500;
}

.research-link a:hover {
  text-decoration: underline;
}
</style>
