<template>
  <section class="amelia-section capabilities-research" aria-label="Agent orchestration capabilities">
    <h2 class="section-heading">What You Can Do With It</h2>
    <ul class="capabilities-grid" role="list">
      <li v-for="item in items" :key="item.capability" class="capability">
        <strong class="capability-name">{{ item.capability }}</strong>
        <span class="capability-detail">{{ item.detail }}</span>
      </li>
    </ul>
    <a :href="withBase('/architecture/inspiration')" class="research-link" aria-label="View full research foundations">
      Full research foundations &rarr;
    </a>
  </section>
</template>

<script setup lang="ts">
import { withBase } from 'vitepress'

const items = [
  { capability: 'Plan, approve, build, review', detail: 'Architect decomposes the task, you approve, Developer writes code, Reviewer checks it. From MetaGPT and HULA.' },
  { capability: 'Iterate until it works', detail: 'Developer-Reviewer loop cycles on feedback until the code passes. Based on AgentCoder and Reflexion.' },
  { capability: 'Automated code review', detail: 'Reviewer acts as LLM-as-a-Judge, scoring code against criteria. From MT-Bench evaluation research.' },
  { capability: 'Search your own docs', detail: 'Upload project docs, agents query them via pgvector RAG. Uses RAPTOR hierarchical retrieval.' },
  { capability: 'Consult an Oracle', detail: 'Route hard decisions to a dedicated reasoning model. Inspired by Amp\'s GPT-5 Oracle pattern.' },
  { capability: 'Run code in a sandbox', detail: 'Agents execute in Docker with network isolation. Follows Recursive Language Models sandbox design.' },
  { capability: 'Swap drivers per agent', detail: 'Choose Claude Code CLI or API SDK per role. Implements SWE-agent\'s agent-computer interface principle.' },
  { capability: 'Resume from checkpoints', detail: 'Pick up failed workflows where they stopped. Uses Context Folding branch/return primitives.' },
  { capability: 'One model per role', detail: 'Assign different LLMs to Architect, Developer, and Reviewer. ReAct-style reasoning and acting per agent.' },
  { capability: 'Configure via YAML profiles', detail: 'Prompts, tools, models, and context per profile. Stateless, immutable, append-only state design.' },
  { capability: 'Generate specs from issues', detail: 'Spec Builder turns GitHub/Linear issues into structured implementation plans.' },
  { capability: 'Watch it run in real time', detail: 'WebSocket-powered React dashboard shows agent progress as it happens.' },
]
</script>

<style scoped>
.capabilities-research {
  padding-top: 2rem;
  padding-bottom: 2.5rem;
}

.section-heading {
  font-family: var(--vp-font-family-mono);
  font-weight: 500;
  font-size: 1.25rem;
  letter-spacing: -0.02em;
  text-transform: uppercase;
  color: var(--vp-c-heading-1);
  margin-bottom: 1.5rem;
}

.capabilities-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
}

.capability {
  display: flex;
  flex-direction: column;
  padding: 0.625rem 0;
  border-bottom: 1px solid var(--vp-c-divider);
}

.capability-name {
  font-family: var(--vp-font-family-mono);
  font-size: 0.8125rem;
  font-weight: 500;
  color: var(--vp-c-text-1);
  line-height: 1.4;
}

.capability-detail {
  font-size: 0.8125rem;
  color: var(--vp-c-text-2);
  line-height: 1.5;
  margin-top: 0.125rem;
}

.research-link {
  display: inline-block;
  margin-top: 1.25rem;
  font-family: var(--vp-font-family-mono);
  font-size: 0.8125rem;
  color: var(--vp-c-brand-1);
  font-weight: 500;
}

.research-link:hover {
  text-decoration: underline;
}

@media (max-width: 768px) {
  .capabilities-grid {
    grid-template-columns: 1fr;
  }
}
</style>
