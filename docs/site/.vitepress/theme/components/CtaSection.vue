<script setup lang="ts">
import { withBase } from 'vitepress'
</script>

<template>
  <section class="amelia-section cta-section">
    <h2 class="cta-heading">Start Experimenting</h2>
    <div class="cta-clone">
      <code>git clone https://github.com/existential-birds/amelia.git && cd amelia</code>
    </div>
    <div class="cta-links">
      <a href="https://github.com/existential-birds/amelia" class="cta-link" target="_blank" rel="noopener">
        GitHub
      </a>
      <span class="cta-sep" aria-hidden="true">/</span>
      <a :href="withBase('/architecture/inspiration')" class="cta-link">
        Architecture
      </a>
      <span class="cta-sep" aria-hidden="true">/</span>
      <a :href="withBase('/guide/usage')" class="cta-link">
        Get Started
      </a>
    </div>
  </section>
</template>

<style scoped>
.cta-section {
  padding-top: 2.5rem;
  padding-bottom: 3rem;
  text-align: center;
}

.cta-heading {
  font-family: var(--vp-font-family-mono);
  font-weight: 500;
  font-size: 1.25rem;
  letter-spacing: -0.02em;
  text-transform: uppercase;
  color: var(--vp-c-heading-1);
  margin-bottom: 1rem;
}

.cta-clone {
  display: inline-block;
  padding: 0.625rem 1.25rem;
  background: var(--vp-c-bg-soft);
  border: 1px solid var(--vp-c-divider);
  border-radius: 6px;
  margin-bottom: 1.25rem;
}

.cta-clone code {
  font-family: var(--vp-font-family-mono);
  font-size: 0.8125rem;
  color: var(--vp-c-text-1);
  background: none;
  padding: 0;
}

.cta-links {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-family: var(--vp-font-family-mono);
  font-size: 0.875rem;
}

.cta-link {
  color: var(--vp-c-brand-1);
  font-weight: 500;
}

.cta-link:hover {
  text-decoration: underline;
}

.cta-sep {
  color: var(--vp-c-text-3);
}
</style>
